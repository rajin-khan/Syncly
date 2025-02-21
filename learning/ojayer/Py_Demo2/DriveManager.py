import os
from service import service
#Manages multiple cloud storage services dynamically.
class DriveManager:
    #constructor
    def __init__(self, token_dir="tokens"):
        self.drives = []
        self.token_dir = token_dir
        os.makedirs(self.token_dir, exist_ok=True)

    #Adds a storage service dynamically.
    def add_drive(self, drive: service, bucket_number):
        drive.authenticate(bucket_number) #we can remove this and make individual service accounts
        self.drives.append(drive)
    #Checks storage usage for all drives.
    def check_all_storages(self):
        storage_info = []
        total_limit = 0
        total_usage = 0
        for index, drive in enumerate(self.drives):
            limit, usage = drive.check_storage()
            total_limit+=limit
            total_usage+=usage
            storage_info.append({
                "Drive Number": index + 1,
                "Storage Limit (bytes)": limit/1024**3,
                "Used Storage (bytes)": usage/1024**3,
                "Free Storage": (limit - usage)/1024**3,
                "Provider": type(drive).__name__
            })
        return storage_info, total_limit, total_usage
    #Retrieves all authenticated bucket numbers from stored tokens.
    def get_all_authenticated_buckets(self):
        return [
            f.replace(".json", "").replace("bucket_", "")
            for f in os.listdir(self.token_dir)
            if f.startswith("bucket_") and f.endswith(".json")
        ]
