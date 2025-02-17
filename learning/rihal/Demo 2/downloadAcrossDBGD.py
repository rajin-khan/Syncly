import os
import json
import io
import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
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

#Google Drive API scope (read-only)
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

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

    def download_file(self, file_id, destination_path):
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

    def download_file(self, file_id, destination_path):
        try:
            #Ensure directory exists
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
        auth_flow = DropboxOAuth2FlowNoRedirect(
            app_key, app_secret,
            token_access_type='offline',
            scope=['files.content.read']
        )
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

    def download_file(self, file_path, destination_path):
        try:
            #Ensure directory exists
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            self.client.files_download_to_file(destination_path, file_path)
            print(f"File downloaded to {destination_path}")
        except Exception as e:
            print(f"Failed to download file: {e}")
            raise

#Metadata management (unchanged)
def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    return {'buckets': []}

def save_metadata(metadata):
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f)

#Storage operations (unchanged except list_files_from_all_buckets)
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
                service_type = bucket['service']
                identifier = file['id'] if service_type == 'google' else file['path']
                all_files.append({
                    'name': file['name'],
                    'size': file.get('size', 0),
                    'url': service.get_file_url(identifier),
                    'service': service_type,
                    'bucket_id': bucket['id'],
                    'identifier': identifier
                })
        except Exception as e:
            print(f"Error listing files from {bucket['service']} bucket {bucket['id']}: {e}")
    return all_files[:max_files] if max_files else all_files

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

#Main execution (updated)
if __name__ == "__main__":
    while True:
        print("\n1. Add storage bucket")
        print("2. Check storage")
        print("3. List and download files")
        print("4. Exit")
        choice = input("Enter choice: ")
        if choice == '1':
            add_bucket()
        elif choice == '2':
            check_all_storage()
        elif choice == '3':
            query = input("Enter search query (optional): ")
            files = list_files_from_all_buckets(query=query.strip() if query else None)
            if not files:
                print("No files found.")
                continue
            print("\nFound files:")
            for idx, file in enumerate(files):
                print(f"{idx + 1}. {file['name']} ({file['service']}) - {file['size']} bytes")
            download_choice = input("\nEnter file number to download (or press Enter to cancel): ").strip()
            if download_choice:
                try:
                    index = int(download_choice) - 1
                    if index < 0 or index >= len(files):
                        print("Invalid file number.")
                        continue
                    selected_file = files[index]
                    service_type = selected_file['service']
                    bucket_id = selected_file['bucket_id']
                    identifier = selected_file['identifier']
                    file_name = selected_file['name']

                    #Get destination path
                    destination = input(f"Enter destination path (default: ./{file_name}): ").strip()
                    if not destination:
                        destination = os.path.join(os.getcwd(), file_name)
                    else:
                        if os.path.isdir(destination):
                            destination = os.path.join(destination, file_name)
                        else:
                            os.makedirs(os.path.dirname(destination), exist_ok=True)

                    #Initialize service
                    if service_type == 'google':
                        service = GoogleDriveService(bucket_id)
                    else:
                        service = DropboxService(bucket_id)
                    service.authenticate()
                    service.download_file(identifier, destination)
                    print(f"Successfully downloaded to {destination}")
                except ValueError:
                    print("Invalid input: please enter a valid number.")
                except Exception as e:
                    print(f"Error during download: {str(e)}")
        elif choice == '4':
            break
        else:
            print("Invalid choice")
