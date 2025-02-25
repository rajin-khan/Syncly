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

def print_header(text):
    width = 60
    print("\n" + "=" * width)
    print(f"{text:^{width}}")
    print("=" * width + "\n")

def print_subheader(text):
    width = 50
    print("\n" + "-" * width)
    print(f"{text:^{width}}")
    print("-" * width + "\n")

def print_status(text):
    print(f"→ {text}")

def print_success(text):
    print(f"\n✓ {text}")

def print_error(text):
    print(f"\n❌ {text}")

def print_progress(percentage):
    bar_length = 30
    filled = int(bar_length * percentage / 100)
    bar = "█" * filled + "▒" * (bar_length - filled)
    print(f"\rProgress: |{bar}| {percentage:.1f}% ", end="", flush=True)

#[Previous authentication functions remain exactly the same]
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

#[Previous list_drive_files function remains exactly the same]
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

def get_all_authenticated_buckets():
    return [f.replace(".json", "").replace("bucket_", "") for f in os.listdir(TOKEN_DIR) if f.startswith("bucket_")]

def check_storage(service, bucket):
    try:
        res = service.about().get(fields='storageQuota').execute()
        limit = int(res['storageQuota']['limit'])
        usage = int(res['storageQuota']['usage'])
        return limit, usage
    except Exception as e:
        print_error(f"Error for bucket {bucket}: {e}")
        return 0, 0

def check_all_storage():
    total_storage = 0
    total_used = 0
    buckets = get_all_authenticated_buckets()
    if not buckets:
        print_error("No authenticated buckets found.")
        return
    
    print_subheader("Storage Summary")
    for bucket in buckets:
        service = authenticate_account(bucket)
        storage, used = check_storage(service, bucket)
        total_storage += storage
        total_used += used
        
    free_space = total_storage - total_used
    print(f"📊 Total Storage: {round(total_storage / (1024**3), 2):>8} GB")
    print(f"📈 Used Space:   {round(total_used / (1024**3), 2):>8} GB")
    print(f"📉 Free Space:   {round(free_space / (1024**3), 2):>8} GB")
    
    # Add usage percentage bar
    usage_percent = (total_used / total_storage) * 100 if total_storage > 0 else 0
    print("\nStorage Usage:")
    print_progress(usage_percent)
    print()  # New line after progress bar

def list_files_from_all_buckets(query=None):
    bucket_numbers = get_all_authenticated_buckets()
    if not bucket_numbers:
        print_error("No authenticated buckets found. Please add a new bucket first.")
        return

    max_files = 100  # Default to 100 files if no choice is made

    if query:
        print_subheader(f"Searching for: '{query}'")
    else:
        print_subheader("File Retrieval Options")
        print("1: ~ 50 files")
        print("2: ~ 100 files")
        print("3: ~ 500 files")
        print("4: All available files")
        
        choice = input("\nSelect number of files to retrieve (1-4): ").strip()

        if choice == "1":
            max_files = 50
        elif choice == "2":
            max_files = 100
        elif choice == "3":
            max_files = 500
        elif choice == "4":
            max_files = None
            print_status("Fetching all available files...")
        else:
            print_status("Invalid choice. Defaulting to 100 files.")
            max_files = 100

    all_files = []

    for bucket in bucket_numbers:
        try:
            service = authenticate_account(bucket)
            files = list_drive_files(service, max_files, query)
            for file in files:
                file_id = file['id']
                file_name = file['name']
                mime_type = file.get('mimeType', 'Unknown')
                size = file.get('size', 'Unknown')
                file_url = f"https://drive.google.com/file/d/{file_id}/view"
                all_files.append((file_name, file_id, mime_type, size, file_url))
        except Exception as e:
            print_error(f"Error retrieving files from bucket {bucket}: {e}")

    all_files.sort(key=lambda x: x[0])
    page_size = 30
    total_files = len(all_files)
    start_index = 0

    while start_index < total_files:
        print_subheader(f"Files {start_index + 1}-{min(start_index + page_size, total_files)} of {total_files}")
        
        for idx, (name, file_id, mime_type, size, file_url) in enumerate(all_files[start_index:start_index + page_size], start=start_index + 1):
            size_str = f"{float(size) / 1024 ** 2:.2f} MB" if size != 'Unknown' else "Unknown size"
            print(f"\n{idx}. {name}")
            print(f"   Type: {mime_type}")
            print(f"   Size: {size_str}")
            print(f"   URL:  {file_url}")

        start_index += page_size

        if start_index < total_files:
            more = input("\nShow more files? (y/n): ").strip().lower()
            if more != 'y':
                break

def upload_chunk(service, chunk_path, mimetype, file_name, chunk_index):
    media = MediaFileUpload(chunk_path, mimetype=mimetype, resumable=True)
    file_metadata = {'name': f'{file_name}_part{chunk_index + 1}'}
    result = service.files().create(media_body=media, body=file_metadata).execute()
    return result.get("id")

def upload_file(file_path, file_name, mimetype):
    print_subheader("File Upload")
    
    if not os.path.exists(file_path):
        print_error("File not found!")
        return
        
    file_size = os.path.getsize(file_path)
    print_status(f"Preparing to upload: {file_name}")
    print_status(f"File size: {round(file_size / (1024**2), 2)} MB")
    
    buckets = get_all_authenticated_buckets()
    free_space = []
    total_free = 0
    
    print_status("Checking available storage...")
    for bucket in buckets:
        service = authenticate_account(bucket)
        total, used = check_storage(service, bucket)
        free = total - used
        total_free += free
        if free > 0:
            free_space.append([free, bucket])
            
    if total_free < file_size:
        print_error("Not enough space available for upload.")
        return
        
    free_space.sort(reverse=True, key=lambda x: x[0])
    metadata = {"file_name": file_name, "chunks": []}
    best_bucket = free_space[0][1]
    service = authenticate_account(best_bucket)
    
    if free_space[0][0] >= file_size:
        print_status("Uploading file...")
        media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
        file_metadata = {'name': file_name}
        result = service.files().create(media_body=media, body=file_metadata).execute()
        file_id = result.get("id")
        metadata["chunks"].append({"chunk_name": file_name, "file_id": file_id, "bucket": best_bucket})
        print_success("Upload complete!")
    else:
        print_status("File will be split into chunks for upload...")
        offset = 0
        chunk_index = 0
        with open(file_path, "rb") as file:
            while offset < file_size:
                free_space.sort(reverse=False, key=lambda x: x[0])
                selected_bucket = None
                for i, (bucket_free, bucket_id) in enumerate(free_space):
                    if bucket_free > 0:
                        selected_bucket = bucket_id
                        selected_index = i
                        break
                        
                if not selected_bucket:
                    print_error("No available buckets with free space.")
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
                        print_status(f"Uploading chunk {chunk_index + 1}...")
                        file_id = upload_chunk(service, chunk_filename, mimetype, file_name, chunk_index)
                        uploaded = True
                    except googleapiclient.errors.HttpError as e:
                        if "storageQuotaExceeded" in str(e):
                            print_status(f"Bucket {selected_bucket} is full. Trying next bucket...")
                            free_space[selected_index][0] = 0
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
                
                free_space[selected_index][0] -= chunk_size
                offset += chunk_size
                chunk_index += 1
                os.remove(chunk_filename)
                
                # Show upload progress
                progress = (offset / file_size) * 100
                print_progress(progress)
                
    if os.path.exists(METADATA_FILE) and os.path.getsize(METADATA_FILE) > 0:
        with open(METADATA_FILE, 'r') as f:
            try:
                existing_metadata = json.load(f)
                if not isinstance(existing_metadata, list):
                    existing_metadata = [existing_metadata]
            except json.JSONDecodeError:
                print_error("Metadata file is corrupted. Resetting metadata.")
                existing_metadata = []
    else:
        existing_metadata = []
        
    existing_metadata.append(metadata)
    with open(METADATA_FILE, 'w') as f:
        json.dump(existing_metadata, f, indent=4)
        print_success("Upload complete. Metadata updated.")

COMMON_EXTENSIONS = ['.jpg', '.pdf', '.png', '.txt', '.csv', '.docx', '.xlsx']

def download_file(service, file_id, save_path):
    try:
        request = service.files().get_media(fileId=file_id)
        file_metadata = service.files().get(fileId=file_id, fields="name").execute()
        file_name = file_metadata.get("name")
        save_file_path = os.path.join(save_path, file_name)
        
        with open(save_file_path, "wb") as file:
            downloader = MediaIoBaseDownload(file, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                print_progress(status.progress() * 100)
                
        print_success(f"Downloaded to: {save_file_path}")
        return save_file_path
    except Exception as e:
        print_error(f"Download failed: {e}")
        return None

def merge_chunks(file_paths, merged_file_path):
    print_status("Merging chunks...")
    with open(merged_file_path, "wb") as merged_file:
        for chunk_path in sorted(file_paths):
            with open(chunk_path, "rb") as chunk:
                merged_file.write(chunk.read())
    print_success(f"Merged file saved at: {merged_file_path}")

def download_and_merge_chunks(service, file_name, save_path="downloads"):
    os.makedirs(save_path, exist_ok=True)
    
    query = f"name contains '{file_name}' and not name contains '.part'"
    result = service.files().list(q=query, fields="files(id, name)").execute()
    files = result.get("files", [])
    
    if files:
        print_status("File found, downloading directly...")
        file_id = files[0]["id"]
        return download_file(service, file_id, save_path)
    
    query = f"name contains '{file_name}.part'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    chunk_files = results.get("files", [])
    
    if not chunk_files:
        print_error("File not found in Google Drive.")
        return None
    
    print_status("Found file chunks. Beginning download...")
    
    chunk_files.sort(key=lambda x: int(re.search(r'\.part(\d+)$', x['name']).group(1)))
    original_filename = re.sub(r'\.part\d+$', '', chunk_files[0]['name'])
    merged_file_path = os.path.join(save_path, original_filename)
    
    chunk_paths = []
    total_chunks = len(chunk_files)
    for i, file in enumerate(chunk_files, 1):
        print_status(f"Downloading chunk {i} of {total_chunks}...")
        file_id = file['id']
        chunk_path = download_file(service, file_id, save_path)
        if chunk_path:
            chunk_paths.append(chunk_path)
    
    merge_chunks(chunk_paths, merged_file_path)
    
    print_status("Cleaning up temporary files...")
    for chunk_path in chunk_paths:
        os.remove(chunk_path)
    
    return merged_file_path

def download_from_all_buckets(file_name, save_path="downloads"):
    print_subheader("File Download")
    
    os.makedirs(save_path, exist_ok=True)
    bucket_numbers = get_all_authenticated_buckets()
    if not bucket_numbers:
        print_error("No authenticated buckets found. Please add a new bucket first.")
        return
    
    print_status(f"Searching for file: {file_name}")
    
    for bucket in bucket_numbers:
        try:
            service = authenticate_account(bucket)
            result = download_and_merge_chunks(service, file_name, save_path)
            if result:
                print_success(f"File downloaded successfully to: {result}")
                return result
        except Exception as e:
            print_error(f"Error in bucket {bucket}: {e}")
    
    print_status("Trying common file extensions...")
    for ext in COMMON_EXTENSIONS:
        full_file_name = f"{file_name}{ext}"
        print_status(f"Checking for: {full_file_name}")
        for bucket in bucket_numbers:
            try:
                service = authenticate_account(bucket)
                result = download_and_merge_chunks(service, full_file_name, save_path)
                if result:
                    print_success(f"File downloaded successfully to: {result}")
                    return result
            except Exception as e:
                print_error(f"Error in bucket {bucket}: {e}")
    
    print_error("File not found in any bucket.")

def search_files():
    print_subheader("File Search")
    query = input("Enter search keyword: ").strip()
    if query:
        list_files_from_all_buckets(query=query)
    else:
        print_error("Search keyword cannot be empty.")

def add_new_bucket():
    print_subheader("Adding New Bucket")
    bucket_number = len(get_all_authenticated_buckets()) + 1
    print_status(f"Initializing bucket {bucket_number}...")
    authenticate_account(bucket_number)
    print_success(f"Bucket {bucket_number} added successfully.")

def print_menu():
    print_header("Syncly Storage Manager")
    print("1. 📋 View Files")
    print("2. 🔍 Search Files")
    print("3. ➕ Add Bucket")
    print("4. ⬆️  Upload File")
    print("5. ⬇️  Download File")
    print("6. 🚪 Exit")

if __name__ == "__main__":
    while True:
        print_menu()
        check_all_storage()
        choice = input("\nChoose option (1-6): ").strip()
        
        if choice == "1":
            list_files_from_all_buckets()
        elif choice == "2":
            search_files()
        elif choice == "3":
            add_new_bucket()
        elif choice == "4":
            print_subheader("File Upload")
            file_path = input("Enter file path: ").strip()
            if file_path:
                upload_file(file_path, os.path.basename(file_path), "application/octet-stream")
            else:
                print_error("File path cannot be empty.")
        elif choice == "5":
            print_subheader("File Download")
            file_name = input("Enter file name to download (without extension): ").strip()
            save_path = input("Enter save path (default: downloads): ").strip() or "downloads"
            if file_name:
                download_from_all_buckets(file_name, save_path)
            else:
                print_error("File name cannot be empty.")
        elif choice == "6":
            print_header("Goodbye! 👋")
            break
        else:
            print_error("Invalid choice. Please select 1-6.")