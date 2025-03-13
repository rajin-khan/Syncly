import os
import dropbox
import logging
import re
from dropbox.exceptions import AuthError, ApiError
from dropbox.files import WriteMode
from FileHandler import FileHandler
from Database import Database

class DropBoxFile(FileHandler):
    def __init__(self, access_token: str, drive_manager):
        self.dbx = dropbox.Dropbox(access_token)
        self.drive_manager = drive_manager
        self.db = Database().get_instance()

    def _update_metadata(self, metadata):
        """Update the metadata in MongoDB."""
        self.db.metadata_collection.update_one(
            {"user_id": self.drive_manager.user_id, "file_name": metadata["file_name"]},
            {"$set": metadata},
            upsert=True
        )
        print("Upload complete. Metadata updated in MongoDB.")

    def _check_available_space(self, file_size):
        """Check if there is enough space across all buckets."""
        sorted_buckets = self.drive_manager.get_sorted_buckets()
        total_free = sum(bucket[0] for bucket in sorted_buckets)
        if total_free < file_size:
            print("Not enough space.")
            return False, None
        return True, sorted_buckets

    def _upload_entire_file(self, file_path, file_name, best_bucket):
        """Upload the entire file to the best available bucket."""
        with open(file_path, "rb") as f:
            best_bucket[1].client.files_upload(f.read(), f"/{file_name}", mode=WriteMode("overwrite"))
        return {"chunk_name": file_name, "account": f"{best_bucket[2] + 1}"}

    def _upload_chunked_file(self, file_path, file_name, file_size, sorted_buckets):
        """Split the file into chunks and upload them to available buckets."""
        metadata = {"user_id": self.drive_manager.user_id, "file_name": file_name, "chunks": []}
        offset = 0
        chunk_index = 0

        with open(file_path, "rb") as file:
            while offset < file_size:
                selected_bucket = self._find_bucket_with_space(sorted_buckets)
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

    def upload_file(self, file_path, file_name, mimetype="None"):
        """Upload a file to Dropbox and save metadata to MongoDB."""
        file_size = os.path.getsize(file_path)
        has_space, sorted_buckets = self._check_available_space(file_size)
        if not has_space:
            return

        metadata = {"user_id": self.drive_manager.user_id, "file_name": file_name, "chunks": []}
        best_bucket = sorted_buckets[0]

        if best_bucket[0] >= file_size:
            # Upload the entire file
            chunk_metadata = self._upload_entire_file(file_path, file_name, best_bucket)
            metadata["chunks"].append(chunk_metadata)
        else:
            # Split the file into chunks and upload
            metadata = self._upload_chunked_file(file_path, file_name, file_size, sorted_buckets)

        # Update metadata in MongoDB
        self._update_metadata(metadata)

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