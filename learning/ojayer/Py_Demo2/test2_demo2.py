from DriveManager import DriveManager
from Dropbox import DropboxService
from DropBoxFile import DropBoxFile
from GoogleDrive import GoogleDrive
from GDriveFile import GoogleDriveFile
import os

# Initialize DriveManager
drive_manager = DriveManager(token_dir="tokens")

# Add Google Drive accounts
drive_manager.add_drive(GoogleDrive(), bucket_number=1)
drive_manager.add_drive(GoogleDrive(), bucket_number=2)
drive_manager.add_drive(GoogleDrive(), bucket_number=3)

# Add Dropbox accounts
dropbox_service1 = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
drive_manager.add_drive(dropbox_service1,bucket_number=4)

dropbox_service2 = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
drive_manager.add_drive(dropbox_service2,bucket_number=5)

# Check storage for all services
storages, limit, usage = drive_manager.check_all_storages()

# Print results
for storage in storages:
    print(f"{storage['Provider']} - Drive {storage['Drive Number']}:")
    print(f"  - Storage Limit: {storage['Storage Limit (bytes)']:.2f} GB")
    print(f"  - Used Storage: {storage['Used Storage (bytes)']:.2f} GB")
    print(f"  - Free Storage: {storage['Free Storage']:.2f} GB")
    print(f"  - Provider: {storage['Provider']}")
    print("-" * 30)

# Print Total Storage
print("Storage Details")
print("-" * 30)
print(f"Total Storage: {round(limit/1024**3, 2)} GB")
print(f"Used Space: {round(usage/1024**3, 2)} GB")
print(f"Free Space: {round((limit-usage)/1024**3, 2)} GB")

# Get the sorted list of buckets (sorted by free space in descending order)
sorted_buckets = drive_manager.get_sorted_buckets()
print("Sorted Buckets:", sorted_buckets)

# Check if there are any drives with free space
if not sorted_buckets:
    print("No drives with free space available.")
else:
    # Select the drive with the most free space
    best_bucket = sorted_buckets[0][1]  # Get the drive instance
    print(f"Selected drive with the most free space: Bucket {sorted_buckets[0][1]}")

    # Upload the file to the selected drive
    file_path = "F:/CSE327/SOFA-LIVER ss.PNG"  # Path to the file you want to upload
    file_name = "SOFA-LIVER ss.PNG"  # Name of the file on the drive
    mimetype = "application-stream"  # MIME type of the file

    try:
        if isinstance(best_bucket, DropboxService):
            # Initialize DropBoxFile with the access token from the selected drive
            ACCESS_TOKEN = best_bucket.client._oauth2_access_token
            dropbox_file = DropBoxFile(ACCESS_TOKEN, drive_manager)
            dropbox_file.upload_file(file_path, file_name, mimetype)
            print(f"File '{file_name}' uploaded to Dropbox bucket {best_bucket}.")
        elif isinstance(best_bucket, GoogleDrive):
            # Upload to Google Drive
            gdrive_file = GoogleDriveFile(drive_manager)
            file_path = input("File path: ").strip()
            gdrive_file.upload_file(file_path, os.path.basename(file_path), "application/octet-stream")
            print(f"File '{file_name}' uploaded to Google Drive bucket {sorted_buckets[0][2]}.")
        else:
            print(f"Unsupported drive type: {type(best_bucket).__name__}")
    except Exception as e:
        print(f"Error uploading file: {e}")