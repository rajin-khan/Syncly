from DriveManager import DriveManager
from google_drive import googleDrive
from Dropbox import DropboxService
from DropBoxFile import DropBoxFile
# Initialize DriveManager
manager = DriveManager()

# Add Google Drive accounts
manager.add_drive(googleDrive(), bucket_number=1)
manager.add_drive(googleDrive(), bucket_number=2)
manager.add_drive(googleDrive(), bucket_number=3)

dropbox_service = DropboxService(app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
manager.add_drive(dropbox_service, bucket_number=4)

 # Check storage for all services
storages,limit,usage = manager.check_all_storages()
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
print(f"Total Storage: {round(limit/1024**3,2)} GB")
print(f"Used Space: {round(usage/1024**3,2)} GB")
print(f"Free Space: {round((limit-usage)/1024**3,2)} GB")


# Initialize DriveManager
drive_manager = DriveManager(token_dir="tokens")

# Example: Add a Dropbox drive (assuming 'service' is implemented for Dropbox)
dropbox_service = DropboxService(app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")  # Replace with actual Dropbox service initialization
bucket_number = 4  # Bucket number for this drive
drive_manager.add_drive(dropbox_service, bucket_number)

# Authenticate Dropbox
try:
    dropbox_service.authenticate(bucket_number)
except Exception as e:
    print(f"Failed to authenticate Dropbox: {e}")
    exit(1)

# Check storage usage for all drives
storage_info, total_limit, total_usage = drive_manager.check_all_storages()
print("Storage Info:")
for info in storage_info:
    print(info)
print(f"Total Limit: {total_limit / 1024**3} GB, Total Usage: {total_usage / 1024**3} GB")

# Initialize DropBoxFile with the DriveManager instance
ACCESS_TOKEN = dropbox_service.client._oauth2_access_token  # Get the access token from the authenticated client
dropbox_file = DropBoxFile(ACCESS_TOKEN, drive_manager)

# Example file details
file_path = "F:/CSE327/tokens/merged_file.csv"  # Path to the file you want to upload
file_name = "merged_file.csv"  # Name of the file on Dropbox
mimetype = "application-stream"  # MIME type of the file

# Upload a file to Dropbox
try:
    dropbox_file.upload_file(file_path, file_name, mimetype)
except Exception as e:
    print(f"Error uploading file: {e}")

# Download a file from Dropbox
dropbox_file_path = "/FileHandling_Algorithm.png"  # Path to the file on Dropbox
save_path = "F:/CSE327/tokens/downloaded_file.png"  # Local path to save the downloaded file
try:
    dropbox_file.download_file(dropbox_file_path, save_path)
except Exception as e:
    print(f"Error downloading file: {e}")

# Search for a file on Dropbox
search_query = "FileHandling_Algorithm"  # File name to search for
try:
    found_file_path = dropbox_file.search_file(search_query)
    if found_file_path:
        print(f"File found at: {found_file_path}")
    else:
        print("File not found.")
except Exception as e:
    print(f"Error searching file: {e}")
