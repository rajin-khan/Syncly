import os
import json
import googleapiclient
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
import re

#Load environment variables
load_dotenv()

#API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

#Get paths from environment
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)

#Authenticate Google Drive account
def authenticate_account(bucket_number):
    token_path = os.path.join(TOKEN_DIR, f"bucket_{bucket_number}.json")
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.valid:
            return build("drive", "v3", credentials=creds)
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())
    return build("drive", "v3", credentials=creds)

#List files from Google Drive
def list_drive_files(service, max_results=None, query=None):
    all_files = []
    page_token = None
    query_filter = f"name contains '{query}'" if query else None
    while True:
        results = service.files().list(
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageToken=page_token,
            q=query_filter
        ).execute()
        all_files.extend(results.get('files', []))
        if max_results and len(all_files) >= max_results:
            return all_files[:max_results]
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return all_files

#Check storage quota for a Google Drive account
def get_all_authenticated_buckets():
    return [f.replace(".json", "").replace("bucket_", "") for f in os.listdir(TOKEN_DIR) if f.startswith("bucket_")]
def check_storage(service, bucket):
    try:
        res = service.about().get(fields='storageQuota').execute()
        limit = int(res['storageQuota']['limit'])
        usage = int(res['storageQuota']['usage'])
        return limit, usage
    except Exception as e:
        print(f"Error for {bucket}: {e}")
        return 0, 0
    
#Check storage quota for all buckets   
def check_all_storage():
    total_storage = 0
    total_used = 0
    buckets = get_all_authenticated_buckets()
    if not buckets:
        print("No authenticated buckets found.")
        return
    for bucket in buckets:
        service = authenticate_account(bucket)
        storage, used = check_storage(service, bucket)
        total_storage += storage
        total_used += used
    print(f"Total Storage: {round(total_storage / (1024**3), 2)} GB")
    print(f"Total Used: {round(total_used / (1024**3), 2)} GB")
    print(f"Total Free: {round((total_storage - total_used) / (1024**3), 2)} GB")


def parse_part_info(file_name):
    """Extract base name and part number from split filenames with improved regex."""
    patterns = [
        r'^(.*?)\.part(\d+)$',                 # .part0, .part1
        r'^(.*?)_part[\_\-]?(\d+)(\..*)?$',    # _part0, _part_1, _part-2
        r'^(.*?)\.(\d+)$',                     # .000, .001 (common split convention)
        r'^(.*?)(\d{3})(\..*)?$'               # Generic 3-digit numbering (e.g., .001)
    ]
    
    for pattern in patterns:
        match = re.match(pattern, file_name)
        if match:
            base = match.group(1)
            part_num = match.group(2)
            # Handle different pattern groups
            if pattern == patterns[1] and match.group(3):
                base += match.group(3) if match.group(3) else ''
            elif pattern == patterns[3] and match.group(3):
                base += match.group(3)
            try:
                return base, int(part_num)
            except ValueError:
                continue
    return None, None

def list_files_from_all_buckets(query=None):
    bucket_numbers = get_all_authenticated_buckets()
    if not bucket_numbers:
        print("No authenticated buckets found. Please add a new bucket first.")
        return
    max_files = 100    #just initializing
    if query:
        print(f"\nSearching for files containing: '{query}' across all buckets...")
    else:
        # Ask user for the number of files to retrieve
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
            max_files = None  # Fetch all files
            print("\nFetching all available files....")
        else:
            print("Invalid choice. Defaulting to 100 files.")
            max_files = 100

    all_files = []
    seen_files = set()  # Track files to avoid duplicates

    for bucket in bucket_numbers:
        try:
            service = authenticate_account(bucket)
            files = list_drive_files(service, max_files, query)  # Retrieve user-defined limit or search query
            for file in files:
                file_id = file['id']
                file_name = file['name']
                mime_type = file.get('mimeType', 'Unknown')
                size = file.get('size', 'Unknown')
                file_url = f"https://drive.google.com/file/d/{file_id}/view"  # Generate Google Drive file URL

                # Check if the file is part of a split file
                base_name, part_num = parse_part_info(file_name)
                if base_name:
                    if part_num == 0:  # Only include part0
                        if base_name not in seen_files:  # Avoid duplicates
                            all_files.append((file_name, file_id, mime_type, size, file_url))
                            seen_files.add(base_name)
                else:
                    # Include non-split files
                    all_files.append((file_name, file_id, mime_type, size, file_url))
        except Exception as e:
            print(f"Error retrieving files or storage details for a bucket: {e}")

    # Sort files alphabetically by name
    all_files.sort(key=lambda x: x[0])

    # Pagination
    page_size = 30
    total_files = len(all_files)
    start_index = 0

    while start_index < total_files:
        # Display paginated file results
        print("\nFiles (Sorted Alphabetically):\n")
        for idx, (name, file_id, mime_type, size, file_url) in enumerate(all_files[start_index:start_index + page_size], start=start_index + 1):
            size_str = f"{float(size) / 1024 ** 2:.2f} MB" if size != 'Unknown' else "Unknown size"
            print(f"{idx}. {name} ({mime_type}) - {size_str}")
            print(f"   Press here to view file: {file_url}\n")  # Display clickable link

        start_index += page_size  # Move to next batch of files

        if start_index < total_files:
            more = input("\nDo you want to see more files? (y/n): ").strip().lower()
            if more != 'y':
                break

#Upload file chunk to Google Drive
def upload_chunk(service, chunk_path, mimetype, file_name, chunk_index):
    media = MediaFileUpload(chunk_path, mimetype=mimetype, resumable=True)
    file_metadata = {'name': f'{file_name}_part{chunk_index + 1}'}
    result = service.files().create(media_body=media, body=file_metadata).execute()
    return result.get("id")


#Upload file to Google Drive
def upload_file(file_path, file_name, mimetype):
    file_size = os.path.getsize(file_path)
    buckets = get_all_authenticated_buckets()
    free_space = []
    total_free = 0
    for bucket in buckets:
        service = authenticate_account(bucket)
        total, used = check_storage(service, bucket)
        free = total - used
        total_free += free
        if free > 0:
            free_space.append([free, bucket])
    if total_free < file_size:
        print("Not enough space.")
        return
    free_space.sort(reverse=True, key=lambda x: x[0])
    metadata = {"file_name": file_name, "chunks": []}
    best_bucket = free_space[0][1]
    service = authenticate_account(best_bucket)
    if free_space[0][0] >= file_size:
        media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
        file_metadata = {'name': file_name}
        result = service.files().create(media_body=media, body=file_metadata).execute()
        file_id = result.get("id")
        metadata["chunks"].append({"chunk_name": file_name, "file_id": file_id, "bucket": best_bucket})
    else:
        offset = 0
        chunk_index = 0
        with open(file_path, "rb") as file:
            while offset < file_size:
                #Sort and get the best available bucket
                free_space.sort(reverse=False, key=lambda x: x[0])
                print(free_space)
                #Find a bucket with enough space
                selected_bucket = None
                for i, (bucket_free, bucket_id) in enumerate(free_space):
                    if bucket_free > 0:
                        selected_bucket = bucket_id
                        selected_index = i
                        break
                if not selected_bucket:
                    print("No available buckets with free space.")
                    break
                chunk_size = min(free_space[selected_index][0], file_size - offset)
                chunk_filename = f"{file_path}.part{chunk_index}"
                with open(chunk_filename, "wb") as chunk_file:
                    chunk_file.write(file.read(chunk_size))
                file_id = None
                uploaded = False
                while not uploaded:
                    service = authenticate_account(selected_bucket)
                    try:
                        file_id = upload_chunk(service, chunk_filename, mimetype, file_name, chunk_index)
                        uploaded = True
                    except googleapiclient.errors.HttpError as e:
                        if "storageQuotaExceeded" in str(e):
                            print(f"Bucket {selected_bucket} is full. Trying next bucket.")
                            free_space[selected_index][0] = 0  #Mark bucket as full
                            break
                        else:
                            os.remove(chunk_filename)
                            raise e
                if file_id is None:
                    raise RuntimeError("Failed to upload chunk after retries")
                metadata["chunks"].append({
                    "chunk_name": f"{file_name}_part{chunk_index + 1}",
                    "file_id": file_id,
                    "bucket": selected_bucket
                })
                #Update remaining space after successful upload
                free_space[selected_index][0] -= chunk_size
                offset += chunk_size
                chunk_index += 1
                os.remove(chunk_filename)
    #Update metadata
    if os.path.exists(METADATA_FILE) and os.path.getsize(METADATA_FILE) > 0:
        with open(METADATA_FILE, 'r') as f:
            try:
                existing_metadata = json.load(f)
                if not isinstance(existing_metadata, list):  
                    existing_metadata = [existing_metadata]
            except json.JSONDecodeError:
                print("Warning: Metadata file is corrupted. Resetting metadata.")
                existing_metadata = []
    else:
        existing_metadata = []
    existing_metadata.append(metadata)
    with open(METADATA_FILE, 'w') as f:
        json.dump(existing_metadata, f, indent=4)
        print("Upload complete. Metadata updated.")


#List of common file extensions to check
COMMON_EXTENSIONS = ['.jpg', '.pdf', '.png', '.txt', '.csv', '.docx', '.xlsx']

#Download a file from Google Drive
def download_file(service, file_id, save_path):
    try:
        request = service.files().get_media(fileId=file_id)
        file_metadata = service.files().get(fileId=file_id, fields="name").execute()
        file_name = file_metadata.get("name")  # Preserve the original file name with extension
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
        for chunk_path in file_paths:
            with open(chunk_path, "rb") as chunk:
                merged_file.write(chunk.read())
    print(f"Merged file saved at: {merged_file_path}")


#Download and merge chunks into a single file
def download_and_merge_chunks(service, file_name, save_path="downloads"):
    os.makedirs(save_path, exist_ok=True)
    #Check if the full file exists first
    query = f"name contains '{file_name}' and not name contains '.part'"
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
        print(f"File not found in this bucket.")
        print(f"\nChecking another bucket...")
        return None
    
    #Sort chunks numerically by part number
    chunk_files.sort(key=lambda x: int(re.search(r'\.part(\d+)$', x['name']).group(1)))
    
    #Extract original filename with extension from first chunk
    original_filename = re.sub(r'\.part\d+$', '', chunk_files[0]['name'])
    merged_file_path = os.path.join(save_path, original_filename)  #Use extracted name
    
    chunk_paths = []
    for file in chunk_files:
        file_id = file['id']
        chunk_path = download_file(service, file_id, save_path)
        if chunk_path:
            chunk_paths.append(chunk_path)
    
    #Merge chunks and save with original extension
    merge_chunks(chunk_paths, merged_file_path)
    
    #Clean up chunk files
    for chunk_path in chunk_paths:
        os.remove(chunk_path)
    
    return merged_file_path


#Download a file from all buckets
def download_from_all_buckets(file_name, save_path="downloads"):
    os.makedirs(save_path, exist_ok=True)
    bucket_numbers = get_all_authenticated_buckets()
    if not bucket_numbers:
        print("No authenticated buckets found. Please add a new bucket first.")
        return
    
    #Check if the full file exists in any bucket
    for bucket in bucket_numbers:
        try:
            service = authenticate_account(bucket)
            result = download_and_merge_chunks(service, file_name, save_path)
            if result:
                return result
        except Exception as e:
            print(f"Error downloading from bucket {bucket}: {e}")
    
    #If the exact file name is not found, try with common extensions
    for ext in COMMON_EXTENSIONS:
        full_file_name = f"{file_name}{ext}"
        for bucket in bucket_numbers:
            try:
                service = authenticate_account(bucket)
                result = download_and_merge_chunks(service, full_file_name, save_path)
                if result:
                    return result
            except Exception as e:
                print(f"Error downloading from bucket {bucket}: {e}")
    
    print("File not found in any bucket.")


def search_files():
    query = input("Enter search keyword: ").strip()
    if query:
        list_files_from_all_buckets(query=query)


def add_new_bucket():
    bucket_number = len(get_all_authenticated_buckets()) + 1
    authenticate_account(bucket_number)
    print(f"Bucket {bucket_number} added.")


if __name__ == "__main__":
    print("Syncly Demo 1")
    while True:
        print("\n-------------Storage Details-------------")
        check_all_storage()
        print("-------------------------------------------")
        print("\n1: View Files\n2: Search\n3: Add Bucket\n4: Upload\n5: Download\n6: Exit")
        choice = input("Choose option: ").strip()
        if choice == "1":
            list_files_from_all_buckets()
        elif choice == "2":
            search_files()
        elif choice == "3":
            add_new_bucket()
        elif choice == "4":
            file_path = input("File path: ").strip()
            upload_file(file_path, os.path.basename(file_path), "application/octet-stream")
        elif choice == "5":
            file_name = input("Enter file name to download (without extension): ").strip()
            save_path = input("Enter save path (default: downloads): ").strip()
            if not save_path:               #default save path
                save_path = "downloads"
            download_from_all_buckets(file_name, save_path) 
        elif choice == "6":
            print("Thank you for using Syncly!")
            break
        else:
            print("Invalid choice.")
      