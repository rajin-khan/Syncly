import os
import json
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Google Drive credentials and scope
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Authenticate Google Drive
def authenticate_google_drive():
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

# Download a file from Google Drive and save it locally
def download_from_drive(drive, file_id, save_path):
    request = drive.files().get_media(fileId=file_id)
    chunk_stream = io.BytesIO()
    downloader = MediaIoBaseDownload(chunk_stream, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    # Save the downloaded file
    with open(save_path, "wb") as f:
        f.write(chunk_stream.getvalue())

# Define output file path in the same directory as the script
output_file = os.path.join(os.path.dirname(__file__), "Real-Madrid.gif")

# Authenticate and download file
drive = authenticate_google_drive()
download_from_drive(drive, '1lxAKErBuCEgn52omwTK-4uzMij-xetXK', output_file)

print(f"File downloaded successfully: {output_file}")
