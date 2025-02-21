import os
import dropbox
from dropbox.exceptions import AuthError, ApiError

class DropBoxFile:
    def __init__(self, access_token: str, drive_manager):
        """
        Constructor for DropBoxFile.
        :param access_token: Dropbox API access token.
        :param drive_manager: Instance of DriveManager for bucket management.
        """
        self.dbx = dropbox.Dropbox(access_token)
        self.drive_manager = drive_manager  # DriveManager instance

    def upload_file(self, file_path: str, file_name: str, mimetype: str):
        """
        Uploads a file to Dropbox.
        """
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            dropbox_path = f"/{file_name}"
            self.dbx.files_upload(file_data, dropbox_path, mode=dropbox.files.WriteMode.overwrite)
            print(f"File {file_name} uploaded to Dropbox at: {dropbox_path}")
        except AuthError as e:
            print(f"Authentication error: {e}. Please refresh your access token.")
        except Exception as e:
            print(f"Error uploading file: {e}")

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
                    dbx_file_name = os.path.splitext(metadata.name)[0]
                    if dbx_file_name.lower() == query.lower():
                        print(f"Found file: {metadata.name}")
                        return metadata.path_lower

            print(f"No exact match found for '{query}'.")
            return None
        except ApiError as err:
            print(f"API error: {err}")
        except Exception as e:
            print(f"Error searching file: {e}")

    def download_and_merge_chunks(self, file_name, save_path):
        return super().download_and_merge_chunks(file_name, save_path)
    
    def merge_chunks(self, file_paths, merged_file_path):
        return super().merge_chunks(file_paths, merged_file_path)
    
    def split_and_upload_file(self, file_path, file_name, mimetype, file_size, free_space, metadata):
        return super().split_and_upload_file(file_path, file_name, mimetype, file_size, free_space, metadata)
    
    def update_metadata(self, metadata):
        return super().update_metadata(metadata)
    
    def upload_chunk(self, chunk_str, mimetype, file_name, chunk_index):
        return super().upload_chunk(chunk_str, mimetype, file_name, chunk_index)