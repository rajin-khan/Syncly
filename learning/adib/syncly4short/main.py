import os
from DriveManager import DriveManager
from GoogleDrive import GoogleDrive
from GDriveFile import GoogleDriveFile
from Dropbox import DropboxService
from DropBoxFile import DropBoxFile
from AuthManager import AuthManager
from Database import Database

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
        file_path = input("File path: ").strip('"').strip("'")  # User inputs the file path
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
    auth_manager = AuthManager()

    print("WELCOME TO SYNCLY! <3")

    # User registration/login flow
    while True:
        print("\n1: Register\n2: Login\n3: Exit")
        choice = input("Choose option: ").strip()

        if choice == "1":
            # Register a new user
            username = input("Enter a username: ").strip()
            password = input("Enter a password: ").strip()
            user_id = auth_manager.register_user(username, password)
            if user_id:
                drive_manager = DriveManager(user_id=user_id, token_dir="tokens")
                break  # Proceed to the main menu after registration

        elif choice == "2":
            # Log in an existing user
            username = input("Enter your username: ").strip()
            password = input("Enter your password: ").strip()
            user_id = auth_manager.login_user(username, password)
            if user_id:
                drive_manager = DriveManager(user_id=user_id, token_dir="tokens")
                break  # Proceed to the main menu after login

        elif choice == "3":
            print("Thank you for using Syncly!")
            return  # Exit the program

        else:
            print("Invalid choice. Please try again.")

    # Main menu
    while True:
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
        print("\n1: View Files\n2: Upload File\n3: Download File\n4: Add New Bucket\n5: Exit")
        choice = input("Choose option: ").strip()

        if choice == "1":
            # View files across all buckets (Google Drive and Dropbox)
            drive_manager.list_files_from_all_buckets()
        elif choice == "2":
            upload_file(drive_manager)
        elif choice == "3":
            file_to_find = input("Enter the file name to search (with extension): ").strip('"').strip("'")
            save_path = input("Enter the folder path in which you want to save: ").strip('"').strip("'")
            search_and_download_file(drive_manager, file_to_find, save_path)
        elif choice == "4":
            # Add a new bucket (Google Drive or Dropbox)
            bucket_type = input("Enter bucket type (1: Google Drive, 2: Dropbox): ").strip()
            bucket_number = len(drive_manager.get_all_authenticated_buckets()) + 1

            try:
                if bucket_type == "1":
                    # Add a new Google Drive bucket
                    google_drive_instance = GoogleDrive()
                    drive_manager.add_drive(google_drive_instance, bucket_number, drive_type="GoogleDrive")
                    print(f"Google Drive bucket {bucket_number} added successfully.")
                elif bucket_type == "2":
                    # Add a new Dropbox bucket
                    dropbox_service_instance = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
                    drive_manager.add_drive(dropbox_service_instance, bucket_number, drive_type="Dropbox")
                    print(f"Dropbox bucket {bucket_number} added successfully.")
                else:
                    print("Invalid bucket type. Please choose 1 for Google Drive or 2 for Dropbox.")

                # Verify that the drives field is updated in the users_collection
                db = Database().get_instance()
                user_data = db.users_collection.find_one({"_id": drive_manager.user_id})  # Use user_id (ObjectId)
                if user_data and "drives" in user_data:
                    print(f"Updated drives list: {user_data['drives']}")
                else:
                    print("Drives list not updated in the database.")
            except Exception as e:
                print(f"Error adding new bucket: {e}")
        elif choice == "5":
            print("Thank you for using Syncly!")
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()