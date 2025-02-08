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

#Upload a chunk to Google Drive
#def upload_to_drive(chunk, chunk_filename, folder_id):
#    bucket_number = len(get_all_authenticated_buckets()) + 1
#    service = authenticate_account(bucket_number)
#    file_metadata = {"name": chunk_filename, "parents": [folder_id] if folder_id else None}
#    media = MediaIoBaseUpload(io.BytesIO(chunk), mimetype="application/octet-stream")
#    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
#    return file.get("id")

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
        #check_all_storage() 
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

#Split file into chunks and update metadata
def split_file(file_path, chunk_size):
    file_size = os.path.getsize(file_path)
    chunk_paths = []
    metadata = {"file_name": os.path.basename(file_path), "chunks": []}
    
    with open(file_path, "rb") as file:
        chunk_index = 0
        while file_size > 0:
            chunk_filename = f"{file_path}.part{chunk_index}"
            with open(chunk_filename, "wb") as chunk_file:
                chunk = file.read(min(chunk_size, file_size))
                chunk_file.write(chunk)
            chunk_paths.append(chunk_filename)
            metadata["chunks"].append({"chunk_index": chunk_index, "chunk_path": chunk_filename})
            file_size -= len(chunk)
            chunk_index += 1
    
    with open(METADATA_FILE, "w") as meta_file:
        json.dump(metadata, meta_file)
    print("File split complete. Metadata updated.")
    
    return chunk_paths

#Upload a single chunk
def upload_chunk(service, chunk_path, mimetype, file_name, chunk_index):
    media = MediaFileUpload(chunk_path, mimetype=mimetype, resumable=True)
    file_metadata = {'name': f'{file_name}_part{chunk_index + 1}'}
    file = service.files().create(media_body=media, body=file_metadata).execute()
    print(f'Uploaded chunk {chunk_index + 1} of {file_name} to Google Drive.')
    return file['id']

#Upload file and save metadata
def upload_file(file_path, file_name, mimetype):
    file_size = os.path.getsize(file_path)
    buckets = get_all_authenticated_buckets()
    free_space = []
    
    #Initialize free space for each bucket
    for bucket in buckets:
        service = authenticate_account(bucket)
        limit, used = check_storage(service,bucket)
        free = limit - used
        if free > 0:
            free_space.append((free, bucket))
    
    free_space.sort(reverse=True, key=lambda x: x[0])
    remaining_size = file_size
    metadata = {"file_name": file_name, "chunks": []}
    chunk_index = 0
    
    while remaining_size > 0:
        if not free_space:
            print("No available buckets with free space.")
            return

        #Get the largest available bucket
        largest_free, best_bucket = free_space[0]
        if largest_free <= 0:
            print("No more space in any bucket.")
            return

        #Determine chunk size (smallest of remaining size and largest_free)
        chunk_size = min(largest_free, remaining_size)
        
        #Split the file into a single chunk of chunk_size
        chunk_path = f"{file_path}.part{chunk_index}"
        with open(file_path, "rb") as file:
            file.seek(file_size - remaining_size)
            chunk_data = file.read(chunk_size)
            with open(chunk_path, "wb") as chunk_file:
                chunk_file.write(chunk_data)
        
        #Upload the chunk to the best bucket
        service = authenticate_account(best_bucket)
        media = MediaFileUpload(chunk_path, mimetype=mimetype)
        chunk_name = f"{file_name}_part{chunk_index}"
        file_metadata = {'name': chunk_name}
        uploaded_file = service.files().create(body=file_metadata, media_body=media).execute()
        file_id = uploaded_file['id']
        
        #Update metadata
        metadata["chunks"].append({
            "bucket": best_bucket,
            "file_id": file_id,
            "chunk_index": chunk_index
        })
        
        #Update remaining size
        remaining_size -= chunk_size
        chunk_index += 1
        
        #Update free_space: subtract chunk_size from the used bucket
        new_free = largest_free - chunk_size
        #Remove the current bucket from free_space and reinsert with new_free
        free_space.pop(0)
        if new_free > 0:
            #Insert the updated bucket back into the list
            inserted = False
            for i, (free, bucket) in enumerate(free_space):
                if new_free >= free:
                    free_space.insert(i, (new_free, best_bucket))
                    inserted = True
                    break
            if not inserted:
                free_space.append((new_free, best_bucket))
        
        #Clean up the chunk file
        #os.remove(chunk_path)
    
    #Save metadata after all chunks are uploaded
    with open(METADATA_FILE, "w") as meta_file:
        json.dump(metadata, meta_file)
    print("Upload complete. Metadata saved.")

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



#Search for files containing a keyword
def search_files():
    query = input("\nEnter a keyword to search for files across all buckets: ").strip()
    if not query:
        print("Invalid input. Returning to menu.")
        return
    list_files_from_all_buckets(query=query)

#Add a new bucket
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
        print("5: Download File")
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
