import os
from service import service
from Dropbox import DropboxService
#Manages multiple cloud storage services dynamically.
class DriveManager:
    def __init__(self, token_dir="tokens"):
        self.drives = []
        self.token_dir = token_dir
        self.sorted_buckets = []  # Initialize sorted_buckets as an empty list
        os.makedirs(self.token_dir, exist_ok=True)

    def add_drive(self, drive: service, bucket_number):
        """
        Adds a storage service dynamically.
        :param drive: The drive instance (e.g., DropboxService, googleDrive).
        :param bucket_number: The bucket number for this drive.
        """
        drive.authenticate(bucket_number)
        self.drives.append(drive)

    def check_all_storages(self):
        """
        Checks storage usage for all drives and sorts them by free space.
        :return: A tuple containing storage info, total limit, and total usage.
        """
        self.sorted_buckets = []  # Reset the sorted_buckets list
        storage_info = []
        total_limit = 0
        total_usage = 0

        for index, drive in enumerate(self.drives):
            limit, usage = drive.check_storage()
            free = limit - usage
            if free > 0 and isinstance(drive, DropboxService):  # Only include DropboxService instances
                self.sorted_buckets.append((free, drive))  # Append (free_space, drive) for each Dropbox drive
            total_limit += limit
            total_usage += usage
            storage_info.append({
                "Drive Number": index + 1,
                "Storage Limit (bytes)": limit / 1024**3,
                "Used Storage (bytes)": usage / 1024**3,
                "Free Storage": (limit - usage) / 1024**3,
                "Provider": type(drive).__name__
            })

        # Sort buckets by free space in descending order
        self.sorted_buckets.sort(reverse=True, key=lambda x: x[0])
        return storage_info, total_limit, total_usage

    def get_sorted_buckets(self):
        """
        Returns the sorted list of buckets with the most free space.
        """
        return self.sorted_buckets

    def update_sorted_buckets(self):
        """
        Updates the sorted list of buckets based on current storage status.
        """
        self.check_all_storages()

    def get_all_authenticated_buckets(self):
        """
        Retrieves all authenticated bucket numbers from stored tokens.
        """
        return [
            f.replace(".json", "").replace("bucket_", "")
            for f in os.listdir(self.token_dir)
            if f.startswith("bucket_") and f.endswith(".json")
        ]
