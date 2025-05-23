import os
import logging
from googleapiclient.discovery import build
from Service import Service
from Database import Database

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleDrive(Service):
    def __init__(self, token_dir="tokens", credentials_file="credentials.json"):
        self.token_dir = token_dir
        self.credentials_file = credentials_file
        self.service = None
        os.makedirs(self.token_dir, exist_ok=True)
        self.db = Database().get_instance()

    def authenticate(self, bucket_number, user_id):
        """
        Authenticate with Google Drive using AuthManager.
        """
        from AuthManager import AuthManager
        auth_manager = AuthManager(user_id, self.token_dir)
        self.service = auth_manager.authenticate_google_drive(bucket_number, self.credentials_file)
        return self.service

    def listFiles(self, max_results=None, query=None):
        """
        List files from Google Drive with optional query filtering.
        """
        if not self.service:
            raise ValueError("Google Drive service not authenticated. Call authenticate() first.")
    
        files_list = []
        page_token = None
        # Escape single quotes in query outside the f-string
        escaped_query = query.replace("'", r"\'") if query else None
        query_filter = f"name contains '{escaped_query}'" if escaped_query else None
    
        try:
            while True:
                results = self.service.files().list(
                    pageSize=100 if not max_results else min(max_results, 100),
                    fields="nextPageToken, files(id, name, mimeType, size)",
                    pageToken=page_token,
                    q=query_filter
                ).execute()
    
                for file in results.get("files", []):
                    file_id = file["id"]
                    file_link = f"https://drive.google.com/file/d/{file_id}/view"
                    files_list.append({
                        "name": file["name"],
                        "size": file.get("size", "Unknown"),
                        "path": file_link,
                        "provider": "GoogleDrive",
                        "id": file["id"]
                    })
    
                page_token = results.get("nextPageToken")
                if not page_token or (max_results and len(files_list) >= max_results):
                    break
                
            logger.info(f"Retrieved {len(files_list)} files from GoogleDrive for query: {query or 'all'}")
            return files_list
        except Exception as e:
            logger.error(f"Error listing files from GoogleDrive: {e}")
            return []

    def check_storage(self):
        """
        Check the storage quota for the authenticated Google Drive account.
        """
        if not self.service:
            logger.error("Service not authenticated. Call authenticate() first.")
            return 0, 0
        
        try:
            res = self.service.about().get(fields='storageQuota').execute()
            limit = int(res['storageQuota']['limit'])
            usage = int(res['storageQuota']['usage'])
            logger.info(f"Storage usage: {usage} bytes used out of {limit} bytes allocated.")
            return limit, usage
        except Exception as e:
            logger.error(f"Error checking storage: {e}")
            return 0, 0