import dropbox
import os

#Replace with your Dropbox access token
ACCESS_TOKEN = 'Insert_your_access_token_here'.strip()

#Downloading a file from Dropbox
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
        #Search and download a file
        file_name = input("Enter the file name (without extension) to search and download: ")
        search_and_download_file(file_name)

