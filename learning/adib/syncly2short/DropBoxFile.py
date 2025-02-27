import os
import json
import dropbox
from dropbox.exceptions import ApiError
from dropbox.files import WriteMode

METADATA_FILE = "metadata.json"

class DropBoxFile:
    def __init__(self, access_token: str, drive_manager):
        from drive_manager import DriveManager  # ✅ Lazy import to avoid circular dependency
        self.dbx = dropbox.Dropbox(access_token)
        self.drive_manager = drive_manager

    
    def upload_file(self, file_path, file_name, mimetype="None"):
        file_size = os.path.getsize(file_path)
        sorted_buckets = self.drive_manager.get_sorted_buckets()
        
        if sum(bucket[0] for bucket in sorted_buckets) < file_size:
            print("Not enough space.")
            return
        
        metadata = {"file_name": file_name, "chunks": []}
        
        for bucket in sorted_buckets:
            if bucket[0] >= file_size:
                self._upload_entire_file(bucket, file_path, file_name, metadata)
                break
            else:
                file_chunks = self._split_file(file_path, file_size, bucket[0])
                self._upload_chunks(bucket, file_chunks, file_name, metadata)
        
        self._update_metadata(metadata)
    
    def list_files(self, query=None):
        """Lists files from Dropbox."""
        try:
            result = self.dbx.files_list_folder("")
            return [{"name": file.name, "path": file.path_lower} for file in result.entries if query in file.name]
        except Exception as e:
            print(f"Error listing Dropbox files: {e}")
            return []
    
    def _upload_entire_file(self, bucket, file_path, file_name, metadata):
        with open(file_path, "rb") as f:
            bucket[1].client.files_upload(f.read(), f"/{file_name}", mode=WriteMode("overwrite"))
        metadata["chunks"].append({"chunk_name": file_name, "account": bucket[2]})
        bucket[0] -= os.path.getsize(file_path)
    
    def _upload_chunks(self, bucket, file_chunks, file_name, metadata):
        for idx, chunk_path in enumerate(file_chunks):
            chunk_name = f"{file_name}_part{idx}"
            try:
                with open(chunk_path, "rb") as chunk_file:
                    bucket[1].client.files_upload(chunk_file.read(), f"/{chunk_name}", mode=WriteMode("overwrite"))
                metadata["chunks"].append({"chunk_name": chunk_name, "account": bucket[2]})
                bucket[0] -= os.path.getsize(chunk_path)
                os.remove(chunk_path)
            except ApiError:
                print(f"Failed to upload chunk: {chunk_name}")
    
    def _split_file(self, file_path, file_size, chunk_size):
        chunks = []
        with open(file_path, "rb") as file:
            for i in range(0, file_size, chunk_size):
                chunk_path = f"{file_path}.part{i//chunk_size}"
                with open(chunk_path, "wb") as chunk_file:
                    chunk_file.write(file.read(min(chunk_size, file_size - i)))
                chunks.append(chunk_path)
        return chunks
    
    def _update_metadata(self, metadata):
        existing_metadata = self._load_metadata()
        existing_metadata.append(metadata)
        with open(METADATA_FILE, 'w') as f:
            json.dump(existing_metadata, f, indent=4)
    
    def _load_metadata(self):
        if os.path.exists(METADATA_FILE) and os.path.getsize(METADATA_FILE) > 0:
            with open(METADATA_FILE, 'r') as f:
                try:
                    return json.load(f) or []
                except json.JSONDecodeError:
                    print("Metadata file is corrupted. Resetting metadata.")
        return []