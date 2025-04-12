import os
import logging
import dropbox
from dropbox.exceptions import AuthError, ApiError
from dropbox.oauth import DropboxOAuth2Flow
from Service import Service
from Database import Database

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DropboxService(Service):
    def __init__(self, token_dir="tokens", app_key=None, app_secret=None):
        self.token_dir = token_dir
        self.app_key = app_key
        self.app_secret = app_secret
        self.service = None
        os.makedirs(self.token_dir, exist_ok=True)
        self.db = Database().get_instance()

    def authenticate(self, bucket_number, user_id):
        """
        Authenticate with Dropbox using AuthManager.
        """
        from AuthManager import AuthManager
        auth_manager = AuthManager(user_id, self.token_dir)
        self.service = auth_manager.authenticate_dropbox(bucket_number, self.app_key, self.app_secret)
        return self.service

    def listFiles(self, folder_path="", query=None):
        """
        List files from Dropbox with optional query filtering.
        """
        if not self.service:
            raise ValueError("Dropbox service not authenticated. Call authenticate() first.")
    
        files_list = []
        try:
            result = self.service.files_list_folder(folder_path, recursive=True)
            logger.info("Request to files/list_folder")
            while True:
                for file in result.entries:
                    if isinstance(file, dropbox.files.FileMetadata):
                        # Apply query filter if provided
                        if query and query.lower() not in file.name.lower():
                            continue
                        file_link = f"https://www.dropbox.com/home/{file.path_display}"
                        files_list.append({
                            "name": file.name,
                            "size": file.size,
                            "path": file_link,
                            "provider": "Dropbox",
                            "id": file.id
                        })
                if not result.has_more:
                    break
                result = self.service.files_list_folder_continue(result.cursor)
            logger.info(f"Retrieved {len(files_list)} files from Dropbox for query: {query or 'all'}")
            return files_list
        except ApiError as err:
            logger.error(f"Dropbox API error: {err}")
            return []
        except Exception as e:
            logger.error(f"Error listing files: {e}")
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