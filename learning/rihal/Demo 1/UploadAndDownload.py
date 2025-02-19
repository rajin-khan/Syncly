import os
import json
import io
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# Load env variables
load_dotenv()

# API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

# Get paths from env
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")  # Default to "tokens" if not set
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")  # Default to "credentials.json" if not set
SERVICE_CREDENTIALS_FILE = os.getenv("SERVICE_CREDENTIALS_FILE", "service_credentials.json")

# Authenticate Google Drive (OAuth for upload, Service Account for download)
def authenticate_google_drive(service_account=False):
    if service_account:
        creds = ServiceCredentials.from_service_account_file(SERVICE_CREDENTIALS_FILE, scopes=SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
    return build("drive", "v3", credentials=creds)

# Get all authenticated buckets from the JSON file
def get_all_authenticated_buckets():
    return [f.replace(".json", "").replace("bucket_", "") for f in os.listdir(TOKEN_DIR) if f.startswith("bucket_")]

# Check storage per bucket
def check_storage(service):
    try:
        res = service.about().get(fields='storageQuota').execute()
        return int(res['storageQuota']['limit']), int(res['storageQuota']['usage'])
    except Exception as e:
        print(f"Error checking storage: {e}")
        return 0, 0

# Split large files into chunks
def split_file(file_path, chunk_size):
    file_size = os.path.getsize(file_path)
    chunk_paths = []
    with open(file_path, "rb") as file:
        for i in range(0, file_size, chunk_size):
            chunk_filename = f"{file_path}.part{i}"
            with open(chunk_filename, "wb") as chunk_file:
                chunk_file.write(file.read(chunk_size))
            chunk_paths.append(chunk_filename)
    return chunk_paths

# Upload file to Google Drive
def upload_file(file_path, file_name, mimetype):
    file_size = os.path.getsize(file_path)
    buckets = get_all_authenticated_buckets()
    free_space = [(check_storage(authenticate_google_drive(bucket))[0] - check_storage(authenticate_google_drive(bucket))[1], bucket) for bucket in buckets]
    free_space.sort(reverse=True, key=lambda x: x[0])
    
    remaining_size = file_size
    metadata = []
    
    while remaining_size > 0:
        largest_free, best_bucket = free_space[0]
        service = authenticate_google_drive(best_bucket)
        
        if largest_free >= remaining_size:
            media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
            file_metadata = {'name': file_name}
            file = service.files().create(media_body=media, body=file_metadata).execute()
            metadata.append(file['id'])
            break
        
        chunk_size = min(largest_free, remaining_size)
        chunk_paths = split_file(file_path, chunk_size)
        for chunk_path in chunk_paths:
            media = MediaFileUpload(chunk_path, mimetype=mimetype, resumable=True)
            file_metadata = {'name': f'{file_name}_part'}
            file = service.files().create(media_body=media, body=file_metadata).execute()
            metadata.append(file['id'])
            remaining_size -= os.path.getsize(chunk_path)

    with open(f"{file_path}.metadata.json", "w") as meta_file:
        json.dump(metadata, meta_file)
    print("Upload complete!")

# Download a file from Google Drive
def download_from_drive(drive, file_id):
    request = drive.files().get_media(fileId=file_id)
    chunk_stream = io.BytesIO()
    downloader = MediaIoBaseDownload(chunk_stream, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return chunk_stream.getvalue()

# Merge multiple chunks into one file
def merge_files(output_file_path, metadata_file):
    if not os.path.exists(metadata_file):
        print("Metadata file not found!")
        return
    
    with open(metadata_file, "r") as meta_file:
        chunk_ids = json.load(meta_file)
    
    drive = authenticate_google_drive(service_account=True)
    
    with open(output_file_path, "wb") as output_file:
        for file_id in chunk_ids:
            print(f"Downloading chunk: {file_id}")
            chunk_data = download_from_drive(drive, file_id)
            output_file.write(chunk_data)
    
    print(f"Files merged successfully into {output_file_path}")

# Example Usage
if __name__ == "__main__":
    action = input("Enter 'upload' to upload a file or 'download' to merge a file: ").strip().lower()
    if action == 'upload':
        file_path = input("Enter file path: ").strip()
        upload_file(file_path, file_name=os.path.basename(file_path), mimetype="application/octet-stream")
    elif action == 'download':
        metadata_file = input("Enter metadata file path: ").strip()
        output_file = input("Enter output file name: ").strip()
        merge_files(output_file, metadata_file)
    else:
        print("Invalid action.")
