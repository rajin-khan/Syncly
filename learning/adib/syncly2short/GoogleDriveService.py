import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveService:
    def __init__(self, token_dir="tokens", credentials_file="credentials.json"):
        self.token_dir = token_dir
        self.credentials_file = credentials_file
        os.makedirs(self.token_dir, exist_ok=True)
    
    def authenticate(self, bucket_number):
        token_path = os.path.join(self.token_dir, f"bucket_{bucket_number}.json")
        creds = self._load_credentials(token_path)
        
        if not creds or not creds.valid:
            creds = self._refresh_or_authenticate(creds, token_path)
        
        if creds:
            return build("drive", "v3", credentials=creds)
        return None
    
    def _load_credentials(self, token_path):
        if os.path.exists(token_path):
            try:
                return Credentials.from_authorized_user_file(token_path)
            except json.JSONDecodeError:
                print(f"Warning: Token file {token_path} is corrupted. Re-authenticating.")
        return None
    
    def _refresh_or_authenticate(self, creds, token_path):
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_credentials(token_path, creds)
                return creds
            except Exception as e:
                print(f"Error refreshing token: {e}. Re-authenticating.")
        
        return self._authenticate_new(token_path)
    
    def _authenticate_new(self, token_path):
        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
        creds = flow.run_local_server(port=0)
        self._save_credentials(token_path, creds)
        return creds
    
    def _save_credentials(self, token_path, creds):
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
    
    def check_storage(self):
        """Checks total and used storage in Google Drive."""
        service = self.authenticate(1)  # Automatically authenticate with first available bucket
        try:
            res = service.about().get(fields='storageQuota').execute()
            return int(res['storageQuota']['limit']), int(res['storageQuota']['usage'])
        except Exception as e:
            print(f"Error checking storage: {e}")
            return 0, 0

