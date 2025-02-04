import os
import json
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


# Google Drive credentials and scope
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Authenticate Google Drive
def authenticate_google_drive():
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

# Upload a chunk to Google Drive
def upload_to_drive(drive, chunk, chunk_filename, folder_id):
    file_metadata = {"name": chunk_filename, "parents": [folder_id] if folder_id else None}
    media = MediaIoBaseUpload(io.BytesIO(chunk), mimetype="application/octet-stream")
    file = drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return file.get("id")


# Split and upload file
def split_file(file_path, chunk_size, folder_id):
    drive = authenticate_google_drive()
    chunk_ids = []
    
    with open(file_path, "rb") as file:
        chunk_index = 0
        while chunk := file.read(chunk_size):
            chunk_filename = f"{os.path.basename(file_path)}.part{chunk_index}"
            file_id = upload_to_drive(drive, chunk, chunk_filename, folder_id[0])
            print(f"Uploaded chunk {chunk_index} with file ID: {file_id}")
            chunk_ids.append(file_id)
            chunk_index += 1
    
    with open(f"{file_path}.metadata.json", "w") as meta_file:
        json.dump(chunk_ids, meta_file)
    print(f"File split and uploaded in {chunk_index} chunks.")


# File path and chunk size
file_path = "csv_result-Rice_Cammeo_Osmancik new.csv"
chunk_size = 1024 * 10  # 10 KB
folder_id = ["13QsCiHzjSm26gKPiomrtJaSpBcHFlZzF", "1Asi8ynnuI4CtH21mPFoVZAl-Oqlna1-F", "1m-cqxt7jrGOQ9dYoX65d7PqcnG1sBZlB"]

# Uncomment to split and upload
split_file(file_path, chunk_size, folder_id)
