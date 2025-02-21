import dropbox
import os

#Replace with your Dropbox access token
ACCESS_TOKEN = 'Insert_Your_Access_Token'.strip()

def upload_file_to_dropbox(file_path, dropbox_path):
    #Initialize Dropbox client
    dbx = dropbox.Dropbox(ACCESS_TOKEN)

    try:
        #Open the file and upload it
        with open(file_path, 'rb') as f:
            dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
            print(f"File {file_path} uploaded to Dropbox as {dropbox_path}")
    except dropbox.exceptions.ApiError as err:
        print(f"API error: {err}")
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
    except Exception as e:
        print(f"Error uploading file: {e}")

def search_and_download_file(file_name):
    #Initialize Dropbox client
    dbx = dropbox.Dropbox(ACCESS_TOKEN)

    try:
        #Search for files in Dropbox
        result = dbx.files_search_v2("", file_name).matches

        if not result:
            print(f"No files found with the name '{file_name}'.")
            return

        #Iterate through search results
        for match in result:
            metadata = match.metadata
            if isinstance(metadata, dropbox.files.FileMetadata):
                #Check if the file name (without extension) matches the search term
                dbx_file_name = os.path.splitext(metadata.name)[0]
                if dbx_file_name.lower() == file_name.lower():
                    print(f"Found file: {metadata.name}")
                    #Download the file
                    download_path = f"./{metadata.name}"
                    with open(download_path, "wb") as f:
                        metadata, res = dbx.files_download(metadata.path_lower)
                        f.write(res.content)
                    print(f"File downloaded to: {download_path}")
                    return

        print(f"No exact match found for '{file_name}'.")
    except dropbox.exceptions.ApiError as err:
        print(f"API error: {err}")
    except Exception as e:
        print(f"Error downloading file: {e}")

#Main function
if __name__ == "__main__":
    while True:
        print("\n1. Upload a file to Dropbox")
        print("2. Search and download a file from Dropbox")
        print("3. Exit")
        choice = input("Enter your choice (1/2/3): ")

        if choice == "1":
            # Upload a file
            file_path = input("Enter the path to the file you want to upload: ")
            dropbox_path = input("Enter the Dropbox path (e.g., /folder/filename.txt): ")
            upload_file_to_dropbox(file_path, dropbox_path)
        elif choice == "2":
            # Search and download a file
            file_name = input("Enter the file name (without extension) to search and download: ")
            search_and_download_file(file_name)
        elif choice == "3":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")
