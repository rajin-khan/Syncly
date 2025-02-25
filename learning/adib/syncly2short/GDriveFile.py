import os
import json
from googleapiclient.http import MediaFileUpload
from DriveManager import DriveManager

METADATA_FILE = "metadata.json"

class GoogleDriveFile:
    def __init__(self, drive_manager: DriveManager, google_drive):
        self.drive_manager = drive_manager
        self.google_drive = google_drive
    
    def upload_file(self, file_path, file_name, mimetype):
        file_size = os.path.getsize(file_path)
        sorted_buckets = self.drive_manager.get_sorted_buckets()
        
        if sum(bucket[0] for bucket in sorted_buckets) < file_size:
            print("Not enough space across all buckets.")
            return
        
        metadata = {"file_name": file_name, "chunks": []}
        
        for bucket in sorted_buckets:
            if bucket[0] >= file_size:
                self._upload_entire_file(bucket, file_path, file_name, mimetype, metadata)
                break
            else:
                file_chunks = self._split_file(file_path, file_size, bucket[0])
                self._upload_chunks(bucket, file_chunks, file_name, mimetype, metadata)
        
        self._update_metadata(metadata)
    
    def list_files(self, query=None):
        """Lists files from Google Drive."""
        service = self.google_drive.authenticate(1)  # Authenticate with the first available bucket
        query_filter = f"name contains '{query}'" if query else None
        results = service.files().list(q=query_filter, fields="files(id, name)").execute()
        
        return [{"name": file["name"], "id": file["id"]} for file in results.get("files", [])]
    
    def _upload_entire_file(self, bucket, file_path, file_name, mimetype, metadata):
        service = self.google_drive.authenticate(bucket[2])
        media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
        result = service.files().create(media_body=media, body={"name": file_name}).execute()
        metadata["chunks"].append({"chunk_name": file_name, "file_id": result["id"], "bucket": bucket[2]})
        bucket[0] -= os.path.getsize(file_path)
    
    def _upload_chunks(self, bucket, file_chunks, file_name, mimetype, metadata):
        service = self.google_drive.authenticate(bucket[2])
        for idx, chunk_path in enumerate(file_chunks):
            chunk_name = f"{file_name}_part{idx}"
            media = MediaFileUpload(chunk_path, mimetype=mimetype, resumable=True)
            result = service.files().create(media_body=media, body={"name": chunk_name}).execute()
            metadata["chunks"].append({"chunk_name": chunk_name, "file_id": result["id"], "bucket": bucket[2]})
            bucket[0] -= os.path.getsize(chunk_path)
            os.remove(chunk_path)
    
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