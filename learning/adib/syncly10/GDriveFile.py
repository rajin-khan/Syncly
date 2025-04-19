# --- START OF FILE GDriveFile.py ---

import os
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
import re
import logging
from FileHandler import FileHandler
from Database import Database
from DriveManager import DriveManager
from GoogleDrive import GoogleDrive
from typing import Optional, List, Dict

# --- Text Extraction Imports ---
try:
    import PyPDF2
except ImportError: PyPDF2 = None; logging.warning("PyPDF2 not installed...")
try:
    import docx
except ImportError: docx = None; logging.warning("python-docx not installed...")

# --- Constants ---
SUPPORTED_TEXT_EXTENSIONS = ('.txt', '.md', '.py', '.js', '.json', '.csv', '.html', '.css', '.xml', '.log', '.c', '.cpp', '.h', '.java', '.sh', '.yaml', '.yml', '.pdf', '.docx')
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024 # 50 MB limit
# List of common file extensions to check
COMMON_EXTENSIONS = ['.jpg', '.pdf', '.png', '.txt', '.csv', '.docx', '.xlsx', '.java', '.py']

class GoogleDriveFile(FileHandler):
    def __init__(self, drive_manager: DriveManager):
        self.drive_manager = drive_manager
        self.db = Database().get_instance()
        self.logger = logging.getLogger(__name__)

    def _get_authenticated_service(self, bucket_number: int):
        # Finds the authenticated GoogleDrive service for a given bucket number.
        # Assumes DriveManager loads drives and GoogleDrive instances store their bucket_number
        for drive in self.drive_manager.drives:
            if isinstance(drive, GoogleDrive) and hasattr(drive, 'bucket_number') and drive.bucket_number == bucket_number:
                if hasattr(drive, 'service') and drive.service:
                    return drive.service
                else:
                    # Try to re-authenticate on the fly? Risky. Log error.
                    self.logger.error(f"GDrive instance for bucket {bucket_number} found but service not authenticated.")
                    return None
        self.logger.error(f"No matching authenticated GoogleDrive instance found for bucket {bucket_number}.")
        return None

    def _check_available_space(self, file_size):
        # Checks storage across GDrive buckets associated with the user
        free_space = []
        total_free = 0
        for drive in self.drive_manager.drives:
            if isinstance(drive, GoogleDrive) and drive.service and hasattr(drive, 'bucket_number'):
                try:
                    limit, usage = drive.check_storage() # check_storage is on the GoogleDrive instance
                    free = limit - usage
                    if free >= 0:
                        total_free += free
                        free_space.append([free, drive.bucket_number]) # Store free space and bucket number
                except Exception as e:
                    self.logger.error(f"Error checking storage for GDrive bucket {drive.bucket_number}: {e}")

        if total_free < file_size:
            self.logger.warning(f"Not enough total free space ({total_free} bytes) across GDrive buckets for file size {file_size} bytes.")
            return False, None

        free_space.sort(reverse=True, key=lambda x: x[0])
        return True, free_space

    # --- CORRECTED update_metadata METHOD ---
    def update_metadata(self, metadata):
        """Update the metadata in MongoDB."""
        # Correct check for None
        if self.db is None or self.db.client is None or self.db.metadata_collection is None:
            self.logger.error("Database connection or metadata_collection not initialized. Cannot update metadata.")
            return
        try:
            user_id = metadata.get("user_id") # Expect user_id to be added before calling
            if not user_id:
                user_id = getattr(self.drive_manager, 'user_id', None) # Fallback

            if not user_id:
                self.logger.error("Cannot update metadata: user_id is missing.")
                return # Stop if user_id is missing

            self.db.metadata_collection.update_one(
                {"user_id": user_id, "file_name": metadata["file_name"]},
                {"$set": metadata},
                upsert=True
            )
            self.logger.info(f"Metadata updated in MongoDB for file: {metadata['file_name']}")
        except Exception as e:
             self.logger.error(f"Failed to update metadata in MongoDB: {e}", exc_info=True)
             # Optionally re-raise or handle more gracefully depending on desired behavior
             # raise # Re-raise might stop the upload process entirely

    def _upload_entire_file(self, file_path, file_name, mimetype, best_bucket_info):
        """Upload the entire file to the best available bucket."""
        bucket_number = best_bucket_info[1]
        service = self._get_authenticated_service(bucket_number)
        if service is None:
            self.logger.error(f"Failed to get authenticated service for GDrive bucket {bucket_number} during upload.")
            return None
        try:
            self.logger.info(f"Uploading '{file_name}' to GDrive Bucket {bucket_number}")
            media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
            file_metadata = {'name': file_name}
            result = service.files().create(media_body=media, body=file_metadata, fields='id').execute()
            file_id = result.get("id")
            self.logger.info(f"Successfully uploaded '{file_name}' to GDrive Bucket {bucket_number}, File ID: {file_id}")
            return {"chunk_name": file_name, "file_id": file_id, "bucket": bucket_number}
        except HttpError as error:
            self.logger.error(f"Failed to upload '{file_name}' to GDrive Bucket {bucket_number}: {error}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error uploading '{file_name}' to GDrive Bucket {bucket_number}: {e}", exc_info=True)
            return None

    def upload_file(self, file_path: str, file_name: str, mimetype: str):
        """Upload a file to Google Drive and save metadata to MongoDB."""
        if not os.path.exists(file_path):
             self.logger.error(f"Upload failed: File not found at {file_path}")
             raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        has_space, free_space_buckets = self._check_available_space(file_size)
        if not has_space:
             self.logger.error(f"Upload failed: Not enough space for file '{file_name}' (size: {file_size} bytes)")
             raise Exception("Not enough storage space available in connected Google Drives.")

        # Ensure user_id is available in DriveManager
        user_id = getattr(self.drive_manager, 'user_id', None)
        if not user_id:
             self.logger.error("Upload failed: Cannot determine user_id from DriveManager.")
             raise Exception("User context missing for metadata.")

        metadata = {"user_id": user_id, "file_name": file_name, "chunks": []} # Add user_id here

        best_bucket_info = free_space_buckets[0]

        if best_bucket_info[0] >= file_size:
            chunk_metadata = self._upload_entire_file(file_path, file_name, mimetype, best_bucket_info)
            if chunk_metadata:
                metadata["chunks"].append(chunk_metadata)
                self.update_metadata(metadata) # Call corrected metadata update
            else:
                 self.logger.error(f"Upload failed for file '{file_name}' due to error in _upload_entire_file.")
                 raise Exception(f"Failed to upload {file_name} to Google Drive.")
        else:
            self.logger.warning(f"File '{file_name}' is larger than the single largest free space. Splitting not yet implemented.")
            raise NotImplementedError("File splitting for Google Drive is not yet implemented.")

    def download_file_content_by_id(self, service, file_id: str, file_size: Optional[int] = None) -> Optional[io.BytesIO]:
        """Downloads file content from Google Drive into an in-memory BytesIO object."""
        if file_size is not None and file_size > MAX_FILE_SIZE_BYTES:
            self.logger.warning(f"Skipping download for file ID {file_id}: size ({file_size} bytes) exceeds limit ({MAX_FILE_SIZE_BYTES} bytes).")
            return None
        try:
            self.logger.info(f"Attempting to download content for GDrive file ID: {file_id}")
            request = service.files().get_media(fileId=file_id)
            file_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(file_buffer, request)
            done = False
            while not done:
                status, done = downloader.next_chunk(num_retries=2)
                if file_buffer.tell() > MAX_FILE_SIZE_BYTES:
                     self.logger.warning(f"Download aborted for file ID {file_id}: Exceeded max size limit ({MAX_FILE_SIZE_BYTES} bytes) during download.")
                     return None # Abort download
            self.logger.info(f"Successfully downloaded content for GDrive file ID: {file_id} ({file_buffer.tell()} bytes)")
            file_buffer.seek(0)
            return file_buffer
        except HttpError as error:
            # ... (error handling) ...
             if error.resp.status == 404: self.logger.error(f"GDrive file ID {file_id} not found (404).")
             elif error.resp.status == 403: self.logger.error(f"Permission denied (403) for GDrive file ID {file_id}.")
             else: self.logger.error(f"HTTP error downloading GDrive file ID {file_id}: {error}")
             return None
        except Exception as e:
            self.logger.error(f"Unexpected error downloading GDrive file ID {file_id}: {e}", exc_info=True)
            return None

    def extract_text_from_content(self, content_buffer: io.BytesIO, filename: str, mime_type: Optional[str] = None) -> Optional[str]:
        """Extracts text from a BytesIO buffer based on filename extension."""
        extracted_text = None
        file_ext = os.path.splitext(filename)[1].lower()
        if not file_ext in SUPPORTED_TEXT_EXTENSIONS:
            self.logger.debug(f"Skipping text extraction for '{filename}': Unsupported extension '{file_ext}'.")
            return None
        self.logger.info(f"Attempting text extraction for '{filename}' (extension: {file_ext})")
        try:
            if file_ext == '.pdf':
                if PyPDF2:
                    # ... pdf extraction logic ...
                    pdf_reader = PyPDF2.PdfReader(content_buffer)
                    text_parts = [page.extract_text() for page in pdf_reader.pages if page.extract_text()]
                    extracted_text = "\n".join(text_parts).strip()
                    if not extracted_text: self.logger.warning(f"PyPDF2 extracted no text from '{filename}'.")
                else: self.logger.warning(f"Cannot extract text from PDF '{filename}': PyPDF2 not available.")
            elif file_ext == '.docx':
                if docx:
                    # ... docx extraction logic ...
                    document = docx.Document(content_buffer)
                    extracted_text = "\n".join([para.text for para in document.paragraphs]).strip()
                else: self.logger.warning(f"Cannot extract text from DOCX '{filename}': python-docx not available.")
            elif file_ext in ('.txt', '.md', '.py', '.js', '.json', '.csv', '.html', '.css', '.xml', '.log', '.c', '.cpp', '.h', '.java', '.sh', '.yaml', '.yml'):
                # ... plain text extraction logic ...
                 raw_bytes = content_buffer.getvalue()
                 try: extracted_text = raw_bytes.decode('utf-8').strip()
                 except UnicodeDecodeError:
                     self.logger.warning(f"UTF-8 decoding failed for '{filename}', trying latin-1.")
                     try: extracted_text = raw_bytes.decode('latin-1').strip()
                     except Exception as decode_err: self.logger.error(f"Could not decode text file '{filename}': {decode_err}")
            else: self.logger.debug(f"No specific text extraction logic for extension '{file_ext}' in file '{filename}'.")
        except PyPDF2.errors.PdfReadError as pdf_err: self.logger.error(f"Error reading PDF '{filename}' with PyPDF2: {pdf_err}")
        except Exception as e: self.logger.error(f"Failed to extract text from '{filename}': {e}", exc_info=True); extracted_text = None
        if extracted_text: self.logger.info(f"Successfully extracted text from '{filename}' (length: {len(extracted_text)} chars).")
        else: self.logger.warning(f"Could not extract text from '{filename}' (extension: {file_ext}).")
        return extracted_text if extracted_text else None

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
        
        # Sort chunks numerically by part number
        chunk_files.sort(key=lambda x: int(re.search(r'\.part(\d+)$', x['name']).group(1)))
        
        # Extract original filename with extension from first chunk
        original_filename = re.sub(r'\.part\d+$', '', chunk_files[0]['name'])
        merged_file_path = os.path.join(save_path, original_filename)       # Use extracted name
        
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
                service = self.google_drive.authenticate(int(bucket), self.drive_manager.user_id)  # Pass user_id here
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
                        service = self.google_drive.authenticate(int(bucket), self.drive_manager.user_id)  # Pass user_id here
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

    def split_and_upload_file(self, file_path, file_name, mimetype, file_size, free_space, metadata):
        """Split the file into chunks and upload them to available buckets."""
        offset = 0
        chunk_index = 0

        with open(file_path, "rb") as file:
            while offset < file_size:
                selected_bucket = self._find_bucket_with_space(free_space)
                if not selected_bucket:
                    print("No available accounts with free space.")
                    break

                chunk_size = min(selected_bucket[0], file_size - offset)
                chunk_filename = self._create_chunk_file(file_path, chunk_index, chunk_size)

                uploaded = self._upload_chunk_to_bucket(chunk_filename, selected_bucket, file_name, chunk_index)
                if not uploaded:
                    raise RuntimeError("Failed to upload chunk after retries")

                chunk_name = f"{file_name}_part{chunk_index}"
                self._update_metadata_and_space(metadata, chunk_name, selected_bucket, chunk_size)

                offset += chunk_size
                chunk_index += 1
                os.remove(chunk_filename)

        return metadata

    def upload_chunk(self, service, chunk_filename: str, mimetype: str, file_name: str, chunk_index: int):
        """
        Upload a single chunk to Google Drive.
        """
        media = MediaFileUpload(chunk_filename, mimetype=mimetype, resumable=True)
        chunk_name = f"{file_name}_part{chunk_index + 1}"
        file_metadata = {'name': chunk_name}
        result = service.files().create(media_body=media, body=file_metadata).execute()
        return result.get("id")


# --- END OF FILE GDriveFile.py ---