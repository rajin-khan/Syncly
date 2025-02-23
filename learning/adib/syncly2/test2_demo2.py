from DriveManager import DriveManager
from Dropbox import DropboxService
from DropBoxFile import DropBoxFile
from GoogleDrive import GoogleDrive
from GDriveFile import GoogleDriveFile
import os

# Initialize DriveManager
drive_manager = DriveManager(token_dir="tokens")

# **Add Google Drive Accounts**
google_drive1 = GoogleDrive(token_dir="tokens", credentials_file="credentials.json")
drive_manager.add_drive(google_drive1, bucket_number=3)

google_drive2 = GoogleDrive(token_dir="tokens", credentials_file="credentials.json")
drive_manager.add_drive(google_drive2, bucket_number=4)

# **Add Dropbox Accounts**
dropbox_service1 = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
drive_manager.add_drive(dropbox_service1, bucket_number=1)

dropbox_service2 = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
drive_manager.add_drive(dropbox_service2, bucket_number=2)

# **Check storage for all services**
storages, limit, usage = drive_manager.check_all_storages()

# Print storage details
for storage in storages:
    print(f"{storage['Provider']} - Drive {storage['Drive Number']}:")
    print(f"  - Storage Limit: {storage['Storage Limit (bytes)']:.2f} GB")
    print(f"  - Used Storage: {storage['Used Storage (bytes)']:.2f} GB")
    print(f"  - Free Storage: {storage['Free Storage']:.2f} GB")
    print("-" * 30)

# **Print Total Storage**
print("Storage Details")
print("-" * 30)
print(f"Total Storage: {round(limit / 1024**3, 2)} GB")
print(f"Used Space: {round(usage / 1024**3, 2)} GB")
print(f"Free Space: {round((limit - usage) / 1024**3, 2)} GB")

# **Get the sorted list of buckets (by free space, descending)**
sorted_buckets = drive_manager.get_sorted_buckets()
print("Sorted Buckets:", sorted_buckets)

# **Check if there's available space**
if not sorted_buckets:
    print("No drives with free space available.")
else:
    # Select the drive with the most free space
    best_bucket = sorted_buckets[0][1]  # Get the drive instance
    bucket_number = sorted_buckets[0][2]  # Get the bucket number
    print(f"Selected drive with the most free space: Bucket {bucket_number}")

    # **Upload file to the best available drive**
    file_path = input("File path: ").strip()  # User inputs the file path
    file_name = os.path.basename(file_path)  # Extract file name

    try:
        if isinstance(best_bucket, DropboxService):
            # **Upload to Dropbox**
            access_token = best_bucket.client._oauth2_access_token
            dropbox_file = DropBoxFile(access_token, drive_manager)
            dropbox_file.upload_file(file_path, file_name)
            print(f"File '{file_name}' uploaded to Dropbox (Bucket {bucket_number}).")

        elif isinstance(best_bucket, GoogleDrive):
            # **Upload to Google Drive**
            gdrive_file = GoogleDriveFile(drive_manager)
            gdrive_file.upload_file(file_path, file_name, "application/octet-stream")
            print(f"File '{file_name}' uploaded to Google Drive (Bucket {bucket_number}).")

        else:
            print(f"Unsupported drive type: {type(best_bucket).__name__}")

    except Exception as e:
        print(f"Error uploading file: {e}")
