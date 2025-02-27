import os
from drive_manager import DriveManager
from GoogleDriveService import GoogleDriveService
from GDriveFile import GoogleDriveFile
from DropboxService import DropboxService
from DropBoxFile import DropBoxFile

def setup_drive_manager():
    """Initialize and authenticate Google Drive and Dropbox accounts."""
    drive_manager = DriveManager(token_dir="tokens")

    # **Add Google Drive Accounts**
    for bucket_number in range(1, 3):
        google_drive_service = GoogleDriveService(token_dir="tokens", credentials_file="credentials.json")
        drive_manager.add_drive(google_drive_service, bucket_number)
    
    # **Add Dropbox Accounts**
    for bucket_number in range(3, 5):
        dropbox_service = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
        drive_manager.add_drive(dropbox_service, bucket_number)
    
    return drive_manager

def upload_file(drive_manager):
    """Handles file upload by selecting the best available storage."""
    sorted_buckets = drive_manager.get_sorted_buckets()
    if not sorted_buckets:
        print("\n❌ No drives with free space available.")
        return
    
    best_bucket = sorted_buckets[0][1]
    bucket_number = sorted_buckets[0][2]
    file_path = input("\n📂 Enter file path to upload: ").strip('"').strip("'")
    if not os.path.exists(file_path):
        print(f"\n❌ File not found: {file_path}")
        return
    
    file_name = os.path.basename(file_path)
    print(f"\nUploading '{file_name}' to {'Dropbox' if isinstance(best_bucket, DropboxService) else 'Google Drive'} (Bucket {bucket_number})...")
    
    try:
        if isinstance(best_bucket, DropboxService):
            dropbox_file = DropBoxFile(best_bucket.authenticate(bucket_number), drive_manager)
            dropbox_file.upload_file(file_path, file_name)
        elif isinstance(best_bucket, GoogleDriveService):
            gdrive_file = GoogleDriveFile(drive_manager, best_bucket)
            gdrive_file.upload_file(file_path, file_name, "application/octet-stream")
        print(f"\n✅ File '{file_name}' uploaded successfully.")
    except Exception as e:
        print(f"\n❌ Error uploading file: {e}")

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n" + "=" * 50)
    print(f"{'WELCOME TO SYNCLY! 💀':^50}")
    print("=" * 50)
    
    drive_manager = setup_drive_manager()
    
    while True:
        # **Check total storage for all services**
        _, total_limit, total_usage, _ = drive_manager.check_all_storages()

        # **Display total storage info**
        print("\n" + "=" * 50)
        print(f"{'💾 STORAGE SUMMARY 💾':^50}")
        print("=" * 50)
        print(f"Total Storage: {round(total_limit / 1024**3, 2)} GB")
        print(f"Used Space: {round(total_usage / 1024**3, 2)} GB")
        print(f"Free Space: {round((total_limit - total_usage) / 1024**3, 2)} GB")

        # **Display storage as a progress bar**
        if total_limit > 0:
            percent_used = (total_usage / total_limit) * 100
            bar_length = 40
            filled_length = int(bar_length * percent_used / 100)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            print(f"[{bar}] {percent_used:.1f}%")
        
        # **Display menu**
        print("\n" + "=" * 50)
        print(f"{'SYNCLY MENU':^50}")
        print("=" * 50)
        print("1: 📁 View All Files")
        print("2: ⬆️ Upload File")
        print("3: ⬇️ Download File")
        print("4: ➕ Add New Bucket")
        print("5: 🚪 Exit")
        print("=" * 50)
        
        choice = input("\nChoose an option (1-5): ").strip()
        
        if choice == "1":
            print("\n📁 FILES ACROSS ALL STORAGE SERVICES")
            print("=" * 50)
            drive_manager.list_files_from_all_buckets()
            input("\nPress Enter to continue...")
        elif choice == "2":
            upload_file(drive_manager)
            input("\nPress Enter to continue...")
        elif choice == "5":
            print("\n" + "=" * 50)
            print(f"{'Thank you for using Syncly! 🤠':^50}")
            print("=" * 50)
            break
        else:
            print("\n❌ Invalid choice. Please enter a number between 1-5.")
            input("\nPress Enter to continue...")
        
        os.system('cls' if os.name == 'nt' else 'clear')

if __name__ == "__main__":
    main()