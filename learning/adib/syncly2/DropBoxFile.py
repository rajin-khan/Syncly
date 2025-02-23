import os
import dropbox
import json
import re
import logging
from dropbox.exceptions import AuthError, ApiError
from dropbox.files import WriteMode
from FileHandler import FileHandler
from DriveManager import DriveManager

# Constants
METADATA_FILE = "metadata.json"
TOKEN_FILE = "token.json"  # File to store access and refresh tokens

class DropBoxFile:
    def __init__(self, access_token: str, drive_manager):
        """
        Constructor for DropBoxFile.
        :param access_token: Dropbox API access token.
        :param drive_manager: Instance of DriveManager for bucket management.
        """
        self.dbx = dropbox.Dropbox(access_token)
        self.drive_manager = drive_manager  # DriveManager instance

    def upload_file(self, file_path, file_name, mimetype="None"):
        file_size = os.path.getsize(file_path)
        sorted_buckets = self.drive_manager.get_sorted_buckets()  # Get sorted buckets from DriveManager
        total_free = sum(bucket[0] for bucket in sorted_buckets)  # Calculate total free space

        if total_free < file_size:
            print("Not enough space.")
            return

        metadata = {"file_name": file_name, "chunks": []}
        best_bucket = sorted_buckets[0]  # Use the bucket with the most free space first

        if best_bucket[0] >= file_size:
            # Upload the entire file
            with open(file_path, "rb") as f:
                best_bucket[1].client.files_upload(f.read(), f"/{file_name}", mode=WriteMode("overwrite"))
            metadata["chunks"].append({"chunk_name": file_name, "account": f"{best_bucket[2]+1}"})
        else:
            # Split the file into chunks and upload
            offset = 0
            chunk_index = 0
            with open(file_path, "rb") as file:
                while offset < file_size:
                    # Find an account with enough space
                    selected_bucket = None
                    for bucket in sorted_buckets:
                        if bucket[0] > 0:
                            selected_bucket = bucket
                            break
                    if not selected_bucket:
                        print("No available accounts with free space.")
                        break

                    chunk_size = min(selected_bucket[0], file_size - offset)
                    chunk_filename = f"{file_path}.part{chunk_index}"
                    with open(chunk_filename, "wb") as chunk_file:
                        chunk_file.write(file.read(chunk_size))

                    uploaded = False
                    while not uploaded:
                        try:
                            chunk_name = f"{file_name}_part{chunk_index}"
                            selected_bucket[1].client.files_upload(
                                open(chunk_filename, "rb").read(),
                                f"/{chunk_name}",
                                mode=WriteMode("overwrite")
                            )
                            uploaded = True
                        except ApiError as e:
                            if "insufficient_space" in str(e):
                                print(f"Account {selected_bucket[1].bucket_number} is full. Trying next account.")
                                selected_bucket[0] = 0  # Mark account as full
                                break
                            else:
                                os.remove(chunk_filename)
                                raise e

                    if not uploaded:
                        raise RuntimeError("Failed to upload chunk after retries")

                    metadata["chunks"].append({
                        "chunk_name": chunk_name,
                        "account": selected_bucket[1].bucket_number
                    })

                    # Update remaining space after successful upload
                    selected_bucket[0] -= chunk_size
                    offset += chunk_size
                    chunk_index += 1
                    os.remove(chunk_filename)

        # Update metadata
        if os.path.exists(METADATA_FILE) and os.path.getsize(METADATA_FILE) > 0:
            with open(METADATA_FILE, 'r') as f:
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
        with open(METADATA_FILE, 'w') as f:
            json.dump(existing_metadata, f, indent=4)
            print("Upload complete. Metadata updated.")
    
    def split_and_upload_file(self,file_path:str, file_name:str, mimetype:str, file_size:str, free_space:str, metadata:str):
        pass

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
            result = self.dbx.files_search_v2(file_name).matches
            chunk_files = [entry.metadata for entry in result if entry.metadata.name.endswith(".part")]

            if not chunk_files:
                logging.info(f"No chunked files found for '{file_name}'.")
                return None

            chunk_files.sort(key=lambda x: int(re.findall(r'\.part(\d+)', x.name)[-1]))

            original_filename = re.sub(r'\.part\d+$', '', chunk_files[0].name)
            merged_file_path = os.path.join(save_path, original_filename)

            if os.path.exists(merged_file_path):
                logging.info(f"File {merged_file_path} already exists. Skipping download.")
                return merged_file_path

            chunk_paths = []
            for file in chunk_files:
                chunk_path = self.download_file(file.path_lower, save_path)
                if chunk_path:
                    chunk_paths.append(chunk_path)

            self.merge_chunks(chunk_paths, merged_file_path)

            for chunk_path in chunk_paths:
                os.remove(chunk_path)

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
    
    def upload_chunk(self, chunk_str, mimetype, file_name, chunk_index):
        return super().upload_chunk(chunk_str, mimetype, file_name, chunk_index)
