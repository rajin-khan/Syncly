import os
from GDriveFile import GoogleDriveFile
from DropBoxFile import DropBoxFile
from DriveManager import DriveManager
from GoogleDrive import GoogleDrive
from Dropbox import DropboxService



def main():
    print("Syncly Demo 1")
    while True:
        print("\n-------------Storage Details-------------")
        print(drive_manager.check_all_storages())  # Check storage for all buckets (Google Drive and Dropbox)
        print("-------------------------------------------")
        print("\n1: View Files\n2: Search\n3: Add Bucket\n4: Upload\n5: Download\n6: Exit")
        choice = input("Choose option: ").strip()

        if choice == "1":
            # View files across all buckets (Google Drive and Dropbox)
            drive_manager.list_files_from_all_buckets()

        elif choice == "2":
            # Search files across all buckets (Google Drive and Dropbox)
            query = input("Enter search keyword: ").strip()
            if query:
                print("\nSearching in Google Drive...")
                gdrive_file.search_file(query)
                print("\nSearching in Dropbox...")
                dropbox_file.search_file(query)
            else:
                print("Please enter a valid search query.")

        elif choice == "3":
            # Add a new bucket (Google Drive or Dropbox)
            bucket_type = input("Enter bucket type (1: Google Drive, 2: Dropbox): ").strip()
            bucket_number = len(drive_manager.get_all_authenticated_buckets()) + 1

            if bucket_type == "1":
                # Add a new Google Drive bucket
                google_drive_instance = GoogleDrive()
                drive_manager.add_drive(google_drive_instance, bucket_number)
                print(f"Google Drive bucket {bucket_number} added successfully.")
            elif bucket_type == "2":
                # Add a new Dropbox bucket
                dropbox_service_instance = DropboxService(token_dir="tokens", app_key="iekqmer228dhy6r", app_secret="t06d75xw4viyrbu")
                drive_manager.add_drive(dropbox_service_instance, bucket_number)
                print(f"Dropbox bucket {bucket_number} added successfully.")
            else:
                print("Invalid bucket type. Please choose 1 for Google Drive or 2 for Dropbox.")

        elif choice == "4":
            # Ask the user where they want to upload the file
            upload_location = input("Where do you want to upload the file? (1: Google Drive, 2: Dropbox): ").strip()

            if upload_location not in ["1", "2"]:
                print("Invalid choice. Please choose 1 for Google Drive or 2 for Dropbox.")
                continue

            # Get the file path and validate it
            file_path = input("File path: ").strip()
            if not os.path.exists(file_path):
                print("File not found. Please check the file path.")
                continue

            file_name = os.path.basename(file_path)
            mimetype = "application/octet-stream"

            # Check if the file is small enough to fit in a single bucket
            """file_size = os.path.getsize(file_path)
            sorted_buckets = drive_manager.get_sorted_buckets()
            total_free = sum(bucket[0] for bucket in sorted_buckets)

            if total_free < file_size:
                print("Not enough space across all buckets.")
                continue"""

            # Upload to the selected service
            if upload_location == "1":
                # Upload to Google Drive
                print("Uploading to Google Drive...")
                gdrive_file.upload_file(file_path, file_name, mimetype)
            elif upload_location == "2":
                # Upload to Dropbox
                print("Uploading to Dropbox...")
                dropbox_file.upload_file(file_path, file_name, mimetype)

        elif choice == "5":
            # Download a file by searching across all buckets (Google Drive and Dropbox)
            file_name = input("Enter file name to download (without extension): ").strip()
            save_path = input("Enter save path (default: downloads): ").strip()

            # Remove quotation marks from the save path
            save_path = save_path.strip('"').strip("'")
            if not save_path:  # Default save path
                save_path = "downloads"

            # Search and download from Google Drive
            print("\nSearching in Google Drive...")
            gdrive_file.download_from_all_buckets(file_name, save_path)

            # Search and download from Dropbox
            print("\nSearching in Dropbox...")
            dropbox_file.download_and_merge_chunks(file_name, save_path)

        elif choice == "6":
            print("Thank you for using Syncly!")
            break

        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
