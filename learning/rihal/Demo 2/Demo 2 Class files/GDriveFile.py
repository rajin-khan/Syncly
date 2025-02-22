import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
import re
from FileHandler import FileHandler
from google_drive import GoogleDrive
from DriveManager import DriveManager

# Load environment variables
load_dotenv()

# API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

# Get paths from environment
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)

# List of common file extensions to check
COMMON_EXTENSIONS = ['.jpg', '.pdf', '.png', '.txt', '.csv', '.docx', '.xlsx']

class GoogleDriveFile(FileHandler):
    def __init__(self, drive_manager: DriveManager):
        self.drive_manager = drive_manager
        self.google_drive = GoogleDrive()

    def upload_chunk(self, chunk_str:str, mimetype:str, file_name:str, chunk_index:str):
        pass
    
    def upload_file(self, file_path:str,file_name:str,mimetype:str):
        pass

    def split_and_upload_file(self, file_path: str, file_name: str, mimetype: str, file_size: str, free_space: str, metadata: str):
        pass

    def update_metadata(self, metadata: str):
        """Update metadata for a file."""
        # Implementation for updating metadata in Google Drive
        pass

    def download_file(self, file_id: str, save_path: str):
        """Download a file from Google Drive."""
        service = self.google_drive.authenticate(1)  # Authenticate with bucket number 1
        try:
            request = service.files().get_media(fileId=file_id)
            file_metadata = service.files().get(fileId=file_id, fields="name").execute()
            file_name = file_metadata.get("name")  # Preserve the original file name with extension
            save_file_path = os.path.join(save_path, file_name)
            
            # Download the file
            with open(save_file_path, "wb") as file:
                downloader = MediaIoBaseDownload(file, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    print(f"Downloading... {int(status.progress() * 100)}% completed")
            
            print(f"Download complete: {save_file_path}")
            return save_file_path
        except Exception as e:
            print(f"Error downloading file: {e}")
            return None

    def search_file(self):
        """Search for files in Google Drive."""
        query = input("Enter search keyword: ").strip()
        if query:
            self.drive_manager.list_files_from_all_buckets(query=query)

    def merge_chunks(self, file_paths: str, merged_file_path: str):
        """Merge file chunks into a single file."""
        with open(merged_file_path, "wb") as merged_file:
            for chunk_path in file_paths:
                with open(chunk_path, "rb") as chunk:
                    merged_file.write(chunk.read())
        print(f"Merged file saved at: {merged_file_path}")

    def download_and_merge_chunks(self, service, file_name: str, save_path: str = "downloads"):
        """Download and merge file chunks into a single file."""
        os.makedirs(save_path, exist_ok=True)

        # Check if the full file exists first
        query = f"name contains '{file_name}' and not name contains '.part'"
        result = service.files().list(q=query, fields="files(id, name)").execute()
        files = result.get("files", [])
        
        if files:
            file_id = files[0]["id"]
            print("File found, downloading directly.")
            return self.download_file(service, file_id, save_path)
        
        # If full file not found, check for chunks
        query = f"name contains '{file_name}.part'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        chunk_files = results.get("files", [])
        if not chunk_files:
            print(f"File not found in this bucket.")
            print(f"\nChecking another bucket...")
            return None
        
        # Sort chunks numerically by part number
        chunk_files.sort(key=lambda x: int(re.search(r'\.part(\d+)$', x['name']).group(1)))
        
        # Extract original filename with extension from first chunk
        original_filename = re.sub(r'\.part\d+$', '', chunk_files[0]['name'])
        merged_file_path = os.path.join(save_path, original_filename)  # Use extracted name
        
        chunk_paths = []
        for file in chunk_files:
            file_id = file['id']
            chunk_path = self.download_file(service, file_id, save_path)
            if chunk_path:
                chunk_paths.append(chunk_path)
        
        # Merge chunks and save with original extension
        self.merge_chunks(chunk_paths, merged_file_path)
        
        # Clean up chunk files
        for chunk_path in chunk_paths:
            os.remove(chunk_path)
        
        return merged_file_path

    """def download_from_all_buckets(self, file_name: str, save_path: str = "downloads"):
        #Download a file from all buckets.
        # Remove quotation marks from the save path (if any)
        save_path = save_path.strip('"').strip("'")
        
        # Create the save directory if it doesn't exist
        os.makedirs(save_path, exist_ok=True)
        
        bucket_numbers = self.drive_manager.get_all_authenticated_buckets()
        if not bucket_numbers:
            print("No authenticated buckets found. Please add a new bucket first.")
            return
        
        # Check if the full file exists in any bucket
        for bucket in bucket_numbers:
            try:
                service = self.google_drive.authenticate(int(bucket))
                result = self.download_and_merge_chunks(service, file_name, save_path)
                if result:
                    return result
            except Exception as e:
                print(f"Error downloading from bucket {bucket}: {e}")
        
        # If the exact file name is not found, try with common extensions
        for ext in COMMON_EXTENSIONS:
            full_file_name = f"{file_name}{ext}"
            for bucket in bucket_numbers:
                try:
                    service = self.google_drive.authenticate(int(bucket))
                    result = self.download_and_merge_chunks(service, full_file_name, save_path)
                    if result:
                        return result
                except Exception as e:
                    print(f"Error downloading from bucket {bucket}: {e}")
        
        print("File not found in any bucket.")"""
    
    def download_from_all_buckets(self, file_name: str, save_path: str = "downloads"):
        """Download a file from all buckets."""
        # Remove quotation marks from the save path (if any)
        save_path = save_path.strip('"').strip("'")
        
        # Create the save directory if it doesn't exist
        os.makedirs(save_path, exist_ok=True)
        
        bucket_numbers = self.drive_manager.get_all_authenticated_buckets()
        print(f"Authenticated Buckets: {bucket_numbers}")  # Debugging

        if not bucket_numbers:
            print("No authenticated buckets found. Please add a new bucket first.")
            return
        
        # Check if the full file exists in any bucket
        for bucket in bucket_numbers:
            try:
                print(f"Authenticating bucket {bucket}...")     #Debugging
                service = self.google_drive.authenticate(int(bucket))
                if service is None:
                    print(f"Failed to authenticate bucket {bucket}.")
                    continue
                
                print(f"Service object for bucket {bucket}: {service}")  # Debug: Verify the service object
                result = self.download_and_merge_chunks(service, file_name, save_path)
                if result:
                    return result
            except Exception as e:
                print(f"Error downloading from bucket {bucket}: {e}")
        
        # If the exact file name is not found, try with common extensions
        for ext in COMMON_EXTENSIONS:
            full_file_name = f"{file_name}{ext}"
            for bucket in bucket_numbers:
                try:
                    print(f"Authenticating bucket {bucket} for file {full_file_name}...")
                    service = self.google_drive.authenticate(int(bucket))
                    if service is None:
                        print(f"Failed to authenticate bucket {bucket}.")
                        continue
                    
                    print(f"Service object for bucket {bucket}: {service}")  # Debug: Verify the service object
                    result = self.download_and_merge_chunks(service, full_file_name, save_path)
                    if result:
                        return result
                except Exception as e:
                    print(f"Error downloading from bucket {bucket}: {e}")
        
        print("File not found in any bucket.")
