import os
import json
from dotenv import load_dotenv
from google.auth.transport.requests import Request

#Load environment variables
load_dotenv()

#Configuration
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)

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

#Import service implementations after base class definition
from google_drive_service import GoogleDriveService
from dropbox_service import DropboxService

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

#Main execution
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

                    destination = input(f"Enter destination path (default: ./{file_name}): ").strip()
                    if not destination:
                        destination = os.path.join(os.getcwd(), file_name)
                    else:
                        if os.path.isdir(destination):
                            destination = os.path.join(destination, file_name)
                        else:
                            os.makedirs(os.path.dirname(destination), exist_ok=True)

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
