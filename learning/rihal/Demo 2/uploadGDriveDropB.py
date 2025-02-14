import os
import json
import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
from google.auth.transport.requests import Request

#Load environment variables
load_dotenv()

#Configuration
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)

#Google Drive API scope
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive']

class CloudService:
    def __init__(self, bucket_id):
        self.bucket_id = bucket_id
        self.token_path = os.path.join(TOKEN_DIR, f"bucket_{bucket_id}.json")
        self.client = None

    def authenticate(self):
        raise NotImplementedError

    def check_storage(self):
        raise NotImplementedError

    def list_files(self, max_results=None, query=None):
        raise NotImplementedError

    def get_file_url(self, file_id):
        raise NotImplementedError

class GoogleDriveService(CloudService):
    def authenticate(self):
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, GOOGLE_SCOPES)
            if not creds.valid:
                creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, GOOGLE_SCOPES)
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

class DropboxService(CloudService):
    def authenticate(self):
        if os.path.exists(self.token_path):
            with open(self.token_path, 'r') as f:
                access_token = f.read().strip()
            self.client = dropbox.Dropbox(access_token)
            try:
                self.client.users_get_current_account()
            except dropbox.exceptions.AuthError:
                self._full_auth()
        else:
            self._full_auth()

    def _full_auth(self):
        app_key = os.getenv("DROPBOX_APP_KEY")
        app_secret = os.getenv("DROPBOX_APP_SECRET")
        auth_flow = DropboxOAuth2FlowNoRedirect(app_key, app_secret, token_access_type='offline')

        print("Authorize this app:", auth_flow.start())
        auth_code = input("Enter auth code: ").strip()
        result = auth_flow.finish(auth_code)
        
        with open(self.token_path, 'w') as f:
            f.write(result.access_token)
        self.client = dropbox.Dropbox(result.access_token)

    def check_storage(self):
        try:
            usage = self.client.users_get_space_usage()
            return usage.allocation.get_individual().allocated, usage.used
        except Exception as e:
            print(f"Dropbox storage error: {e}")
            return 0, 0

    def list_files(self, max_results=None, query=None):
        files = []
        result = self.client.files_list_folder(path="", recursive=True)
        
        while True:
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    files.append({
                        'id': entry.id,
                        'name': entry.name,
                        'size': entry.size,
                        'path': entry.path_display
                    })
            if not result.has_more or (max_results and len(files) >= max_results):
                break
            result = self.client.files_list_folder_continue(result.cursor)
        return files[:max_results] if max_results else files

    def get_file_url(self, file_path):
        try:
            return self.client.sharing_create_shared_link(file_path).url
        except:
            return f"https://www.dropbox.com/home{file_path}"

#Metadata management
def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    return {'buckets': []}

def save_metadata(metadata):
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f)

#Storage operations
def check_all_storage():
    metadata = load_metadata()
    total_limit = 0
    total_usage = 0

    for bucket in metadata['buckets']:
        try:
            if bucket['service'] == 'google':
                service = GoogleDriveService(bucket['id'])
            elif bucket['service'] == 'dropbox':
                service = DropboxService(bucket['id'])
            else:
                continue
                
            service.authenticate()
            limit, usage = service.check_storage()
            total_limit += limit
            total_usage += usage
        except Exception as e:
            print(f"Error checking {bucket['service']} bucket {bucket['id']}: {e}")

    print(f"Total Storage: {total_limit / 1e9:.2f} GB")
    print(f"Total Used: {total_usage / 1e9:.2f} GB")
    print(f"Available: {(total_limit - total_usage) / 1e9:.2f} GB")

def list_files_from_all_buckets(query=None, max_files=100):
    metadata = load_metadata()
    all_files = []

    for bucket in metadata['buckets']:
        try:
            if bucket['service'] == 'google':
                service = GoogleDriveService(bucket['id'])
            elif bucket['service'] == 'dropbox':
                service = DropboxService(bucket['id'])
            else:
                continue
                
            service.authenticate()
            files = service.list_files(max_files, query)
            
            for file in files:
                all_files.append({
                    'name': file['name'],
                    'size': file.get('size', 0),
                    'url': service.get_file_url(file.get('id', file.get('path', ''))),
                    'service': bucket['service']
                })
        except Exception as e:
            print(f"Error listing files from {bucket['service']} bucket {bucket['id']}: {e}")

    #Display logic remains similar to original with pagination
    #(Omitted for brevity, use similar pagination code from original)

def add_bucket():
    metadata = load_metadata()
    service_choice = input("Choose service:\n1. Google Drive\n2. Dropbox\n> ")
    
    if service_choice not in ['1', '2']:
        print("Invalid choice")
        return

    bucket_id = str(len(metadata['buckets']) + 1)
    service = GoogleDriveService(bucket_id) if service_choice == '1' else DropboxService(bucket_id)
    
    try:
        service.authenticate()
        metadata['buckets'].append({
            'id': bucket_id,
            'service': 'google' if service_choice == '1' else 'dropbox',
            'token_path': service.token_path
        })
        save_metadata(metadata)
        print(f"Added {service.__class__.__name__} bucket {bucket_id}")
    except Exception as e:
        print(f"Authentication failed: {e}")

#Main execution
if __name__ == "__main__":
    while True:
        print("\n1. Add storage bucket")
        print("2. Check storage")
        print("3. List files")
        print("4. Exit")
        choice = input("Enter choice: ")

        if choice == '1':
            add_bucket()
        elif choice == '2':
            check_all_storage()
        elif choice == '3':
            query = input("Enter search query (optional): ")
            list_files_from_all_buckets(query=query if query else None)
        elif choice == '4':
            break
        else:
            print("Invalid choice")
