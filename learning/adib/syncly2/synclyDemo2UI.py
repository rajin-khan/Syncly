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

    drive_manager.add_drive(dropbox_service1, bucket_number=3)
    drive_manager.add_drive(dropbox_service2, bucket_number=4)

    return drive_manager

def upload_file(drive_manager):
    #**Get the sorted list of buckets (by free space, descending)**
    sorted_buckets = drive_manager.get_sorted_buckets()
    
    if not sorted_buckets:
        print("\n❌ No drives with free space available.")
        return
    
    # Select the drive with the most free space
    best_bucket = sorted_buckets[0][1]  # Get the drive instance
    bucket_number = sorted_buckets[0][2]  # Get the bucket number
    
    # Get file path from user
    file_path = input("\n📂 Enter file path to upload: ").strip('"').strip("'")
    if not os.path.exists(file_path):
        print(f"\n❌ File not found: {file_path}")
        return
        
    file_name = os.path.basename(file_path)  # Extract file name

    print(f"\nUploading '{file_name}' to {'Dropbox' if isinstance(best_bucket, DropboxService) else 'Google Drive'} (Bucket {bucket_number})...")
    
    try:
        if isinstance(best_bucket, DropboxService):
            # **Upload to Dropbox**
            access_token = best_bucket.client._oauth2_access_token
            dropbox_file = DropBoxFile(access_token, drive_manager)
            dropbox_file.upload_file(file_path, file_name)
            print(f"\n✅ File '{file_name}' uploaded to Dropbox (Bucket {bucket_number}).")

        elif isinstance(best_bucket, GoogleDrive):
            # **Upload to Google Drive**
            gdrive_file = GoogleDriveFile(drive_manager)
            gdrive_file.upload_file(file_path, file_name, "application/octet-stream")
            print(f"\n✅ File '{file_name}' uploaded to Google Drive (Bucket {bucket_number}).")

        else:
            print(f"\n❌ Unsupported drive type: {type(best_bucket).__name__}")

    except Exception as e:
        print(f"\n❌ Error uploading file: {e}")

def search_and_download_file(drive_manager, file_name=None, save_path=None):
    """
    Search for a file across all connected Google Drive and Dropbox accounts and download it.
    :param drive_manager: The DriveManager instance containing authenticated drives.
    :param file_name: The name of the file to search for.
    :param save_path: The directory to save the downloaded file.
    """
    if file_name is None:
        file_name = input("\n🔍 Enter the file name to search: ").strip('"').strip("'")
    
    if save_path is None:
        save_path = input("💾 Enter the folder path in which you want to save: ").strip('"').strip("'")
    
    os.makedirs(save_path, exist_ok=True)
    print(f"\nSearching for '{file_name}' across all drives...")

    # **Search in Google Drive accounts**
    google_drive = GoogleDriveFile(drive_manager)
    downloaded_file = google_drive.download_from_all_buckets(file_name, save_path)
    if downloaded_file:
        print(f"\n✅ File successfully downloaded from Google Drive: {downloaded_file}")
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
            print(f"\n✅ File successfully downloaded from Dropbox: {save_file_path}")
            return save_file_path

    print("\n❌ File not found in any connected storage.")
    return None

def main():
    """Main function to handle upload and download operations."""
    # Clear the terminal for a clean start
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("\n" + "=" * 50)
    print(f"{'WELCOME TO SYNCLY! ❤️':^50}")
    print("=" * 50)
    
    drive_manager = setup_drive_manager()
    
    while True:
        # **Check storage for all services**
        storages, limit, usage = drive_manager.check_all_storages()

        # Display only total storage info
        print("\n" + "=" * 50)
        print(f"{'💾 STORAGE SUMMARY 💾':^50}")
        print("=" * 50)
        print(f"Total Storage: {round(limit / 1024**3, 2)} GB")
        print(f"Used Space: {round(usage / 1024**3, 2)} GB")
        print(f"Free Space: {round((limit - usage) / 1024**3, 2)} GB")
        
        # Calculate percentage used for visual bar
        if limit > 0:
            percent_used = (usage / limit) * 100
            bar_length = 40
            filled_length = int(bar_length * percent_used / 100)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"[{bar}] {percent_used:.1f}%")
        
        # Display menu (without Add Bucket option)
        print("\n" + "=" * 50)
        print(f"{'SYNCLY MENU':^50}")
        print("=" * 50)
        print("1: 📁 View All Files")
        print("2: ⬆️ Upload File")
        print("3: ⬇️ Download File")
        print("4: 🚪 Exit")
        print("=" * 50)
        
        choice = input("\nChoose an option (1-4): ").strip()
        
        if choice == "1":
            # View files across all buckets (Google Drive and Dropbox)
            print("\n📁 FILES ACROSS ALL STORAGE SERVICES")
            print("=" * 50)
            drive_manager.list_files_from_all_buckets()
            input("\nPress Enter to continue...")
            
        elif choice == "2":
            upload_file(drive_manager)
            input("\nPress Enter to continue...")
            
        elif choice == "3":
            file_to_find = input("\n🔍 Enter the file name to search: ").strip('"').strip("'")
            save_path = input("💾 Enter the folder path in which you want to save: ").strip('"').strip("'")
            search_and_download_file(drive_manager, file_to_find, save_path)
            input("\nPress Enter to continue...")
            
        elif choice == "4":
            print("\n" + "=" * 50)
            print(f"{'Thank you for using Syncly! 🤠':^50}")
            print("=" * 50)
            break
            
        else:
            print("\n❌ Invalid choice. Please enter a number between 1-4.")
            input("\nPress Enter to continue...")
        
        # Clear the terminal for next iteration
        os.system('cls' if os.name == 'nt' else 'clear')

if __name__ == "__main__":
    main()