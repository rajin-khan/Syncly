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
            return self._initialize_client_with_tokens(token_data, user_id, bucket_number)
        else:
            return self._start_new_authentication(user_id, bucket_number)

    def _initialize_client_with_tokens(self, token_data, user_id, bucket_number):
        """
        Initialize the Dropbox client using stored tokens.
        """
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        try:
            self.client = dropbox.Dropbox(
                oauth2_access_token=access_token,
                oauth2_refresh_token=refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret,
            )
            # Test the token by making a simple API call
            self.client.users_get_current_account()
            logger.info("Dropbox client initialized successfully.")
            return self.client
        except AuthError as e:
            if "expired_access_token" in str(e):
                logger.info("🔄 Refreshing expired Dropbox token...")
                return self._refresh_tokens(user_id, bucket_number, refresh_token)
            else:
                logger.error(f"Dropbox authentication error: {e}")
                return None

    def _refresh_tokens(self, user_id, bucket_number, refresh_token):
        """
        Refresh the Dropbox tokens using the refresh token.
        """
        try:
            auth_flow = DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)
            new_access_token, new_refresh_token = auth_flow.refresh_access_token(refresh_token)

            # Update the tokens in MongoDB
            self.db.tokens_collection.update_one(
                {"user_id": user_id, "bucket_number": bucket_number},
                {"$set": {
                    "access_token": new_access_token,
                    "refresh_token": new_refresh_token
                }},
                upsert=True
            )
            logger.info("Tokens refreshed and saved to MongoDB.")

            # Reinitialize the Dropbox client with the new tokens
            self.client = dropbox.Dropbox(
                oauth2_access_token=new_access_token,
                oauth2_refresh_token=new_refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret,
            )
            logger.info("Dropbox client reinitialized successfully.")
            return self.client
        except Exception as refresh_error:
            logger.error(f"Failed to refresh Dropbox token: {refresh_error}")
            return None

    def _start_new_authentication(self, user_id, bucket_number):
        """
        Start a new OAuth 2.0 authentication flow.
        """
        logger.info("Starting Dropbox authentication...")
        auth_flow = DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)
        authorize_url = auth_flow.start()
        print(f"Authorize this app: {authorize_url}")
        auth_code = input("\nEnter auth code: ").strip()

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
            #update the user's drives list in MongoDB
            self.db.users_collection.update_one(
                {"username": user_id},
                {"$addToSet":{"drives":bucket_number}}
            )
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
            if "expired_access_token" in str(e):
                logger.error("Access token expired. Please reauthenticate.")
            elif "rate_limit" in str(e):
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
            if "not_found" in str(err):
                logger.error(f"Folder not found: {folder_path}")
            elif "no_permission" in str(err):
                logger.error(f"No permission to access folder: {folder_path}")
            else:
                logger.error(f"Dropbox API error: {err}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return []
