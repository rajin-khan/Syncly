from DriveManager import DriveManager
from google_drive import googleDrive
from Dropbox import DropboxService

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
