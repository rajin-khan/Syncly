#--- START OF FILE DriveManager.py ---

import os
import re
from Service import Service
from Database import Database
from GoogleDrive import GoogleDrive
from Dropbox import DropboxService
from AuthManager import AuthManager
import logging # Added logging
from typing import List, Dict, Optional # Added typing imports

logger = logging.getLogger(__name__) # Added logger

class DriveManager:
    def __init__(self, user_id, token_dir="tokens"):
        self.user_id = user_id
        self.drives: List[Service] = [] # Added type hint
        self.token_dir = token_dir
        self.sorted_buckets = []
        os.makedirs(self.token_dir, exist_ok=True)
        # AuthManager is generally not needed directly here after initialization,
        # as authentication happens when loading drives.
        # self.auth_manager = AuthManager(user_id, token_dir)
        self.load_user_drives()

    def load_user_drives(self):
        """Loads and authenticates drives associated with the user_id."""
        db = Database().get_instance()
        user_drives = db.drives_collection.find({"user_id": self.user_id})
        loaded_drives_count = 0
        for drive_data in user_drives:
            drive_instance = None
            try:
                bucket_num = drive_data['bucket_number']
                drive_type = drive_data['type']
                logger.info(f"Loading drive: Type={drive_type}, Bucket={bucket_num} for User ID: {self.user_id}")

                if drive_type == 'GoogleDrive':
                    gd = GoogleDrive(token_dir=self.token_dir, credentials_file="credentials.json")
                    # Authentication happens here
                    if gd.authenticate(bucket_num, self.user_id):
                         drive_instance = gd
                    else:
                         logger.error(f"Failed to authenticate GoogleDrive Bucket {bucket_num} for User ID: {self.user_id}")

                elif drive_type == 'Dropbox':
                    # Ensure app_key and app_secret are present
                    app_key = drive_data.get('app_key')
                    app_secret = drive_data.get('app_secret')
                    if not app_key or not app_secret:
                        logger.error(f"Dropbox Bucket {bucket_num} for User ID: {self.user_id} is missing app_key or app_secret in database.")
                        continue # Skip this drive

                    dbx = DropboxService(token_dir=self.token_dir, app_key=app_key, app_secret=app_secret)
                     # Authentication happens here
                    if dbx.authenticate(bucket_num, self.user_id):
                         drive_instance = dbx
                    else:
                         logger.error(f"Failed to authenticate Dropbox Bucket {bucket_num} for User ID: {self.user_id}")

                else:
                     logger.warning(f"Unknown drive type '{drive_type}' found for user {self.user_id}, bucket {bucket_num}")

                if drive_instance:
                    self.drives.append(drive_instance)
                    loaded_drives_count += 1
                    logger.info(f"Successfully loaded and authenticated {drive_type} Bucket {bucket_num}")

            except KeyError as e:
                 logger.error(f"Missing expected key {e} in drive data for user {self.user_id}: {drive_data}")
            except Exception as e:
                logger.error(f"Error loading drive for user {self.user_id}, data {drive_data}: {e}", exc_info=True)

        logger.info(f"Finished loading drives for User ID: {self.user_id}. Total loaded: {loaded_drives_count}")


    def add_drive(self, drive: Service, bucket_number, drive_type):
        """
        Adds a storage service dynamically and saves it to the database.
        """
        try:
            # Authenticate the drive - this might involve user interaction
            if not drive.authenticate(bucket_number, self.user_id):
                logger.error(f"Failed to authenticate {drive_type} for bucket {bucket_number}.")
                # Depending on the flow, you might raise an error or return a failure status
                raise Exception(f"Authentication failed for {drive_type}")

            # Add only if authentication was successful
            self.drives.append(drive)
            logger.info(f"{type(drive).__name__} added successfully as bucket {bucket_number}.")

            # Save the drive metadata to the database
            db = Database().get_instance()
            drive_meta = {
                "user_id": self.user_id,
                "type": drive_type,
                "bucket_number": bucket_number,
            }
            # Include app keys only for Dropbox
            if isinstance(drive, DropboxService):
                drive_meta["app_key"] = getattr(drive, 'app_key', None)
                drive_meta["app_secret"] = getattr(drive, 'app_secret', None)

            db.drives_collection.insert_one(drive_meta)

            # Update the user's drives list in MongoDB
            # This might be redundant if drives_collection is the source of truth
            # Consider if users_collection.drives is still needed
            # db.users_collection.update_one(
            #     {"_id": self.user_id},
            #     {"$addToSet": {"drives": bucket_number}},
            #     upsert=False # Don't create user here
            # )
            # logger.info(f"Drive {bucket_number} added to user {self.user_id}'s record.")

        except Exception as e:
            logger.error(f"Error adding drive {drive_type} bucket {bucket_number}: {e}", exc_info=True)
            raise # Re-raise the exception to be handled by the caller (e.g., the API endpoint)


    def check_all_storages(self):
        """
        Checks storage usage for all drives and sorts them by free space.
        :return: A tuple containing storage info, total limit, and total usage.
        """
        self.sorted_buckets = []  # Reset the sorted_buckets list
        storage_info = []
        total_limit = 0
        total_usage = 0
        logger.info(f"Checking storage for {len(self.drives)} drives for user {self.user_id}")
        for index, drive in enumerate(self.drives):
            try:
                limit, usage = drive.check_storage()
                free = limit - usage
                # Ensure drive object is valid before adding
                if hasattr(drive, 'service') and drive.service: # Basic check if drive is authenticated/valid
                    if free >= 0: # Allow storing even if full, just sort order changes
                        self.sorted_buckets.append((free, drive, index))
                    provider_name = type(drive).__name__
                else:
                    provider_name = f"{type(drive).__name__} (Unauthenticated?)"
                    limit, usage, free = 0, 0, 0 # Assume zero storage if not authenticated
                    logger.warning(f"Drive at index {index} ({provider_name}) seems unauthenticated. Skipping detailed storage check.")


                total_limit += limit
                total_usage += usage
                storage_info.append({
                    "Drive Number": index + 1,
                    "Storage Limit (bytes)": limit / 1024**3 if limit else 0,
                    "Used Storage (bytes)": usage / 1024**3 if usage else 0,
                    "Free Storage": free / 1024**3 if free else 0,
                    "Provider": provider_name
                })
            except Exception as e:
                 logger.error(f"Error checking storage for drive at index {index} ({type(drive).__name__}): {e}", exc_info=True)
                 # Add placeholder info if a specific drive check fails
                 storage_info.append({
                     "Drive Number": index + 1,
                     "Storage Limit (bytes)": 0, "Used Storage (bytes)": 0, "Free Storage": 0,
                     "Provider": f"{type(drive).__name__} (Error)"
                 })


        # Sort buckets by free space in descending order
        self.sorted_buckets.sort(reverse=True, key=lambda x: x[0])
        logger.info(f"Storage check complete. Total Limit: {total_limit}, Total Usage: {total_usage}")
        return storage_info, total_limit, total_usage

    def get_sorted_buckets(self):
        """
        Returns the sorted list of buckets with the most free space. Re-checks if list is empty.
        """
        # Re-check storage if the list is empty or seems outdated
        if not self.sorted_buckets:
             logger.info("Sorted buckets list is empty, re-checking storage.")
             self.check_all_storages()
        return self.sorted_buckets

    def update_sorted_buckets(self):
        """
        Updates the sorted list of buckets based on current storage status.
        """
        self.check_all_storages()

    def get_all_authenticated_buckets(self):
        """
        Retrieves all authenticated bucket numbers for the current user from the database.
        This might be less reliable than checking loaded self.drives.
        """
        # Consider relying on self.drives which holds authenticated instances
        # return [i+1 for i, drive in enumerate(self.drives) if hasattr(drive, 'service') and drive.service]

        # Original DB query method (might include unauthenticated drives if token exists but fails refresh)
        db = Database().get_instance()
        tokens = db.tokens_collection.find({"user_id": self.user_id})
        authenticated_buckets = [str(token["bucket_number"]) for token in tokens]
        return authenticated_buckets

    @staticmethod
    def parse_part_info(file_name):
        """
        Extract base name and part number from split filenames with improved regex.
        """
        # This method seems related to file splitting, which is not the focus of Step B. Keeping it as is.
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

    def get_files_from_drive(self, drive: Service, query: Optional[str]):
        """
        Retrieve files from a single drive based on the query (for listing).
        Uses listFiles.
        """
        try:
            # This is used by list_files_from_all_buckets for the /list command
            return drive.listFiles(query=query)
        except Exception as e:
            logger.error(f"Error listing files from {type(drive).__name__}: {e}", exc_info=True)
            return []

    def search_files_in_drive(self, drive: Service, query: str, limit: int):
        """
        Retrieve files from a single drive based on the query (for searching).
        Uses searchFiles.
        """
        try:
            # This is the new method for targeted search for LLM context
            return drive.searchFiles(query=query, limit=limit)
        except Exception as e:
            logger.error(f"Error searching files in {type(drive).__name__}: {e}", exc_info=True)
            return []

    def display_files(self, all_files, start_index, page_size):
        """
        Display a paginated list of files (for CLI).
        """
        # This method is for the CLI (main.py) and not directly used by API/Bot for Step B. Keeping as is.
        print("\nFiles (Sorted Alphabetically):\n")
        for idx, (name, provider, size, file_url) in enumerate(all_files[start_index:start_index + page_size], start=start_index + 1):
            size_str = f"{float(size) / 1024 ** 2:.2f} MB" if isinstance(size, (int, float, str)) and size != 'Unknown' and str(size).isdigit() else "Unknown size"
            print(f"{idx}. {name} ({provider}) - {size_str}")
            print(f"   Press here to view file: {file_url}\n")

    def paginate_files(self, all_files, page_size=30):
        """
        Paginate and display files (for CLI).
        """
         # This method is for the CLI (main.py) and not directly used by API/Bot for Step B. Keeping as is.
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
        List files from all authenticated cloud services (for CLI).
        :param query: Optional simple name filter query.
        """
         # This method is for the CLI (main.py) and /list command. Uses listFiles. Keeping as is.
        if not self.drives:
            print("No authenticated drives found. Please add a new bucket first.")
            return

        all_files = []
        seen_files = set() # Using set for faster lookup

        # Collect files from all drives
        for drive in self.drives:
            # Use get_files_from_drive which calls listFiles
            files = self.get_files_from_drive(drive, query)
            for file_info in files:
                file_name = file_info.get("name", "Unknown")
                # Use a tuple of (name, provider) for uniqueness check if needed,
                # but simple name check might suffice for display listing.
                if file_name not in seen_files:
                    all_files.append((
                        file_name,
                        file_info.get("provider", type(drive).__name__),
                        file_info.get("size", "Unknown"),
                        file_info.get("path", "N/A")
                    ))
                    seen_files.add(file_name)

        # Sort files by name
        all_files.sort(key=lambda x: x[0].lower()) # Case-insensitive sort

        # Paginate and display files
        self.paginate_files(all_files)

    # --- New Method for LLM Context ---
    def search_files_for_llm(self, query: str, limit_per_drive: int = 5, total_limit: int = 10) -> List[Dict]:
        """
        Searches for files across all authenticated drives based on a query,
        intended for providing context to an LLM. Uses searchFiles.
        Returns a limited list of file metadata.
        """
        if not self.drives:
            logger.warning(f"No authenticated drives found for user {self.user_id} during LLM search.")
            return []

        all_found_files = []
        logger.info(f"Starting LLM file search for query '{query}' across {len(self.drives)} drives.")

        # Collect files from all drives using the searchFiles method
        for drive in self.drives:
            logger.debug(f"Searching in {type(drive).__name__}...")
            try:
                # Pass the query and a per-drive limit
                found_in_drive = self.search_files_in_drive(drive, query, limit_per_drive)
                if found_in_drive:
                     logger.info(f"Found {len(found_in_drive)} potential files in {type(drive).__name__}")
                     all_found_files.extend(found_in_drive) # Add provider info if not already present
                else:
                     logger.info(f"No files found matching query in {type(drive).__name__}")

            except Exception as e:
                logger.error(f"Error searching files for LLM context in {type(drive).__name__}: {e}", exc_info=True)

        # Optional: De-duplicate based on name and provider? For now, keep duplicates if they exist across providers.
        # Optional: Sort by relevance if search APIs provide scores, or by name/date. Sorting by name for consistency.
        all_found_files.sort(key=lambda x: x.get('name', '').lower())

        logger.info(f"Total files found across all drives before limit: {len(all_found_files)}")

        # Return the top N results overall
        return all_found_files[:total_limit]


# --- END OF FILE DriveManager.py ---