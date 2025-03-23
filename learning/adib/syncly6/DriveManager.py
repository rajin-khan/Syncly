
import os
import re
from Service import Service
from Database import Database
from GoogleDrive import GoogleDrive
from Dropbox import DropboxService
from AuthManager import AuthManager

class DriveManager:
    def __init__(self, user_id, token_dir="tokens"):
        self.user_id = user_id
        self.drives = []
        self.token_dir = token_dir
        self.sorted_buckets = []
        os.makedirs(self.token_dir, exist_ok=True)
        self.auth_manager = AuthManager(user_id, token_dir)
        self.load_user_drives()

    def load_user_drives(self):
        db = Database().get_instance()
        user_drives = db.drives_collection.find({"user_id": self.user_id})
        for drive in user_drives:
            if drive['type'] == 'GoogleDrive':
                gd = GoogleDrive(token_dir=self.token_dir, credentials_file="credentials.json")
                gd.authenticate(drive['bucket_number'], self.user_id)
                self.drives.append(gd)
            elif drive['type'] == 'Dropbox':
                dbx = DropboxService(token_dir=self.token_dir, app_key=drive['app_key'], app_secret=drive['app_secret'])
                dbx.authenticate(drive['bucket_number'], self.user_id)
                self.drives.append(dbx)

    def add_drive(self, drive: Service, bucket_number, drive_type):
        """
        Adds a storage service dynamically and saves it to the database.
        """
        # Authenticate the drive
        drive.authenticate(bucket_number, self.user_id)
        self.drives.append(drive)
        print(f"{type(drive).__name__} added successfully as bucket {bucket_number}.")

        # Save the drive to the database
        db = Database().get_instance()
        db.drives_collection.insert_one({
            "user_id": self.user_id,
            "type": drive_type,
            "bucket_number": bucket_number,
            "app_key": getattr(drive, 'app_key', None),
            "app_secret": getattr(drive, 'app_secret', None)
        })
        # Update the user's drives list in MongoDB
        db.users_collection.update_one(
            {"_id": self.user_id},  # Use the user_id (ObjectId) to find the correct document
            {"$addToSet": {"drives": bucket_number}},  # Add the new drive to the drives list
            upsert=True
        )
        

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
            if free > 0:
                self.sorted_buckets.append((free, drive, index))  # Append (free_space, drive) for each Dropbox drive

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
        Retrieves all authenticated bucket numbers for the current user from the database.
        """
        # Query the tokens_collection for tokens associated with the current user
        db = Database().get_instance()
        tokens = db.tokens_collection.find({"user_id": self.user_id})
    
        # Extract the bucket numbers from the tokens
        authenticated_buckets = [str(token["bucket_number"]) for token in tokens]
    
        return authenticated_buckets

    @staticmethod
    def parse_part_info(file_name):
        """
        Extract base name and part number from split filenames with improved regex.
        """
        patterns = [
            r'^(.*?)\.part(\d+)$',                 # .part0, .part1
            r'^(.*?)_part[\_\-]?(\d+)(\..*)?$',    # _part0, _part_1, _part-2
            r'^(.*?)\.(\d+)$',                     # .000, .001 (common split convention)
            r'^(.*?)(\d{3})(\..*)?$'               # Generic 3-digit numbering (e.g., .001)
        ]

        for pattern in patterns:
            match = re.match(pattern, file_name)
            if match:
                base = match.group(1)
                part_num = match.group(2)
                # Handle different pattern groups
                if pattern == patterns[1] and match.group(3):
                    base += match.group(3) if match.group(3) else ''
                elif pattern == patterns[3] and match.group(3):
                    base += match.group(3)
                try:
                    return base, int(part_num)
                except ValueError:
                    continue
        return None, None

    def get_files_from_drive(self, drive, query):
        """
        Retrieve files from a single drive based on the query.
        """
        try:
            return drive.listFiles(query=query)
        except Exception as e:
            print(f"Error retrieving files from {type(drive).__name__}: {e}")
            return []

    def display_files(self, all_files, start_index, page_size):
        """
        Display a paginated list of files.
        """
        print("\nFiles (Sorted Alphabetically):\n")
        for idx, (name, provider, size, file_url) in enumerate(all_files[start_index:start_index + page_size], start=start_index + 1):
            size_str = f"{float(size) / 1024 ** 2:.2f} MB" if size != 'Unknown' else "Unknown size"
            print(f"{idx}. {name} ({provider}) - {size_str}")
            print(f"   Press here to view file: {file_url}\n")

    def paginate_files(self, all_files, page_size=30):
        """
        Paginate and display files.
        """
        total_files = len(all_files)
        start_index = 0

        while start_index < total_files:
            self.display_files(all_files, start_index, page_size)
            start_index += page_size

            if start_index < total_files:
                more = input("\nDo you want to see more files? (y/n): ").strip().lower()
                if more != 'y':
                    break

    def list_files_from_all_buckets(self, query=None):
        """
        List files from all authenticated cloud services.
        :param query: Optional search query.
        """
        if not self.drives:
            print("No authenticated drives found. Please add a new bucket first.")
            return

        all_files = []
        seen_files = set()

        # Collect files from all drives
        for drive in self.drives:
            files = self.get_files_from_drive(drive, query)
            for file in files:
                file_name = file.get("name", "Unknown")
                file_size = file.get("size", "Unknown")
                file_path = file.get("path", "N/A")
                provider = type(drive).__name__

                if file_name not in seen_files:
                    all_files.append((file_name, provider, file_size, file_path))
                    seen_files.add(file_name)

        # Sort files by name
        all_files.sort(key=lambda x: x[0])

        # Paginate and display files
        self.paginate_files(all_files)
