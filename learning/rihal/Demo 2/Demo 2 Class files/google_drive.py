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

class GoogleDrive:
    def __init__(self, token_dir="tokens", credentials_file="credentials.json"):
        self.token_dir = token_dir
        self.credentials_file = credentials_file
        self.scopes = ['https://www.googleapis.com/auth/drive']
        self.service = None  # Store the authenticated service instance
        os.makedirs(self.token_dir, exist_ok=True)

    def authenticate(self, bucket_number):
        token_path = os.path.join(self.token_dir, f"bucket_{bucket_number}.json")
        print(f"Token path: {token_path}")  # Debug: Print the token file path

        if os.path.exists(token_path):
            print(f"Token file found for bucket {bucket_number}.")  # Debug: Token file exists
            try:
                creds = Credentials.from_authorized_user_file(token_path, self.scopes)
                if creds.valid:
                    print(f"Credentials are valid for bucket {bucket_number}.")  # Debug: Credentials are valid
                    self.service = build("drive", "v3", credentials=creds)
                    return self.service  # Return the service object
                else:
                    print(f"Invalid credentials for bucket {bucket_number}.")  # Debug: Credentials are invalid
            except Exception as e:
                print(f"Error loading credentials for bucket {bucket_number}: {e}")  # Debug: Error loading credentials
        else:
            print(f"No token found for bucket {bucket_number}. Starting OAuth flow...")  # Debug: No token file

        # Start OAuth flow
        try:
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.scopes)
            creds = flow.run_local_server(port=0)
            print("OAuth flow completed successfully.")  # Debug: OAuth flow completed
        except Exception as e:
            print(f"Error during OAuth flow for bucket {bucket_number}: {e}")  # Debug: Error during OAuth flow
            return None

        # Save the token file
        try:
            with open(token_path, "w") as token_file:
                token_file.write(creds.to_json())
            print(f"Token file saved successfully for bucket {bucket_number}.")  # Debug: Token file saved
        except Exception as e:
            print(f"Error saving token file for bucket {bucket_number}: {e}")  # Debug: Error saving token file
            return None

        # Build the service
        try:
            self.service = build("drive", "v3", credentials=creds)
            print(f"Service created successfully for bucket {bucket_number}.")  # Debug: Service created
            return self.service  # Return the service object
        except Exception as e:
            print(f"Error creating service for bucket {bucket_number}: {e}")  # Debug: Error creating service
            return None
    
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
            print(f"Storage limit: {limit} bytes, Usage: {usage} bytes")  # Debug: Print storage details
            return limit, usage
        except Exception as e:
            print(f"Error checking storage: {e}")
            return 0, 0
