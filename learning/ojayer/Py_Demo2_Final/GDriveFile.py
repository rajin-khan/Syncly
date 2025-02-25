import json
import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
import re
from FileHandler import FileHandler
from GoogleDrive import GoogleDrive
from DriveManager import DriveManager

#Load environment variables
load_dotenv()

#API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

#Get paths from environment
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)

#List of common file extensions to check
COMMON_EXTENSIONS = ['.jpg', '.pdf', '.png', '.txt', '.csv', '.docx', '.xlsx', '.java', '.py']

class GoogleDriveFile(FileHandler):
    def __init__(self, drive_manager: DriveManager):
        self.drive_manager = drive_manager
        self.google_drive = GoogleDrive()

    def upload_file(self, file_path: str, file_name: str, mimetype: str):
        """
        Upload a file to Google Drive. If the file is larger than the available space in a single bucket,
        it will be split into chunks and uploaded across multiple buckets.
        """
        #Get file size
        file_size = os.path.getsize(file_path)
        
        #Get all authenticated buckets
        buckets = self.drive_manager.get_all_authenticated_buckets()
        if not buckets:
            print("No authenticated buckets found. Please add a new bucket first.")
            return
        
        #Calculate free space in each bucket
        free_space = []
        total_free = 0
        for bucket in buckets:
            service = self.google_drive.authenticate(int(bucket))
            if service is None:
                print(f"Failed to authenticate bucket {bucket}.")
                continue
            
            limit, usage = self.google_drive.check_storage()
            free = limit - usage
            total_free += free
            if free > 0:
                free_space.append([free, bucket])
        
        #Check if there is enough total free space
        if total_free < file_size:
            print("Not enough space across all buckets.")
            return
        
        #Sort buckets by free space (descending)
        free_space.sort(reverse=True, key=lambda x: x[0])
        
        #Metadata to track uploaded chunks
        metadata = {"file_name": file_name, "chunks": []}
        
        #Upload the file
        if free_space[0][0] >= file_size:
            #Upload the entire file to the best bucket
            best_bucket = free_space[0][1]
            service = self.google_drive.authenticate(int(best_bucket))
            if service is None:
                print(f"Failed to authenticate bucket {best_bucket}.")
                return
            
            media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
            file_metadata = {'name': file_name}
            result = service.files().create(media_body=media, body=file_metadata).execute()
            file_id = result.get("id")
            metadata["chunks"].append({
                "chunk_name": file_name,
                "file_id": file_id,
                "bucket": best_bucket
            })
        else:
            #Split the file into chunks and upload to multiple buckets
            offset = 0
            chunk_index = 0
            with open(file_path, "rb") as file:
                while offset < file_size:
                    #Sort buckets by free space (descending)
                    free_space.sort(reverse=True, key=lambda x: x[0])
                    
                    #Find a bucket with enough space
                    selected_bucket = None
                    for i, (bucket_free, bucket_id) in enumerate(free_space):
                        if bucket_free > 0:
                            selected_bucket = bucket_id
                            selected_index = i
                            break
                    
                    if not selected_bucket:
                        print("No available buckets with free space.")
                        break
                    
                    #Calculate chunk size
                    chunk_size = min(free_space[selected_index][0], file_size - offset)
                    chunk_filename = f"{file_path}.part{chunk_index}"
                    
                    #Write the chunk to a temporary file
                    with open(chunk_filename, "wb") as chunk_file:
                        chunk_file.write(file.read(chunk_size))
                    
                    #Upload the chunk
                    file_id = None
                    uploaded = False
                    while not uploaded:
                        service = self.google_drive.authenticate(int(selected_bucket))
                        if service is None:
                            print(f"Failed to authenticate bucket {selected_bucket}.")
                            break
                        
                        try:
                            file_id = self.upload_chunk(service, chunk_filename, mimetype, file_name, chunk_index)
                            uploaded = True
                        except HttpError as e:
                            if "storageQuotaExceeded" in str(e):
                                print(f"Bucket {selected_bucket} is full. Trying next bucket.")
                                free_space[selected_index][0] = 0       #Mark bucket as full
                                break
                            else:
                                os.remove(chunk_filename)
                                raise e
                    
                    if file_id is None:
                        raise RuntimeError("Failed to upload chunk after retries")
                    
                    #Update metadata
                    metadata["chunks"].append({
                        "chunk_name": f"{file_name}_part{chunk_index + 1}",
                        "file_id": file_id,
                        "bucket": selected_bucket
                    })
                    
                    #Update remaining space and offset
                    free_space[selected_index][0] -= chunk_size
                    offset += chunk_size
                    chunk_index += 1
                    
                    #Clean up the temporary chunk file
                    os.remove(chunk_filename)
        
        #Update metadata file
        self.update_metadata(metadata)

    def split_and_upload_file(self,file_path:str, file_name:str, mimetype:str, file_size:str, free_space:str, metadata:str):
        pass

    def upload_chunk(self, service, chunk_filename: str, mimetype: str, file_name: str, chunk_index: int):
        """
        Upload a single chunk to Google Drive.
        """
        media = MediaFileUpload(chunk_filename, mimetype=mimetype, resumable=True)
        chunk_name = f"{file_name}_part{chunk_index + 1}"
        file_metadata = {'name': chunk_name}
        result = service.files().create(media_body=media, body=file_metadata).execute()
        return result.get("id")

    def update_metadata(self, metadata: dict):
        """
        Update the metadata file with the new upload information.
        """
        metadata_file = "metadata.json"
        if os.path.exists(metadata_file) and os.path.getsize(metadata_file) > 0:
            with open(metadata_file, 'r') as f:
                try:
                    existing_metadata = json.load(f)
                    if not isinstance(existing_metadata, list):
                        existing_metadata = [existing_metadata]
                except json.JSONDecodeError:
                    print("Warning: Metadata file is corrupted. Resetting metadata.")
                    existing_metadata = []
        else:
            existing_metadata = []
        
        existing_metadata.append(metadata)
        with open(metadata_file, 'w') as f:
            json.dump(existing_metadata, f, indent=4)
            print("Upload complete. Metadata updated.")
            
    def download_file(self, service, file_id: str, save_path: str):
        """Download a file from Google Drive."""
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

        #Check if the full file exists first
        query = f"name contains '{file_name}' and not name contains '.part'"
        result = service.files().list(q=query, fields="files(id, name)").execute()
        files = result.get("files", [])
        
        if files:
            file_id = files[0]["id"]
            print("File found, downloading directly.")
            return self.download_file(service, file_id, save_path)
        
        #If full file not found, check for chunks
        query = f"name contains '{file_name}.part'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        chunk_files = results.get("files", [])
        
        #Sort chunks numerically by part number
        chunk_files.sort(key=lambda x: int(re.search(r'\.part(\d+)$', x['name']).group(1)))
        
        #Extract original filename with extension from first chunk
        original_filename = re.sub(r'\.part\d+$', '', chunk_files[0]['name'])
        merged_file_path = os.path.join(save_path, original_filename)       #Use extracted name
        
        chunk_paths = []
        for file in chunk_files:
            file_id = file['id']
            chunk_path = self.download_file(service, file_id, save_path)
            if chunk_path:
                chunk_paths.append(chunk_path)
        
        #Merge chunks and save with original extension
        self.merge_chunks(chunk_paths, merged_file_path)
        
        #Clean up chunk files
        for chunk_path in chunk_paths:
            os.remove(chunk_path)
        
        return merged_file_path

    def download_from_all_buckets(self, file_name: str, save_path: str = "downloads"):
        """Download a file from all buckets."""
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
                print(f"Authenticating bucket {bucket}...")
                service = self.google_drive.authenticate(int(bucket))
                if service is None:
                    print(f"Failed to authenticate bucket {bucket}.")
                    continue
                
                # Search for the file in the current bucket
                query = f"name contains '{file_name}' and not name contains '.part'"
                result = service.files().list(q=query, fields="files(id, name)").execute()
                files = result.get("files", [])
                
                if files:
                    file_id = files[0]["id"]
                    print(f"Downloading file from bucket {bucket}...")
                    downloaded_file = self.download_file(service, file_id, save_path)
                    if downloaded_file:
                        print(f"Download complete: {downloaded_file}")
                        return downloaded_file
                else:
                    print(f"File not found in bucket {bucket}.")
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
                    
                    # Search for the file in the current bucket
                    query = f"name contains '{full_file_name}' and not name contains '.part'"
                    result = service.files().list(q=query, fields="files(id, name)").execute()
                    files = result.get("files", [])
                    
                    if files:
                        file_id = files[0]["id"]
                        print(f"Downloading file from bucket {bucket}...")
                        downloaded_file = self.download_file(service, file_id, save_path)
                        if downloaded_file:
                            print(f"Download complete: {downloaded_file}")
                            return downloaded_file
                    else:
                        print(f"File not found in bucket {bucket}.")
                except Exception as e:
                    print(f"Error downloading from bucket {bucket}: {e}")
        
        print("File not found in any bucket.")

    def search_file(self):
        """Search for files in Google Drive."""
        query = input("Enter search keyword: ").strip()
        if query:
            self.drive_manager.list_files_from_all_buckets(query=query)