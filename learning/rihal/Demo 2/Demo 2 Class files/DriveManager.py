import os
from service import service
from google_drive import GoogleDrive
import re

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
        self.sorted_buckets = []
        storage_info = []
        total_limit = 0
        total_usage = 0
        for index, drive in enumerate(self.drives):
            limit, usage = drive.check_storage()
            free = limit-usage
            if(free>0):
                self.sorted_buckets.append((free,self.drives))
            total_limit+=limit
            total_usage+=usage
            storage_info.append({
                "Drive Number": index + 1,
                "Storage Limit (bytes)": limit/1024**3,
                "Used Storage (bytes)": usage/1024**3,
                "Free Storage": (limit - usage)/1024**3,
                "Provider": type(drive).__name__
            })
        self.sorted_buckets.sort(reverse=True,key=lambda x:x[0])
        return storage_info, total_limit, total_usage
    
    def get_sorted_buckets(self):
        """
        Return the sorted list of buckets with the most free space.
        """
        return self.sorted_buckets

    def update_sorted_buckets(self):
        """
        Update the sorted list of buckets based on current storage status.
        """
        self.check_all_storages()

    #Retrieves all authenticated bucket numbers from stored tokens.
    def get_all_authenticated_buckets(self):
        return [
            f.replace(".json", "").replace("bucket_", "")
            for f in os.listdir(self.token_dir)
            if f.startswith("bucket_") and f.endswith(".json")
        ]


    #Retrieving the exact files using the exact file names
    @staticmethod
    def parse_part_info(file_name):
        #Extract base name and part number from split filenames with improved regex.
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
                #Handle different pattern groups
                if pattern == patterns[1] and match.group(3):
                    base += match.group(3) if match.group(3) else ''
                elif pattern == patterns[3] and match.group(3):
                    base += match.group(3)
                try:
                    return base, int(part_num)
                except ValueError:
                    continue
        return None, None

    #List files from all authenticated buckets, with optional search query.
    def list_files_from_all_buckets(self, query=None):
        bucket_numbers = self.get_all_authenticated_buckets()
        if not bucket_numbers:
            print("No authenticated buckets found. Please add a new bucket first.")
            return

        max_files = 100  # Default value
        if query:
            print(f"\nSearching for files containing: '{query}' across all buckets...")
        else:
            # Ask user for the number of files to retrieve
            print("\nHow many files would you like to retrieve? (More files take longer to retrieve)")
            print("1: ~ 50 files")
            print("2: ~ 100 files")
            print("3: ~ 500 files")
            print("4: All available files (Takes much longer)")

            choice = input("Enter a number (1-4): ").strip()

            if choice == "1":
                max_files = 50
            elif choice == "2":
                max_files = 100
            elif choice == "3":
                max_files = 500
            elif choice == "4":
                max_files = None  # Fetch all files
                print("\nFetching all available files....")
            else:
                print("Invalid choice. Defaulting to 100 files.")
                max_files = 100

        all_files = []
        seen_files = set()  # Track files to avoid duplicates

        for bucket in bucket_numbers:
            try:
                # Use the googleDrive class to authenticate and list files
                drive = next((d for d in self.drives if isinstance(d, GoogleDrive)), None)
                if not drive:
                    print(f"No googleDrive instance found for bucket {bucket}.")
                    continue

                drive.authenticate(bucket)
                files = drive.listFiles(max_results=max_files, query=query)
                for file in files:
                    file_id = file['id']
                    file_name = file['name']
                    mime_type = file.get('mimeType', 'Unknown')
                    size = file.get('size', 'Unknown')
                    file_url = f"https://drive.google.com/file/d/{file_id}/view"  # Generate Google Drive file URL

                    # Check if the file is part of a split file
                    base_name, part_num = self.parse_part_info(file_name)
                    if base_name:
                        if part_num == 0:  # Only include part0
                            if base_name not in seen_files:  # Avoid duplicates
                                all_files.append((file_name, file_id, mime_type, size, file_url))
                                seen_files.add(base_name)
                    else:
                        # Include non-split files
                        all_files.append((file_name, file_id, mime_type, size, file_url))
            except Exception as e:
                print(f"Error retrieving files or storage details for bucket {bucket}: {e}")

        #Sort files alphabetically by name
        all_files.sort(key=lambda x: x[0])

        #Pagination
        page_size = 30
        total_files = len(all_files)
        start_index = 0

        while start_index < total_files:
            #Display paginated file results
            print("\nFiles (Sorted Alphabetically):\n")
            for idx, (name, file_id, mime_type, size, file_url) in enumerate(all_files[start_index:start_index + page_size], start=start_index + 1):
                size_str = f"{float(size) / 1024 ** 2:.2f} MB" if size != 'Unknown' else "Unknown size"
                print(f"{idx}. {name} ({mime_type}) - {size_str}")
                print(f"   Press here to view file: {file_url}\n")      #Display clickable link

            start_index += page_size        #Move to next batch of files

            if start_index < total_files:
                more = input("\nDo you want to see more files? (y/n): ").strip().lower()
                if more != 'y':
                    break
