import os
import io
import json
import googleapiclient
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

# Get paths from environment
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)

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
        print(f"Error for {bucket}: {e}")
        return 0, 0

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

def list_files_from_all_buckets(query=None):
    bucket_numbers = get_all_authenticated_buckets()
    if not bucket_numbers:
        print("No authenticated buckets found.")
        return
    all_files = []
    for bucket in bucket_numbers:
        try:
            service = authenticate_account(bucket)
            files = list_drive_files(service, None, query)
            for file in files:
                all_files.append((file['name'], file['id'], file.get('mimeType', 'Unknown'), file.get('size', 'Unknown')))
        except Exception as e:
            print(f"Error retrieving files for bucket {bucket}: {e}")
    all_files.sort(key=lambda x: x[0])
    page_size = 30
    start_index = 0
    total_files = len(all_files)
    while start_index < total_files:
        print("\nFiles (Sorted Alphabetically):\n")
        for idx, (name, file_id, mime_type, size) in enumerate(all_files[start_index:start_index+page_size], start=start_index+1):
            size_str = f"{float(size)/1024**2:.2f} MB" if size != 'Unknown' else "Unknown size"
            print(f"{idx}. {name} ({mime_type}) - {size_str}")
        start_index += page_size
        if start_index < total_files:
            more = input("\nSee more files? (y/n): ").strip().lower()
            if more != 'y':
                break

def upload_chunk(service, chunk_path, mimetype, file_name, chunk_index):
    media = MediaFileUpload(chunk_path, mimetype=mimetype, resumable=True)
    file_metadata = {'name': f'{file_name}_part{chunk_index + 1}'}
    result = service.files().create(media_body=media, body=file_metadata).execute()
    return result.get("id")

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
                # Sort and get the best available bucket
                free_space.sort(reverse=False, key=lambda x: x[0])
                print(free_space)

                # Find a bucket with enough space
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
                            free_space[selected_index][0] = 0  # Mark bucket as full
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

                # Update remaining space after successful upload
                free_space[selected_index][0] -= chunk_size
                offset += chunk_size
                chunk_index += 1
                os.remove(chunk_filename)

    # Update metadata
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
                print(f"Downloading... {int(status.progress() * 100)}%")
        return save_file_path
    except Exception as e:
        print(f"Download error: {e}")
        return None

def merge_chunks(file_paths, merged_file_path):
    with open(merged_file_path, "wb") as merged_file:
        for chunk_path in sorted(file_paths):
            with open(chunk_path, "rb") as chunk:
                merged_file.write(chunk.read())
    print(f"Merged file saved at: {merged_file_path}")

def download_using_metadata(file_name, save_path):
    if not os.path.exists(METADATA_FILE):
        print("Metadata not found.")
        return
    with open(METADATA_FILE, 'r') as f:
        metadata_list = json.load(f)
    target_metadata = None
    for md in metadata_list:
        if md['file_name'] == file_name:
            target_metadata = md
            break
    if not target_metadata:
        print("File not found in metadata.")
        return
    chunks = target_metadata['chunks']
    if len(chunks) == 1 and chunks[0]['chunk_name'] == file_name:
        chunk = chunks[0]
        service = authenticate_account(chunk['bucket'])
        download_file(service, chunk['file_id'], save_path)
        return
    chunk_paths = []
    for chunk in chunks:
        service = authenticate_account(chunk['bucket'])
        downloaded_path = download_file(service, chunk['file_id'], save_path)
        if downloaded_path:
            chunk_paths.append(downloaded_path)
        else:
            print("Failed to download chunk.")
            return
    merged_path = os.path.join(save_path, file_name)
    merge_chunks(sorted(chunk_paths), merged_path)
    for path in chunk_paths:
        os.remove(path)
    print(f"File downloaded: {merged_path}")

def download_from_all_buckets(file_name, save_path="downloads"):
    os.makedirs(save_path, exist_ok=True)
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r') as f:
            try:
                metadata_list = json.load(f)
                for md in metadata_list:
                    if md['file_name'] == file_name:
                        print("Found in metadata. Downloading...")
                        download_using_metadata(file_name, save_path)
                        return
            except json.JSONDecodeError:
                print("Corrupted metadata.")
    print("Searching all buckets...")
    buckets = get_all_authenticated_buckets()
    for bucket in buckets:
        service = authenticate_account(bucket)
        query = f"name = '{file_name}'"
        result = service.files().list(q=query).execute()
        files = result.get('files', [])
        if files:
            download_file(service, files[0]['id'], save_path)
            return
        query = f"name contains '{file_name}_part'"
        result = service.files().list(q=query).execute()
        parts = result.get('files', [])
        if parts:
            chunk_paths = []
            for part in sorted(parts, key=lambda x: x['name']):
                downloaded = download_file(service, part['id'], save_path)
                if downloaded:
                    chunk_paths.append(downloaded)
            if chunk_paths:
                merged_path = os.path.join(save_path, file_name)
                merge_chunks(chunk_paths, merged_path)
                for path in chunk_paths:
                    os.remove(path)
                return
    print("File not found.")

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
        print("\n----- Storage Summary -----")
        check_all_storage()
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
            file_name = input("File name to download: ").strip()
            save_path = input("Save path (default: downloads): ").strip() or "downloads"
            download_from_all_buckets(file_name, save_path)
        elif choice == "6":
            print("Goodbye!")
            break
        else:
            print("Invalid choice.")

