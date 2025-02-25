import os
import re
from Service import Service
from DropboxService import DropboxService
from GoogleDriveService import GoogleDriveService
from GDriveFile import GoogleDriveFile
from DropBoxFile import DropBoxFile

class DriveManager:
    def __init__(self, token_dir="tokens"):
        self.drives = []
        self.token_dir = token_dir
        os.makedirs(self.token_dir, exist_ok=True)
    
    def add_drive(self, drive: Service, bucket_number):
        """
        Adds a storage service dynamically.
        """
        drive.authenticate(bucket_number)
        self.drives.append(drive)
        print(f"{type(drive).__name__} added successfully as bucket {bucket_number}.")
    
    def check_all_storages(self):
        """
        Checks storage usage for all drives and sorts them by free space.
        """
        storage_info = []
        total_limit, total_usage = 0, 0
        sorted_buckets = []
        
        for index, drive in enumerate(self.drives):
            limit, usage = drive.check_storage()
            free = limit - usage
            if free > 0:
                sorted_buckets.append((free, drive, index))
            
            total_limit += limit
            total_usage += usage
            storage_info.append(self._format_storage_info(drive, index, limit, usage))
        
        sorted_buckets.sort(reverse=True, key=lambda x: x[0])
        return storage_info, total_limit, total_usage, sorted_buckets
    
    def get_sorted_buckets(self):
        """Returns the sorted list of buckets based on free space."""
        return self.check_all_storages()[3]
    
    def get_all_authenticated_buckets(self):
        """Retrieves all authenticated bucket numbers."""
        return [
            f.replace(".json", "").replace("bucket_", "")
            for f in os.listdir(self.token_dir)
            if f.startswith("bucket_") and f.endswith(".json")
        ]
    
    @staticmethod
    def _format_storage_info(drive, index, limit, usage):
        """Formats storage information for better readability."""
        return {
            "Drive Number": index + 1,
            "Storage Limit (GB)": limit / 1024**3,
            "Used Storage (GB)": usage / 1024**3,
            "Free Storage (GB)": (limit - usage) / 1024**3,
            "Provider": type(drive).__name__
        }
    
    @staticmethod
    def parse_part_info(file_name):
        """Extracts base name and part number from split filenames."""
        patterns = [
            r'^(.*?)\.part(\d+)$',
            r'^(.*?)_part[\_\-]?(\d+)(\..*)?$',
            r'^(.*?)\.(\d+)$',
            r'^(.*?)(\d{3})(\..*)?$'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, file_name)
            if match:
                base = match.group(1)
                part_num = match.group(2)
                try:
                    return base, int(part_num)
                except ValueError:
                    continue
        return None, None
    
    def list_files_from_all_buckets(self, query=None):
        """List files from all authenticated cloud services."""
        if not self.drives:
            print("No authenticated drives found.")
            return []
        
        all_files, seen_files = [], set()
        
        for drive in self.drives:
            try:
                if isinstance(drive, GoogleDriveService):
                    gdrive_file = GoogleDriveFile(self, drive)
                    files = gdrive_file.list_files(query=query)
                elif isinstance(drive, DropboxService):
                    dropbox_file = DropBoxFile(drive.authenticate(1), self)  # Fixed: Ensure authentication
                    files = dropbox_file.list_files(query=query)

                for file in files:
                    file_name = file.get("name", "Unknown")
                    if file_name not in seen_files:
                        all_files.append(file)
                        seen_files.add(file_name)
            except Exception as e:
                print(f"Error retrieving files from {type(drive).__name__}: {e}")
        
        return sorted(all_files, key=lambda x: x["name"])