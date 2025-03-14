import os
import logging
import dropbox
from Service import Service
from dropbox.exceptions import AuthError, ApiError
from dropbox.oauth import DropboxOAuth2FlowNoRedirect
from Database import Database

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get paths from environment
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")
APP_KEY = os.getenv("DROPBOX_APP_KEY")
APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
os.makedirs(TOKEN_DIR, exist_ok=True)

class DropboxService(Service):
    def __init__(self, token_dir=TOKEN_DIR, app_key=APP_KEY, app_secret=APP_SECRET):
        self.token_dir = token_dir
        self.app_key = app_key
        self.app_secret = app_secret
        self.service = None
        os.makedirs(self.token_dir, exist_ok=True)
        self.db = Database().get_instance()

    def authenticate(self, bucket_number, user_id):
        """
        Authenticate with Dropbox and store tokens in MongoDB.
        """
        token_data = self.db.tokens_collection.find_one({"user_id": user_id, "bucket_number": bucket_number})
        
        creds = None
        if token_data:
            try:
                creds = {
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                    "app_key": self.app_key,
                    "app_secret": self.app_secret
                }
                self.service = dropbox.Dropbox(
                    oauth2_access_token=creds["access_token"],
                    oauth2_refresh_token=creds["refresh_token"],
                    app_key=creds["app_key"],
                    app_secret=creds["app_secret"]
                )
                # Test the connection
                self.service.users_get_current_account()
                logger.info("Dropbox client initialized successfully.")
            except Exception as e:
                logger.error(f"Error loading token: {e}. Re-authenticating.")
                creds = None

        if not creds or not self.service:
            if creds and "refresh_token" in creds:
                try:
                    logger.info("🔄 Refreshing expired token...")
                    auth_flow = DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)
                    new_access_token, new_refresh_token = auth_flow.refresh_access_token(creds["refresh_token"])
                    
                    # Update tokens in MongoDB
                    self.db.tokens_collection.update_one(
                        {"user_id": user_id, "bucket_number": bucket_number},
                        {"$set": {
                            "access_token": new_access_token,
                            "refresh_token": new_refresh_token,
                            "app_key": self.app_key,
                            "app_secret": self.app_secret
                        }},
                        upsert=True
                    )
                    creds = {
                        "access_token": new_access_token,
                        "refresh_token": new_refresh_token,
                        "app_key": self.app_key,
                        "app_secret": self.app_secret
                    }
                    self.service = dropbox.Dropbox(
                        oauth2_access_token=creds["access_token"],
                        oauth2_refresh_token=creds["refresh_token"],
                        app_key=creds["app_key"],
                        app_secret=creds["app_secret"]
                    )
                except Exception as e:
                    logger.error(f"Error refreshing token: {e}. Re-authenticating.")
                    creds = None

            if not creds:
                logger.info("Starting Dropbox authentication...")
                auth_flow = DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)
                authorize_url = auth_flow.start()
                print(f"Authorize this app: {authorize_url}")
                auth_code = input("\nEnter auth code: ").strip()

                oauth_result = auth_flow.finish(auth_code)
                creds = {
                    "access_token": oauth_result.access_token,
                    "refresh_token": oauth_result.refresh_token,
                    "app_key": self.app_key,
                    "app_secret": self.app_secret
                }

                # Save new credentials to MongoDB
                self.db.tokens_collection.update_one(
                    {"user_id": user_id, "bucket_number": bucket_number},
                    {"$set": {
                        "access_token": creds["access_token"],
                        "refresh_token": creds["refresh_token"],
                        "app_key": creds["app_key"],
                        "app_secret": creds["app_secret"]
                    }},
                    upsert=True
                )
                logger.info("Authentication successful. Token saved to MongoDB.")
                # Update user's drives list in MongoDB
                self.db.users_collection.update_one(
                    {"_id": user_id},
                    {"$addToSet": {"drives": bucket_number}},
                    upsert=True
                )
                self.service = dropbox.Dropbox(
                    oauth2_access_token=creds["access_token"],
                    oauth2_refresh_token=creds["refresh_token"],
                    app_key=creds["app_key"],
                    app_secret=creds["app_secret"]
                )
        return self.service

    def listFiles(self, folder_path="", query=None):
        """
        List files from Dropbox with correct web links.
        """
        if not self.service:
            raise ValueError("Dropbox service not authenticated. Call authenticate() first.")

        files_list = []
        try:
            result = self.service.files_list_folder(folder_path)
            while True:
                for file in result.entries:
                    if isinstance(file, dropbox.files.FileMetadata):
                        file_link = f"https://www.dropbox.com/home/{file.path_display}"
                        files_list.append({
                            "name": file.name,
                            "size": file.size,
                            "path": file_link,
                            "provider": "Dropbox"
                        })

                if not result.has_more:
                    break
                result = self.service.files_list_folder_continue(result.cursor)

            return files_list
        except ApiError as err:
            logger.error(f"Dropbox API error: {err}")
            return []

    def check_storage(self):
        """
        Check the storage quota for the authenticated Dropbox account.
        """
        if not self.service:
            logger.error("Service not authenticated. Call authenticate() first.")
            return 0, 0
        
        try:
            usage = self.service.users_get_space_usage()
            limit = usage.allocation.get_individual().allocated
            usage_used = usage.used
            logger.info(f"Storage usage: {usage_used} bytes used out of {limit} bytes allocated.")
            return limit, usage_used
        except Exception as e:
            logger.error(f"Error checking storage: {e}")
            return 0, 0
