import os
from DriveManager import DriveManager
from GoogleDrive import GoogleDrive
from GDriveFile import GoogleDriveFile
from Dropbox import DropboxService
from DropBoxFile import DropBoxFile

def setup_drive_manager():
    """Initialize and authenticate Google Drive and Dropbox accounts."""
    drive_manager = DriveManager(token_dir="tokens")

    # **Add Two Google Drive Accounts**
    google_drive_1 = GoogleDrive(token_dir="tokens", credentials_file="credentials.json")
    google_drive_2 = GoogleDrive(token_dir="tokens", credentials_file="credentials.json")

    drive_manager.add_drive(google_drive_1, bucket_number=1)
    drive_manager.add_drive(google_drive_2, bucket_number=2)

    # **Add Two Dropbox Accounts**
    dropbox_service1 = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
    dropbox_service2 = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")

    drive_manager.add_drive(dropbox_service1, bucket_number=3)
    drive_manager.add_drive(dropbox_service2, bucket_number=4)

    return drive_manager

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

# **Main Execution**
if __name__ == "__main__":
    drive_manager = setup_drive_manager()
    file_to_find = input("Enter the file name to search: ").strip()
    search_and_download_file(drive_manager, file_to_find)
