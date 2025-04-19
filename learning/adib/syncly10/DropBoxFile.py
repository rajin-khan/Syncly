# --- START OF FILE DropBoxFile.py ---

import os
import io
import dropbox
import logging
import re
from dropbox.exceptions import AuthError, ApiError
from dropbox.files import WriteMode, FileMetadata, SearchOptions, SearchOrderBy, FileStatus # Added imports
from FileHandler import FileHandler
from Database import Database
from typing import Optional, List, Dict
from DriveManager import DriveManager # Import DriveManager if needed for user_id context
from Dropbox import DropboxService

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

class DropBoxFile(FileHandler):
    def __init__(self, access_token: str, drive_manager): # Pass DriveManager
        self.dbx = dropbox.Dropbox(access_token)
        self.drive_manager = drive_manager # Store DriveManager
        self.db = Database().get_instance()
        self.logger = logging.getLogger(__name__)

    # --- CORRECTED _update_metadata METHOD ---
    def _update_metadata(self, metadata):
        """Update the metadata in MongoDB."""
        # Correct check for None
        if self.db is None or self.db.client is None or self.db.metadata_collection is None:
            self.logger.error("Database connection or metadata_collection not initialized. Cannot update metadata.")
            return
        try:
            # Get user_id (should be added to metadata dict before calling)
            user_id = metadata.get("user_id")
            if not user_id:
                 # Fallback to getting from drive_manager instance if not in metadata
                 user_id = getattr(self.drive_manager, 'user_id', None)

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
             # raise # Optionally re-raise

    def _check_available_space(self, file_size):
        # Checks space across Dropbox buckets associated with the user
        dropbox_buckets_info = []
        total_free = 0
        if not hasattr(self.drive_manager, 'drives') or not self.drive_manager.drives:
             self.logger.warning("DriveManager has no drives loaded for Dropbox space check.")
             return False, None

        for drive_instance in self.drive_manager.drives:
             # Check if it's a DropboxService instance and has an authenticated service
            if isinstance(drive_instance, DropboxService) and drive_instance.service and hasattr(drive_instance, 'bucket_number'):
                 try:
                     # Use the check_storage method from DropboxService instance
                     limit, usage_used = drive_instance.check_storage()
                     free = limit - usage_used
                     if free >= 0:
                          total_free += free
                          # Store free space, the client instance, and bucket number
                          dropbox_buckets_info.append([free, drive_instance.service, drive_instance.bucket_number])
                 except Exception as e:
                     self.logger.error(f"Error checking storage for Dropbox bucket {drive_instance.bucket_number}: {e}")

        if total_free < file_size:
            self.logger.warning(f"Not enough total free space ({total_free} bytes) across Dropbox buckets for file size {file_size} bytes.")
            return False, None

        dropbox_buckets_info.sort(reverse=True, key=lambda x: x[0])
        return True, dropbox_buckets_info

    def _upload_entire_file(self, file_path, file_name, best_bucket_info):
        """Upload the entire file to the best available Dropbox bucket."""
        free_space, dbx_client, bucket_number = best_bucket_info
        dropbox_path = f"/{file_name}"
        try:
            self.logger.info(f"Uploading '{file_name}' to Dropbox Bucket {bucket_number} (Path: {dropbox_path})")
            with open(file_path, "rb") as f:
                file_metadata = dbx_client.files_upload(f.read(), dropbox_path, mode=WriteMode("overwrite"))
            self.logger.info(f"Successfully uploaded '{file_name}' to Dropbox Bucket {bucket_number}, Path: {file_metadata.path_display}")
            return {"chunk_name": file_name, "file_id": file_metadata.id, "path": file_metadata.path_lower, "bucket": bucket_number}
        except ApiError as err:
            self.logger.error(f"Failed to upload '{file_name}' to Dropbox Bucket {bucket_number}: {err}")
            return None
        except Exception as e:
             self.logger.error(f"Unexpected error uploading '{file_name}' to Dropbox Bucket {bucket_number}: {e}", exc_info=True)
             return None

    def upload_file(self, file_path, file_name, mimetype="None"):
        """Upload a file to Dropbox and save metadata to MongoDB."""
        if not os.path.exists(file_path):
             self.logger.error(f"Upload failed: File not found at {file_path}")
             raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        has_space, sorted_dropbox_buckets = self._check_available_space(file_size)
        if not has_space:
             self.logger.error(f"Upload failed: Not enough space for file '{file_name}' (size: {file_size} bytes)")
             raise Exception("Not enough storage space available in connected Dropbox accounts.")

        user_id = getattr(self.drive_manager, 'user_id', None)
        if not user_id:
            self.logger.error("Cannot upload: user_id not found in DriveManager.")
            raise Exception("User context not found for metadata.")

        metadata = {"user_id": user_id, "file_name": file_name, "chunks": []} # Add user_id here
        best_bucket_info = sorted_dropbox_buckets[0] # [free_space, client_instance, bucket_number]

        if best_bucket_info[0] >= file_size:
            chunk_metadata = self._upload_entire_file(file_path, file_name, best_bucket_info)
            if chunk_metadata:
                metadata["chunks"].append(chunk_metadata)
                self._update_metadata(metadata) # Call corrected metadata update
            else:
                 self.logger.error(f"Upload failed for file '{file_name}' due to error in _upload_entire_file (Dropbox).")
                 raise Exception(f"Failed to upload {file_name} to Dropbox.")
        else:
            self.logger.warning(f"File '{file_name}' is larger than the single largest free space in Dropbox buckets. Chunking required but not implemented.")
            raise NotImplementedError("File splitting/chunking for Dropbox is not yet implemented.")


    # --- download_file_content_by_path, extract_text_from_content ---
    # --- download_file, search_file, download_and_merge_chunks ---
    # --- merge_chunks, split_and_upload_file, update_metadata, upload_chunk ---
    # (Keep the rest of the DropBoxFile methods as they were in the previous step)
    # ... (rest of DropBoxFile.py methods from previous step) ...

    def download_file_content_by_path(self, file_path: str) -> Optional[io.BytesIO]:
        """Downloads file content from Dropbox (using file path) into an in-memory BytesIO object."""
        try:
            self.logger.info(f"Attempting to get metadata for Dropbox path: {file_path}")
            metadata = self.dbx.files_get_metadata(file_path)
            if not isinstance(metadata, FileMetadata):
                 self.logger.warning(f"Path {file_path} is not a file. Skipping download.")
                 return None
            file_size = metadata.size
            if file_size > MAX_FILE_SIZE_BYTES:
                self.logger.warning(f"Skipping download for Dropbox path {file_path}: size ({file_size} bytes) exceeds limit ({MAX_FILE_SIZE_BYTES} bytes).")
                return None
            self.logger.info(f"Attempting to download content for Dropbox path: {file_path} ({file_size} bytes)")
            metadata, response = self.dbx.files_download(file_path)
            if response.status_code == 200:
                file_buffer = io.BytesIO(response.content)
                self.logger.info(f"Successfully downloaded content for Dropbox path: {file_path} ({file_buffer.tell()} bytes)")
                file_buffer.seek(0)
                return file_buffer
            else:
                 self.logger.error(f"Dropbox download failed for path {file_path} with status code: {response.status_code}. Content: {response.text}")
                 return None
        except ApiError as err:
            # ... (error handling) ...
            if err.error.is_path() and err.error.get_path().is_not_found(): self.logger.error(f"Dropbox path not found (404): {file_path}")
            elif err.user_message_text: self.logger.error(f"API error downloading Dropbox path {file_path}: {err.user_message_text}")
            else: self.logger.error(f"API error downloading Dropbox path {file_path}: {err}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error downloading Dropbox path {file_path}: {e}", exc_info=True)
            return None

    def extract_text_from_content(self, content_buffer: io.BytesIO, filename: str, mime_type: Optional[str] = None) -> Optional[str]:
        """Extracts text from a BytesIO buffer based on filename extension."""
        # Identical logic to GDriveFile, can be potentially refactored
        extracted_text = None
        file_ext = os.path.splitext(filename)[1].lower()
        if not file_ext in SUPPORTED_TEXT_EXTENSIONS:
             self.logger.debug(f"Skipping text extraction for '{filename}': Unsupported extension '{file_ext}'.")
             return None
        self.logger.info(f"Attempting text extraction for '{filename}' (extension: {file_ext})")
        try:
            if file_ext == '.pdf':
                if PyPDF2:
                    # ... pdf extraction ...
                    pdf_reader = PyPDF2.PdfReader(content_buffer)
                    text_parts = [page.extract_text() for page in pdf_reader.pages if page.extract_text()]
                    extracted_text = "\n".join(text_parts).strip()
                    if not extracted_text: self.logger.warning(f"PyPDF2 extracted no text from '{filename}'.")
                else: self.logger.warning(f"Cannot extract text from PDF '{filename}': PyPDF2 not available.")
            elif file_ext == '.docx':
                if docx:
                     # ... docx extraction ...
                     document = docx.Document(content_buffer)
                     extracted_text = "\n".join([para.text for para in document.paragraphs]).strip()
                else: self.logger.warning(f"Cannot extract text from DOCX '{filename}': python-docx not available.")
            elif file_ext in ('.txt', '.md', '.py', '.js', '.json', '.csv', '.html', '.css', '.xml', '.log', '.c', '.cpp', '.h', '.java', '.sh', '.yaml', '.yml'):
                # ... plain text extraction ...
                raw_bytes = content_buffer.getvalue(); extracted_text = None
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

    def download_file(self, file_path: str, save_path: str):
        """
        Downloads a file from Dropbox.
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            # Download the file
            with open(save_path, 'wb') as f:
                metadata, res = self.dbx.files_download(file_path)
                f.write(res.content)
            print(f"File downloaded to: {save_path}")
        except ApiError as err:
            print(f"API error: {err}")
        except PermissionError:
            print(f"Permission denied: Cannot write to {save_path}. Check directory permissions.")
        except Exception as e:
            print(f"Error downloading file: {e}")

    def search_file(self, query: str):
        """
        Searches for a file in Dropbox.
        :param query: The search query (file name).
        :return: Path to the file if found, otherwise None.
        """
        try:
            result = self.dbx.files_search_v2(query=query).matches

            if not result:
                print(f"No files found with the name '{query}'.")
                return None

            for match in result:
                metadata = match.metadata.get_metadata()
                if isinstance(metadata, dropbox.files.FileMetadata):
                    if metadata.name.lower() == query.lower():
                        print(f"Found file: {metadata.name}")
                        return metadata.path_lower

            print(f"No exact match found for '{query}'.")
            return None
        except ApiError as err:
            print(f"API error: {err}")
        except Exception as e:
            print(f"Error searching file: {e}")

    def download_and_merge_chunks(self, file_name, save_path):
        """Download and merge chunked files from Dropbox."""
        os.makedirs(save_path, exist_ok=True)
    
        try:
            result = self.dbx.files_search_v2(query=file_name).matches
            chunk_files = [entry.metadata.get_metadata() for entry in result if ".part" in entry.metadata.name]
    
            if not chunk_files:
                logging.info(f"No chunked files found for '{file_name}'.")
                return None
    
            # Sort chunks by part number
            chunk_files.sort(key=lambda x: int(re.search(r'\.part(\d+)', x.name).group(1)))
    
            original_filename = re.sub(r'\.part\d+$', '', chunk_files[0].name)
            merged_file_path = os.path.join(save_path, original_filename)
    
            if os.path.exists(merged_file_path):
                logging.info(f"File {merged_file_path} already exists. Skipping download.")
                return merged_file_path
    
            chunk_paths = []
            for file in chunk_files:
                chunk_path = os.path.join(save_path, file.name)  # Save with original chunk name temporarily
                self.download_file(file.path_lower, chunk_path)
                if os.path.exists(chunk_path):
                    chunk_paths.append(chunk_path)
    
            self.merge_chunks(chunk_paths, merged_file_path)
    
            for chunk_path in chunk_paths:
                os.remove(chunk_path)
    
            logging.info(f"Merged file saved at: {merged_file_path}")
            return merged_file_path
        except Exception as e:
            logging.error(f"Error downloading chunked files: {e}")
            return None

    def merge_chunks(self, file_paths, merged_file_path):
        """Merge downloaded file chunks into a single file."""
        with open(merged_file_path, "wb") as merged_file:
            for chunk_path in file_paths:
                with open(chunk_path, "rb") as chunk:
                    merged_file.write(chunk.read())

        logging.info(f"Merged file saved at: {merged_file_path}")

    def split_and_upload_file(self, file_path, file_name, mimetype, file_size, free_space, metadata):
        return super().split_and_upload_file(file_path, file_name, mimetype, file_size, free_space, metadata)
    
    def update_metadata(self, metadata):
        return super().update_metadata(metadata)
    
    def upload_chunk(self, chunk_str, mimetype, file_name, chunk_index):
        return super().upload_chunk(chunk_str, mimetype, file_name, chunk_index)


# --- END OF FILE DropBoxFile.py ---