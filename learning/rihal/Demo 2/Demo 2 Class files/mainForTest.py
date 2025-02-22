import os
from GDriveFile import GoogleDriveFile
from DriveManager import DriveManager
from google_drive import GoogleDrive

def main():
    print("Syncly Demo 1")
    
    # Create DriveManager and GoogleDriveFile instances
    drive_manager = DriveManager()
    gdrive_file = GoogleDriveFile(drive_manager)

    # Add a googleDrive instance to DriveManager
    google_drive_instance = GoogleDrive()
    drive_manager.add_drive(google_drive_instance, bucket_number=1)  # Add bucket 1

    while True:
            print("\n-------------Storage Details-------------")
            drive_manager.check_all_storages()
            print("-------------------------------------------")
            print("\n1: View Files\n2: Search\n3: Add Bucket\n4: Upload\n5: Download\n6: Exit")
            choice = input("Choose option: ").strip()
            if choice == "1":
                drive_manager.list_files_from_all_buckets()
            elif choice == "2":
                gdrive_file.search_file()
            elif choice == "3":
                bucket_number = len(drive_manager.get_all_authenticated_buckets()) + 1
                google_drive_instance = GoogleDrive()       #Create a new googleDrive instance
                drive_manager.add_drive(google_drive_instance, bucket_number)       #Add the new bucket
            elif choice == "4":
                file_path = input("File path: ").strip()
                gdrive_file.upload_file(file_path, os.path.basename(file_path), "application/octet-stream")
            elif choice == "5":
                #Download
                file_name = input("Enter file name to download (without extension): ").strip()
                save_path = input("Enter save path (default: downloads): ").strip()
                
                #Remove quotation marks from the save path
                save_path = save_path.strip('"').strip("'")
                
                if not save_path:  # Default save path
                    save_path = "downloads"
                
                gdrive_file.download_from_all_buckets(file_name, save_path)
            elif choice == "6":
                print("Thank you for using Syncly!")
                break
            else:
                print("Invalid choice.")
      
if __name__ == "__main__":
    main()
