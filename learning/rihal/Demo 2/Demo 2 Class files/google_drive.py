import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from service import service
from dotenv import load_dotenv
import re

#Load environment variables
load_dotenv()

#API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

#Get paths from environment
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)

class GoogleDrive(service):
    def __init__(self, token_dir="tokens", credentials_file="credentials.json"):
        self.token_dir = token_dir
        self.credentials_file = credentials_file
        self.scopes = ['https://www.googleapis.com/auth/drive']
        self.service = None  # Store the authenticated service instance
        os.makedirs(self.token_dir, exist_ok=True)

    """def authenticate(self, bucket_number):
        token_path = os.path.join(self.token_dir, f"bucket_{bucket_number}.json")
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, self.scopes)
            if creds.valid:
                self.service = build("drive", "v3", credentials=creds)
                return
        else:
            print(f"No token found for bucket {bucket_number}. Starting OAuth flow...")
        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.scopes)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        #Build the service
        self.service = build("drive", "v3", credentials=creds)
        return self.service"""
    
    def authenticate(self, bucket_number):
        token_path = os.path.join(TOKEN_DIR, f"bucket_{bucket_number}.json")
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if creds.valid:
                self.service = build("drive", "v3", credentials=creds)  # Store in self.service
                return self.service
        print(f"No valid token found for bucket {bucket_number}. Starting OAuth flow...")
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        self.service = build("drive", "v3", credentials=creds)  # Store in self.service
        return self.service


    def listFiles(self, max_results=None, query=None):
        if not self.service:
            raise ValueError("Service not authenticated. Call authenticate() first.")
        
        all_files = []
        page_token = None
        query_filter = f"name contains '{query}'" if query else None

        while True:
            results = self.service.files().list(
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                q=query_filter
            ).execute()
            all_files.extend(results.get('files', []))
            if max_results and len(all_files) >= max_results:
                return all_files[:max_results]
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        return all_files

    def check_storage(self):
        if not self.service:
            raise ValueError("Service not authenticated. Call authenticate() first.")
        
        try:
            res = self.service.about().get(fields='storageQuota').execute()
            limit = int(res['storageQuota']['limit'])
            usage = int(res['storageQuota']['usage'])
            return limit, usage
        except Exception as e:
            print(f"Error: {e}")
            return 0, 0
