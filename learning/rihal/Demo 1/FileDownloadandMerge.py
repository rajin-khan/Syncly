import os
import json
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

#Google Drive credentials and scope
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "service_credentials.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

#Authenticate Google Drive
def authenticate_google_drive():
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

#Download a file from Google Drive and return its content
def download_from_drive(drive, file_id):
    request = drive.files().get_media(fileId=file_id)
    chunk_stream = io.BytesIO()
    downloader = MediaIoBaseDownload(chunk_stream, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return chunk_stream.getvalue()

#Merge multiple files into one
def merge_files(output_file_path, metadata_file):
    if not os.path.exists(metadata_file):
        print("Metadata file not found!")
        return
    
    with open(metadata_file, "r") as meta_file:
        chunk_ids = json.load(meta_file)
    
    drive = authenticate_google_drive()
    
    with open(output_file_path, "wb") as output_file:
        for file_id in chunk_ids:
            print(f"Downloading chunk: {file_id}")
            chunk_data = download_from_drive(drive, file_id)
            output_file.write(chunk_data)
    
    print(f"Files merged successfully into {output_file_path}")

#Define output file path in the same directory as the script
output_file = os.path.join(os.path.dirname(__file__), "Real-Madrid.gif")
metadata_file = os.path.join(os.path.dirname(__file__), "mis-stickers.gif.metadata.json")
folder_id = ["13QsCiHzjSm26gKPiomrtJaSpBcHFlZzF", "1Asi8ynnuI4CtH21mPFoVZAl-Oqlna1-F", "1m-cqxt7jrGOQ9dYoX65d7PqcnG1sBZlB"]

import os

#If Metadata file is not found
if not os.path.exists(metadata_file):
    print(f"Error: Metadata file not found at {metadata_file}")


#Authenticate and merge files
drive = authenticate_google_drive()
merge_files(output_file, metadata_file)
