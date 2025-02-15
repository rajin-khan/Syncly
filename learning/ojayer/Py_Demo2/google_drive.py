import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from drive import drive

class googleDrive(drive):
    def __init__(self, token_dir = "tokens", credentials_file="credentials.json"):
        self.token_dir = token_dir
        self.credentials_file = credentials_file
        self.scopes = ['https://www.googleapis.com/auth/drive']
        os.makedirs(self.token_dir, exist_ok=True)

    
    def authenticate(self,bucket_number):
        token_path = os.path.join(self.token_dir, f"bucket_{bucket_number}.json")
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, self.scopes)
            if creds.valid:
                return build("drive", "v3", credentials=creds)
        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.scopes)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        return build("drive", "v3", credentials=creds)
    
    def list_drive_files(service, max_results=None, query=None):
        all_files = []
        page_token = None
        query_filter = f"name contains '{query}'" if query else None
        while True:
            results = service.files().list(
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
    
    def check_storage(self,bucket):
        if not self.service:
            raise ValueError("Service not authenticated. Call authenticate() first.")
        
        try:
            res = self.about().get(fields='storageQuota').execute()
            limit = int(res['storageQuota']['limit'])
            usage = int(res['storageQuota']['usage'])
            return limit, usage
        except Exception as e:
            print(f"Error for {bucket}: {e}")
            return 0, 0