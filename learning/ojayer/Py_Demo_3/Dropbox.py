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

class DropboxService(Service):
    def __init__(self, token_dir, app_key, app_secret):
        self.token_dir = token_dir
        self.app_key = app_key
        self.app_secret = app_secret
        self.client = None
        os.makedirs(self.token_dir, exist_ok=True)
        self.db = Database().get_instance()

    def authenticate(self, bucket_number, user_id):
        """
        Authenticate with Dropbox and store tokens in MongoDB.
        """
        token_data = self.db.tokens_collection.find_one({"user_id": user_id, "bucket_number": bucket_number})
        
        if token_data:
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            self.client = dropbox.Dropbox(
                oauth2_access_token=access_token,
                oauth2_refresh_token=refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret,
            )
            logger.info("Dropbox client initialized successfully.")
            return self.client

        # If no valid tokens, start OAuth 2.0 authentication
        logger.info("Starting Dropbox authentication...")
        auth_flow = DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)
        authorize_url = auth_flow.start()
        print(f"Authorize this app: {authorize_url}")
        auth_code = input("Enter auth code: ").strip()

        try:
            oauth_result = auth_flow.finish(auth_code)
            access_token = oauth_result.access_token
            refresh_token = oauth_result.refresh_token
            logger.info("Authentication successful.")

            # Save new tokens to MongoDB
            self.db.tokens_collection.update_one(
                {"user_id": user_id, "bucket_number": bucket_number},
                {"$set": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "app_key": self.app_key,
                    "app_secret": self.app_secret
                }},
                upsert=True
            )
            logger.info("Tokens saved to MongoDB.")

            # Initialize the Dropbox client
            self.client = dropbox.Dropbox(
                oauth2_access_token=access_token,
                oauth2_refresh_token=refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret,
            )
            logger.info("Dropbox client initialized successfully.")
            return self.client
        except Exception as e:
            logger.error(f"Error authenticating: {e}")
            return None

    def check_storage(self):
        """
        Check the storage quota for the authenticated Dropbox account.
        """
        if not self.client:
            raise ValueError("Service not authenticated. Call authenticate() first.")

        try:
            usage = self.client.users_get_space_usage()
            allocated = usage.allocation.get_individual().allocated
            used = usage.used
            logger.info(f"Storage usage: {used} bytes used out of {allocated} bytes allocated.")
            return allocated, used
        except ApiError as e:
            if "rate_limit" in str(e):
                logger.error("Rate limit exceeded. Please try again later.")
            elif "insufficient_permissions" in str(e):
                logger.error("Insufficient permissions to access storage information.")
            else:
                logger.error(f"Dropbox API error: {e}")
            return 0, 0
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return 0, 0

    def listFiles(self, folder_path="", query=None):
        """
        List all files in a Dropbox folder.
        """
        if not self.client:
            raise ValueError("Dropbox service not authenticated. Call authenticate() first.")

        files = []
        try:
            result = self.client.files_list_folder(folder_path)
            files.extend(result.entries)

            # Handle pagination
            while result.has_more:
                result = self.client.files_list_folder_continue(result.cursor)
                files.extend(result.entries)

            file_list = []
            for file in files:
                if isinstance(file, dropbox.files.FileMetadata):
                    file_list.append({
                        "name": file.name,
                        "size": file.size,
                        "path": f"https://www.dropbox.com/home/{file.path_display}",
                        "provider": "Dropbox"
                    })
            return file_list
        except dropbox.exceptions.ApiError as err:
            logger.error(f"Dropbox API error: {err}")
            return []