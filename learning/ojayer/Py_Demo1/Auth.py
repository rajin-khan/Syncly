import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload


# Google Drive credentials and scope
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Authenticate Google Drive
def authenticate_google_drive():
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

# Upload a File to Google Drive
def upload_to_drive(drive, filename, folder_id):
    file_metadata = {"name": filename, "parents": [folder_id] if folder_id else None}
    with open(filename, "rb") as file:
        media = MediaIoBaseUpload(file, mimetype="application/octet-stream")
        uploaded_file = drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
    
    return uploaded_file.get("id")


# Example of how to use the above functions

# Authenticate Google Drive
drive = authenticate_google_drive()

# File path
file_path = "csv_result-Rice_Cammeo_Osmancik new.csv"

# Chunk size 10kb
chunk_size = 1024*32

# Folder ID
folder_id = "13QsCiHzjSm26gKPiomrtJaSpBcHFlZzF"

# upload file
upload_id = upload_to_drive(drive, file_path, folder_id)

print(f"Uploaded file with ID: {upload_id}")