import os
from DriveManager import DriveManager
from GoogleDrive import GoogleDrive
from GDriveFile import GoogleDriveFile
from Dropbox import DropboxService
from DropBoxFile import DropBoxFile

def setup_drive_manager():
    """Initialize and authenticate Google Drive and Dropbox accounts."""
    drive_manager = DriveManager(token_dir="tokens")

    #**Add Two Google Drive Accounts**
    google_drive_1 = GoogleDrive(token_dir="tokens", credentials_file="credentials.json")
    google_drive_2 = GoogleDrive(token_dir="tokens", credentials_file="credentials.json")

    drive_manager.add_drive(google_drive_1, bucket_number=1)
    drive_manager.add_drive(google_drive_2, bucket_number=2)

    #**Add Two Dropbox Accounts**
    dropbox_service1 = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
    dropbox_service2 = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")

    drive_manager.add_drive(dropbox_service1, bucket_number=1)
    drive_manager.add_drive(dropbox_service2, bucket_number=2)

    return drive_manager

def upload_file(drive_manager):
    #**Get the sorted list of buckets (by free space, descending)**
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


def search_and_download_file(drive_manager, file_name, save_path="downloads"):
    """
    Search for a file across all connected Google Drive and Dropbox accounts and download it.
    :param drive_manager: The DriveManager instance containing authenticated drives.
    :param file_name: The name of the file to search for.
    :param save_path: The directory to save the downloaded file.
    """
    os.makedirs(save_path, exist_ok=True)

    # **Search in Google Drive accounts**
    google_drive = GoogleDriveFile(drive_manager)
    downloaded_file = google_drive.download_from_all_buckets(file_name, save_path)
    if downloaded_file:
        print(f"File successfully downloaded from Google Drive: {downloaded_file}")
        return downloaded_file

    # **Search in Dropbox accounts**
    dropbox_accounts = [drive for drive in drive_manager.drives if isinstance(drive, DropboxService)]
    
    for dropbox_service in dropbox_accounts:
        access_token = dropbox_service.client._oauth2_access_token
        dropbox_file = DropBoxFile(access_token, drive_manager)
        
        dropbox_file_path = dropbox_file.search_file(file_name)
        if dropbox_file_path:
            save_file_path = os.path.join(save_path, os.path.basename(dropbox_file_path))
            dropbox_file.download_file(dropbox_file_path, save_file_path)
            print(f"File successfully downloaded from Dropbox: {save_file_path}")
            return save_file_path

    print("File not found in any connected storage.")
    return None

def main():
    """Main function to handle upload and download operations."""
    drive_manager = setup_drive_manager()
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

    while True:
        print("\n1: Upload File\n2: Download File\n3: Exit")
        choice = input("Choose option: ").strip()

        if choice == "1":
            upload_file(drive_manager)
        elif choice == "2":
            file_to_find = input("Enter the file name to search: ").strip()
            search_and_download_file(drive_manager, file_to_find)
        elif choice == "3":
            print("Thank you for using Syncly!")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
