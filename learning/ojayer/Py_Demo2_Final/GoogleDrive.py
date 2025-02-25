import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from Service import Service
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

class GoogleDrive(Service):
    def __init__(self, token_dir="tokens", credentials_file="credentials.json"):
        self.token_dir = token_dir
        self.credentials_file = credentials_file
        self.scopes = ['https://www.googleapis.com/auth/drive']
        self.service = None         #Store the authenticated service instance
        os.makedirs(self.token_dir, exist_ok=True)

    def authenticate(self, bucket_number):
        """
        Authenticate with Google Drive using OAuth 2.0.

        Args:
            bucket_number (int): The bucket number associated with this Google Drive instance.

        Returns:
            googleapiclient.discovery.Resource: Authenticated Google Drive service instance.
        """
        token_path = os.path.join(self.token_dir, f"bucket_{bucket_number}.json")

        creds = None
        if os.path.exists(token_path):
            try:
                # Load the token file
                with open(token_path, "r") as token_file:
                    token_data = json.load(token_file)

                # Ensure required fields exist
                required_fields = {"client_id", "client_secret", "refresh_token", "token"}
                if all(field in token_data for field in required_fields):
                    creds = Credentials.from_authorized_user_file(token_path)
                else:
                    print(f" Warning: Token file {token_path} is missing required fields. Re-authenticating.")
                    creds = None  # Force re-authentication

            except json.JSONDecodeError:
                print(f"Warning: Token file {token_path} is corrupted. Re-authenticating.")
                creds = None  # Force re-authentication

        # If no valid credentials, start OAuth 2.0 authentication
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    print("🔄 Refreshing expired token...")
                    creds.refresh(Request())
                except Exception as e:
                    print(f" Error refreshing token: {e}. Re-authenticating.")
                    creds = None  # Force re-authentication

            if not creds:
                # OAuth authentication flow
                print(" Starting Google Drive authentication...")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)

                # Save new credentials to the token file
                with open(token_path, "w") as token_file:
                    token_file.write(creds.to_json())

                print(f"Authentication successful. Token saved to {token_path}.")

        # Build the Google Drive service
        self.service = build("drive", "v3", credentials=creds)
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
        """Check the storage quota for the authenticated Google Drive account."""
        if not self.service:
            print("Service not authenticated. Call authenticate() first.")
            return 0, 0
        
        try:
            res = self.service.about().get(fields='storageQuota').execute()
            limit = int(res['storageQuota']['limit'])
            usage = int(res['storageQuota']['usage'])
            return limit, usage
        except Exception as e:
            print(f"Error checking storage: {e}")
            return 0, 0