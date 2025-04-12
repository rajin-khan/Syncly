import os
import re
import logging
from typing import List, Tuple, Optional

from bson import ObjectId
from Database import Database
from GoogleDrive import GoogleDrive
from Dropbox import DropboxService
from AuthManager import AuthManager
from Service import Service
from dotenv import load_dotenv

load_dotenv()  # Load .env file

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DriveManager")

class DriveManager:
    def __init__(self, user_id: str, token_dir: str = "tokens"):
        """
        Initialize DriveManager with user ID and token directory.
        
        :param user_id: Unique identifier for the user (MongoDB ObjectId as string).
        :param token_dir: Directory to store authentication tokens.
        """
        self.user_id = user_id
        self.token_dir = token_dir
        self.drives: List[Service] = []
        self.sorted_buckets: List[Tuple[float, Service, int]] = []
        os.makedirs(self.token_dir, exist_ok=True)
        self.auth_manager = AuthManager(user_id, token_dir)
        logger.info(f"DriveManager initialized for user_id {user_id}")

    def load_user_drives(self) -> None:
        """
        Load authenticated drives from MongoDB's drives_collection.
        Clears existing drives to prevent duplicates.
        """
        self.drives = []
        db = Database.get_instance()
        try:
            user_id_obj = ObjectId(self.user_id)
            logger.info(f"Querying drives_collection for user_id {self.user_id} (ObjectId: {user_id_obj})")
            user_drives = db.drives_collection.find({"user_id": user_id_obj})
            drives_list = list(user_drives)
            logger.info(f"Found {len(drives_list)} drives for user_id {self.user_id}: {[drive.get('type') for drive in drives_list]}")

            for drive in drives_list:
                drive_type = drive.get("type")
                bucket_number = drive.get("bucket_number")
                if not drive_type or not bucket_number:
                    logger.warning(f"Invalid drive entry: {drive}")
                    continue
                try:
                    if drive_type == "GoogleDrive":
                        gd = GoogleDrive(token_dir=self.token_dir, credentials_file="credentials.json")
                        if gd.authenticate(bucket_number, self.user_id):
                            self.drives.append(gd)
                            logger.info(f"Loaded Google Drive bucket {bucket_number} for user_id {self.user_id}")
                        else:
                            logger.error(f"Google Drive authentication failed for bucket {bucket_number}")
                    elif drive_type == "Dropbox":
                        app_key = drive.get("app_key") or os.getenv("DROPBOX_APP_KEY")
                        app_secret = drive.get("app_secret") or os.getenv("DROPBOX_APP_SECRET")
                        if not app_key or not app_secret:
                            logger.error(f"Missing app_key or app_secret for Dropbox bucket {bucket_number}")
                            continue
                        dbx = DropboxService(token_dir=self.token_dir, app_key=app_key, app_secret=app_secret)
                        if dbx.authenticate(bucket_number, self.user_id):
                            self.drives.append(dbx)
                            logger.info(f"Loaded Dropbox bucket {bucket_number} for user_id {self.user_id}")
                        else:
                            logger.error(f"Dropbox authentication failed for bucket {bucket_number}")
                    else:
                        logger.warning(f"Unknown drive type {drive_type} for bucket {bucket_number}")
                except Exception as e:
                    logger.error(f"Failed to load drive {drive_type} bucket {bucket_number}: {e}")
        except Exception as e:
            logger.error(f"Error querying drives_collection for user_id {self.user_id}: {e}")

    def add_drive(self, drive: Service, bucket_number: int, drive_type: str) -> None:
        """
        Add a new storage drive and save it to MongoDB.
        
        :param drive: The drive instance (GoogleDrive or DropboxService).
        :param bucket_number: Unique bucket number for the drive.
        :param drive_type: Type of drive ("GoogleDrive" or "Dropbox").
        """
        try:
            drive.authenticate(bucket_number, self.user_id)
            self.drives.append(drive)
            logger.info(f"{drive_type} bucket {bucket_number} added for user_id {self.user_id}")
    
            # Save to drives_collection
            db = Database().get_instance()
            db.drives_collection.update_one(
                {"user_id": ObjectId(self.user_id), "bucket_number": bucket_number},
                {
                    "$set": {
                        "user_id": ObjectId(self.user_id),
                        "type": drive_type,
                        "bucket_number": bucket_number,
                        "app_key": getattr(drive, "app_key", None) or os.getenv("DROPBOX_APP_KEY") if drive_type == "Dropbox" else None,
                        "app_secret": getattr(drive, "app_secret", None) or os.getenv("DROPBOX_APP_SECRET") if drive_type == "Dropbox" else None
                    }
                },
                upsert=True
            )
    
            # Update user's drives list in users_collection
            db.users_collection.update_one(
                {"_id": ObjectId(self.user_id)},
                {"$addToSet": {"drives": bucket_number}},
                upsert=True
            )
            logger.info(f"Saved {drive_type} bucket {bucket_number} to MongoDB")
        except Exception as e:
            logger.error(f"Error adding {drive_type} bucket {bucket_number}: {e}")
            raise

    def check_all_storages(self) -> Tuple[List[dict], float, float]:
        """
        Check storage usage across all drives and sort by free space.
        
        :return: Tuple of (storage_info, total_limit, total_usage).
        """
        self.sorted_buckets = []
        storage_info = []
        total_limit = 0.0
        total_usage = 0.0

        for index, drive in enumerate(self.drives):
            try:
                limit, usage = drive.check_storage()
                free = limit - usage
                total_limit += limit
                total_usage += usage
                if free > 0:
                    self.sorted_buckets.append((free, drive, index))
                storage_info.append({
                    "Drive Number": index + 1,
                    "Storage Limit (bytes)": limit / 1024**3,
                    "Used Storage (bytes)": usage / 1024**3,
                    "Free Storage": free / 1024**3,
                    "Provider": type(drive).__name__
                })
            except Exception as e:
                logger.error(f"Error checking storage for {type(drive).__name__} drive {index + 1}: {e}")

        self.sorted_buckets.sort(reverse=True, key=lambda x: x[0])
        logger.info(f"Checked storage for {len(self.drives)} drives, total_limit: {total_limit / 1024**3:.2f} GB")
        return storage_info, total_limit, total_usage

    def get_sorted_buckets(self) -> List[Tuple[float, Service, int]]:
        """
        Get the sorted list of buckets by free space.
        
        :return: List of tuples (free_space, drive, index).
        """
        return self.sorted_buckets

    def update_sorted_buckets(self) -> None:
        """
        Refresh the sorted buckets list based on current storage.
        """
        self.check_all_storages()

    def get_all_authenticated_buckets(self) -> List[str]:
        """
        Get all authenticated bucket numbers for the user.
        
        :return: List of bucket numbers as strings.
        """
        db = Database.get_instance()
        try:
            user_id_obj = ObjectId(self.user_id)
            logger.info(f"Querying drives_collection for user_id {self.user_id} (ObjectId: {user_id_obj})")
            drives = db.drives_collection.find({"user_id": user_id_obj})
            bucket_numbers = [str(drive["bucket_number"]) for drive in drives]
            logger.info(f"Found {len(bucket_numbers)} authenticated buckets for user_id {self.user_id}")
            return bucket_numbers
        except Exception as e:
            logger.error(f"Error retrieving authenticated buckets for user_id {self.user_id}: {e}")
            return []

    @staticmethod
    def parse_part_info(file_name: str) -> Tuple[Optional[str], Optional[int]]:
        """
        Extract base name and part number from split filenames.
        
        :param file_name: Name of the file.
        :return: Tuple of (base_name, part_number) or (None, None).
        """
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
                if pattern == patterns[1] and match.group(3):
                    base += match.group(3)
                elif pattern == patterns[3] and match.group(3):
                    base += match.group(3)
                try:
                    return base, int(part_num)
                except ValueError:
                    continue
        logger.debug(f"No part info parsed for file: {file_name}")
        return None, None

    def get_files_from_drive(self, drive: Service, query: Optional[str] = None) -> List[dict]:
        """
        Retrieve files from a single drive.
        
        :param drive: The drive instance.
        :param query: Optional search query.
        :return: List of file dictionaries.
        """
        try:
            files = drive.listFiles(query=query)
            logger.info(f"Retrieved {len(files)} files from {type(drive).__name__}")
            return files
        except Exception as e:
            logger.error(f"Error retrieving files from {type(drive).__name__}: {e}")
            return []

    def display_files(self, all_files: List[Tuple[str, str, str, str]], start_index: int, page_size: int) -> None:
        """
        Display a paginated list of files.
        
        :param all_files: List of tuples (name, provider, size, file_url).
        :param start_index: Starting index for pagination.
        :param page_size: Number of files per page.
        """
        print("\nFiles (Sorted Alphabetically):\n")
        for idx, (name, provider, size, file_url) in enumerate(all_files[start_index:start_index + page_size], start=start_index + 1):
            size_str = f"{float(size) / 1024 ** 2:.2f} MB" if size != "Unknown" and size else "Unknown size"
            print(f"{idx}. {name} ({provider}) - {size_str}")
            print(f"   URL: {file_url}\n")

    def paginate_files(self, all_files: List[Tuple[str, str, str, str]], page_size: int = 30) -> None:
        """
        Paginate and display files interactively.
        
        :param all_files: List of file tuples to display.
        :param page_size: Number of files per page.
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
        logger.info(f"Displayed {min(start_index, total_files)} of {total_files} files")

    def list_files_from_all_buckets(self, query: Optional[str] = None) -> None:
        """
        List files from all authenticated drives.
        
        :param query: Optional search query to filter files.
        """
        if not self.drives:
            print("No authenticated drives found. Please add a new bucket first.")
            logger.warning(f"No drives available for user_id {self.user_id}")
            return

        all_files = []
        seen_files = set()

        for drive in self.drives:
            files = self.get_files_from_drive(drive, query)
            for file in files:
                file_name = file.get("name", "Unknown")
                if file_name in seen_files:
                    continue
                file_size = file.get("size", "Unknown")
                file_path = file.get("path", "N/A")
                provider = type(drive).__name__
                all_files.append((file_name, provider, file_size, file_path))
                seen_files.add(file_name)

        if not all_files:
            print("No files found matching the query.")
            logger.info(f"No files found for query: {query}")
            return

        all_files.sort(key=lambda x: x[0])
        self.paginate_files(all_files)