import os
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from main import CloudService

GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class GoogleDriveService(CloudService):
    def authenticate(self):
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, GOOGLE_SCOPES)
            if not creds.valid:
                creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.getenv("CREDENTIALS_FILE", "credentials.json"), GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
            with open(self.token_path, "w") as token_file:
                token_file.write(creds.to_json())
        self.client = build("drive", "v3", credentials=creds)

    def check_storage(self):
        try:
            res = self.client.about().get(fields='storageQuota').execute()
            return int(res['storageQuota']['limit']), int(res['storageQuota']['usage'])
        except Exception as e:
            print(f"Google Drive storage error: {e}")
            return 0, 0

    def list_files(self, max_results=None, query=None):
        files = []
        page_token = None
        query_str = f"name contains '{query}'" if query else ""

        while True:
            response = self.client.files().list(
                q=query_str,
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token
            ).execute()
            files.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            if not page_token or (max_results and len(files) >= max_results):
                break
        return files[:max_results] if max_results else files

    def get_file_url(self, file_id):
        return f"https://drive.google.com/file/d/{file_id}/view"

    def download_file(self, file_id, destination_path):
        try:
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            request = self.client.files().get_media(fileId=file_id)
            with io.FileIO(destination_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    print(f"Downloaded {int(status.progress() * 100)}%.")
            print(f"File downloaded to {destination_path}")
        except Exception as e:
            print(f"Failed to download file: {e}")
            raise
        