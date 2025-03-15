import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from Service import Service
from Database import Database



#API scope
SCOPES = ['https://www.googleapis.com/auth/drive']


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


#Get paths from environment
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)

class GoogleDrive(Service):
    def __init__(self, token_dir="tokens", credentials_file="credentials.json"):
        self.token_dir = token_dir
        self.credentials_file = credentials_file
        self.scopes = SCOPES
        self.service = None
        os.makedirs(self.token_dir, exist_ok=True)
        self.db = Database().get_instance()

    def authenticate(self, bucket_number, user_id):
        """
        Authenticate with Google Drive and store tokens in MongoDB.
        """
        token_data = self.db.tokens_collection.find_one({"user_id": user_id, "bucket_number": bucket_number})
        
        creds = None
        if token_data:
            try:
                creds = Credentials.from_authorized_user_info(token_data)
            except Exception as e:
                logger.error(f"Error loading token: {e}. Re-authenticating.")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    logger.info("🔄 Refreshing expired token...")
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Error refreshing token: {e}. Re-authenticating.")
                    creds = None

            if not creds:
                logger.info("Starting Google Drive authentication...")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.scopes)
                creds = flow.run_local_server(port=0)

                # Save new credentials to MongoDB
                self.db.tokens_collection.update_one(
                    {"user_id": user_id, "bucket_number": bucket_number},
                    {"$set": {
                        "access_token": creds.token,
                        "refresh_token": creds.refresh_token,
                        "client_id": creds.client_id,
                        "client_secret": creds.client_secret,
                        "token_uri": creds.token_uri,
                        "scopes": creds.scopes
                    }},
                    upsert=True
                )
                logger.info("Authentication successful. Token saved to MongoDB.")
                #Update user's drives list in MongoDB
                self.db.users_collection.update_one(
                    {"_id": user_id},
                    {"$addToSet": {"drives": bucket_number}},
                    upsert=True
                )
        self.service = build("drive", "v3", credentials=creds)
        return self.service
    
    def listFiles(self, max_results=None, query=None):
        """
        List files from Google Drive with correct web links.
        """
        if not self.service:
            raise ValueError("Google Drive service not authenticated. Call authenticate() first.")

        files_list = []
        page_token = None
        query_filter = f"name contains '{query}'" if query else None

        while True:
            results = self.service.files().list(
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                q=query_filter
            ).execute()

            for file in results.get("files", []):
                file_id = file["id"]
                file_link = f"https://drive.google.com/file/d/{file_id}/view"  # Generate correct link

                files_list.append({
                    "name": file["name"],
                    "size": file.get("size", "Unknown"),
                    "path": file_link,
                    "provider": "GoogleDrive"
                })

            page_token = results.get("nextPageToken")
            if not page_token:
                break

        return files_list

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
