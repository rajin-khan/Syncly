import os
import io
import json
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

#load env variables
load_dotenv()

#api scope = read only
SCOPES = ['https://www.googleapis.com/auth/drive']

#get paths from env
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")  #default to "tokens" if not set
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")  #default to "credentials.json" if not set
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)  #ensure token dir exists

def authenticate_account(bucket_number):
    token_path = os.path.join(TOKEN_DIR, f"bucket_{bucket_number}.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.valid:
            return build("drive", "v3", credentials=creds)

    #re-auth tokens if needed
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    #saved creds
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)

# Upload a chunk to Google Drive
# def upload_to_drive(chunk, chunk_filename, folder_id):
#     bucket_number = len(get_all_authenticated_buckets()) + 1
#     service = authenticate_account(bucket_number)
#     file_metadata = {"name": chunk_filename, "parents": [folder_id] if folder_id else None}
#     media = MediaIoBaseUpload(io.BytesIO(chunk), mimetype="application/octet-stream")
#     file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
#     return file.get("id")

def list_drive_files(service, max_results=None, query=None):
    all_files = []
    page_token = None
    query_filter = f"name contains '{query}'" if query else None  #apply search filter if provided

    while True:
        results = service.files().list(
            pageSize=100,  #fetch 100 files per API request
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageToken=page_token,
            q=query_filter  #apply search filter
        ).execute()

        all_files.extend(results.get('files', []))

        #stop early if we reach the requested limit
        if max_results and len(all_files) >= max_results:
            return all_files[:max_results]

        page_token = results.get('nextPageToken')
        if not page_token:
            break  #no more pages left

    return all_files

def get_all_authenticated_buckets():
    return [f.replace(".json", "").replace("bucket_", "") for f in os.listdir(TOKEN_DIR) if f.startswith("bucket_")]

#function to check storage
def check_storage(service,bucket):
    try:
        res = service.about().get(fields='storageQuota').execute()
            
        limit = int(res['storageQuota']['limit'])
        usage = int(res['storageQuota']['usage'])
            
            
        #print(f"\n--- {bucket} ---")
        #print(f"Total: {round(limit / (1024**3))} GB")
        #print(f"Used: {round(usage / (1024**3))} GB")
            
    except Exception as e:
            print(f"Error for {bucket}: {e}")
    
    return limit,usage

def check_all_storage():
    total_storage = 0
    total_used = 0
    buckets = get_all_authenticated_buckets()
    if not buckets:
        print("No authenticated buckets found. Please add a new bucket first.")
        return
    for bucket in buckets:
        service = authenticate_account(bucket)
        #retrieve storage info from each bucket
        storage,used = check_storage(service,bucket)
        total_storage += storage
        total_used += used
    print(f"Total Storage: {round(total_storage / (1024**3), 2)} GB")
    print(f"Total Used: {round(total_used / (1024**3), 2)} GB")
    print(f"Total Free: {round((total_storage - total_used) / (1024**3), 2)} GB")
        


def list_files_from_all_buckets(query=None):
    bucket_numbers = get_all_authenticated_buckets()
    if not bucket_numbers:
        print("No authenticated buckets found. Please add a new bucket first.")
        return

    if query:
        print(f"\nSearching for files containing: '{query}' across all buckets...")
    else:
        #ask user for the number of files to retrieve
        print("\nHow many files would you like to retrieve? (More files take longer to retrieve)")
        print("1: ~ 50 files")
        print("2: ~ 100 files")
        print("3: ~ 500 files")
        print("4: All available files (Takes much longer)")

        choice = input("Enter a number (1-4): ").strip()

        if choice == "1":
            max_files = 50
        elif choice == "2":
            max_files = 100
        elif choice == "3":
            max_files = 500
        elif choice == "4":
            max_files = None  #fetch all files
            print("\nFetching all available files....")
        else:
            print("Invalid choice. Defaulting to 100 files.")
            max_files = 100
            
    max_files = None  #in search mode, fetch all matches

    all_files = []

    for bucket in bucket_numbers:
        try:
            service = authenticate_account(bucket)
            files = list_drive_files(service, max_files, query)  #retrieve user-defined limit or search query
            for file in files:
                all_files.append((file['name'], file['id'], file.get('mimeType', 'Unknown'), file.get('size', 'Unknown')))
        except Exception as e:
            print(f"Error retrieving files or storage details for a bucket: {e}")

    #sort files alphabetically by name
    all_files.sort(key=lambda x: x[0])

    #pagination
    page_size = 30
    total_files = len(all_files)
    start_index = 0

    while start_index < total_files:
        #display total storage info on every page
        # check_all_storage() 
        #display paginated file results
        print("\nFiles (Sorted Alphabetically):\n")
        for idx, (name, file_id, mime_type, size) in enumerate(all_files[start_index:start_index+page_size], start=start_index+1):
            size_str = f"{float(size)/1024**2:.2f} MB" if size != 'Unknown' else "Unknown size"
            print(f"{idx}. {name} ({mime_type}) - {size_str}")

        start_index += page_size  #move to next batch of files

        if start_index < total_files:
            more = input("\nDo you want to see more files? (y/n): ").strip().lower()
            if more != 'y':
                break



def upload_chunk(service, bucket_id, chunk_path, mimetype, file_name, chunk_index):
    """Upload a single chunk to Google Drive and return its file ID."""
    media = MediaFileUpload(chunk_path, mimetype=mimetype, resumable=True)
    file_metadata = {'name': f'{file_name}_part{chunk_index + 1}'}
    result = service.files().create(media_body=media, body=file_metadata).execute()
    file_id = result.get("id")
    print(f'Uploaded chunk {chunk_index + 1} of {file_name} to bucket {bucket_id}. File ID: {file_id}')
    return file_id

def upload_file(file_path, file_name, mimetype):
    """
    Upload the file to Google Drive, splitting it across buckets if necessary.
    Also writes metadata (filename, fileid, bucket) to metadata.json to track when
    and where each part was uploaded.
    """
    print("Entered upload function")
    file_size = os.path.getsize(file_path)
    buckets = get_all_authenticated_buckets()  # Replace with your actual function.
    free_space = []  # List of [free_bytes, bucket_identifier]
    print(f"File size = {file_size} bytes")
    total_free = 0
    # Check available storage on each bucket.
    for bucket in buckets:
        service = authenticate_account(bucket)  # Replace with your authentication function.
        total, used = check_storage(service,bucket)  # Replace with your storage-checking function.
        free = total - used
        total_free = total_free+ free
        if free > 0:
            free_space.append([free, bucket])
    if(total_free<file_size):
        print("Not Enough Space", free_space)
        return
    # Sort buckets so that the one with the most free space is first.
    free_space.sort(reverse=True, key=lambda x: x[0])
    print("Buckets and free space:", free_space)

    # This dictionary will hold the metadata.
    metadata = {
        "file_name": file_name,
        "chunks": []  # Each element will include: chunk_name, file_id, bucket.
    }

    # If the bucket with the most free space can hold the whole file, upload in one piece.
    if free_space[0][0] >= file_size:
        best_bucket = free_space[0][1]
        print(f"Uploading the whole file to bucket {best_bucket}.")
        service = authenticate_account(best_bucket)
        media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
        file_metadata = {'name': file_name}
        result = service.files().create(media_body=media, body=file_metadata).execute()
        file_id = result.get("id")
        print(f"Uploaded the whole file to bucket {best_bucket}. File ID: {file_id}")

        metadata["chunks"].append({
            "chunk_name": file_name,
            "file_id": file_id,
            "bucket": best_bucket
        })

        # Write the metadata to metadata.json.
        with open("metadata.json", "w") as meta_file:
            json.dump(metadata, meta_file, indent=4)
        return

    # Otherwise, perform chunked upload.
    offset = 0
    chunk_index = 0

    with open(file_path, "rb") as file:
        while offset < file_size:
            # Always sort free_space so that the bucket with the most free space is first.
            free_space.sort(reverse=True, key=lambda x: x[0])
            bucket_free, bucket_id = free_space[0]
            chunk_size = min(bucket_free, file_size - offset)
            print(f"Uploading chunk {chunk_index + 1} of size {chunk_size} bytes to bucket {bucket_id}.")

            # Read the next chunk_size bytes and write them to a temporary file.
            chunk_filename = f"{file_path}.part{chunk_index}"
            with open(chunk_filename, "wb") as chunk_file:
                chunk_file.write(file.read(chunk_size))

            service = authenticate_account(bucket_id)
            file_id = upload_chunk(service, bucket_id, chunk_filename, mimetype, file_name, chunk_index)
            metadata["chunks"].append({
                "chunk_name": f"{file_name}_part{chunk_index + 1}",
                "file_id": file_id,
                "bucket": bucket_id
            })

            # Update the available free space for the bucket we just used.
            free_space[0][0] -= chunk_size
            offset += chunk_size
            chunk_index += 1
            print(f"Uploaded {offset} of {file_size} bytes.")

    # Write the metadata file after all chunks have been uploaded.
    with open("metadata.json", "w") as meta_file:
        json.dump(metadata, meta_file, indent=4)
    print("Metadata written to metadata.json.")

#Download a file from Google Drive
def download_file(service, file_id, save_path):
    try:
        request = service.files().get_media(fileId=file_id)
        file_metadata = service.files().get(fileId=file_id, fields="name").execute()
        file_name = file_metadata.get("name")
        save_file_path = os.path.join(save_path, file_name)
        
        #Download the file
        with open(save_file_path, "wb") as file:
            downloader = MediaIoBaseDownload(file, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                print(f"Downloading... {int(status.progress() * 100)}% completed")
        
        print(f"Download complete: {save_file_path}")
        return save_file_path
    except Exception as e:
        print(f"Error downloading file: {e}")
        return None
#Merge chunks into a single file
def merge_chunks(file_paths, merged_file_path):
    with open(merged_file_path, "wb") as merged_file:
        for chunk_path in sorted(file_paths):
            with open(chunk_path, "rb") as chunk:
                merged_file.write(chunk.read())
    print(f"Merged file saved at: {merged_file_path}")

#Download and merge chunks into a single file
def download_and_merge_chunks(service, file_name, save_path="downloads"):
    os.makedirs(save_path, exist_ok=True)
    
    #Check if the full file exists first
    query = f"name = '{file_name}'"
    result = service.files().list(q=query, fields="files(id, name)").execute()
    files = result.get("files", [])
    
    if files:
        file_id = files[0]["id"]
        print("File found, downloading directly.")
        return download_file(service, file_id, save_path)
    
    #If full file not found, check for chunks
    query = f"name contains '{file_name}.part'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    chunk_files = results.get("files", [])
    
    if not chunk_files:
        print("File not found in Google Drive.")
        return None
    
    chunk_paths = []
    for file in sorted(chunk_files, key=lambda x: x['name']):
        file_id = file['id']
        chunk_path = download_file(service, file_id, save_path)
        if chunk_path:
            chunk_paths.append(chunk_path)
    
    merged_file_path = os.path.join(save_path, file_name)
    merge_chunks(chunk_paths, merged_file_path)
    return merged_file_path

#Download a file from all buckets
def download_from_all_buckets(file_name, save_path="downloads"):
    os.makedirs(save_path, exist_ok=True)
    bucket_numbers = get_all_authenticated_buckets()
    if not bucket_numbers:
        print("No authenticated buckets found. Please add a new bucket first.")
        return
    
    for bucket in bucket_numbers:
        try:
            service = authenticate_account(bucket)
            result = download_and_merge_chunks(service, file_name, save_path)
            if result:
                return result
        except Exception as e:
            print(f"Error downloading from bucket {bucket}: {e}")
    
    print("File not found in any bucket.")


def search_files():
    query = input("\nEnter a keyword to search for files across all buckets: ").strip()
    if not query:
        print("Invalid input. Returning to menu.")
        return
    list_files_from_all_buckets(query=query)

def add_new_bucket():
    bucket_number = len(get_all_authenticated_buckets()) + 1
    print(f"\nAdding a new bucket: Bucket {bucket_number}...")
    authenticate_account(bucket_number)
    print(f"Bucket {bucket_number} added successfully!")

if __name__ == "__main__":
    print("Syncly Demo 1")
    while True:
        print("\n-------------Storage Details-------------")
        check_all_storage()
        print("-------------------------------------------")
        print("\nOptions:")
        print("1: View Files")
        print("2: Search Files")
        print("3: Add New Bucket")
        print("4: Upload File")
        print("5: Downlaod File")
        print("6: Exit")

        choice = input("Choose an option (Enter a number): ")

        if choice == "1":
            list_files_from_all_buckets()
        elif choice == "2":
            search_files()
        elif choice == "3":
            add_new_bucket()
        elif choice == "4":
            file_path = input("Enter file path: ").strip()
            upload_file(file_path, file_name=os.path.basename(file_path), mimetype="application/octet-stream")
        elif choice == "5":
            file_path = input("Enter file name to download: ").strip()
            save_path = input("Enter save path (default: downloads): ").strip()
            download_from_all_buckets(file_path, save_path)
        elif choice == "6":
            print("Thank you for using Syncly's Demo 1!")
            break
        else:
            print("Invalid option. Please try again.")

