import os
import io
import json
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# Load environment variables
load_dotenv()

# API scope = read only
SCOPES = ['https://www.googleapis.com/auth/drive']

# Get paths from env
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")  # Default to "tokens" if not set
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")  # Default to "credentials.json" if not set
METADATA_FILE = "metadata.json"
os.makedirs(TOKEN_DIR, exist_ok=True)  # Ensure token dir exists

# Global variables for GUI
service = None
current_bucket = None

# Authenticate Google Drive account
def authenticate_account(bucket_number):
    token_path = os.path.join(TOKEN_DIR, f"bucket_{bucket_number}.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.valid:
            return build("drive", "v3", credentials=creds)

    # Re-auth tokens if needed
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save credentials
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)

# List files in Google Drive
def list_drive_files(service, max_results=None, query=None):
    all_files = []
    page_token = None
    query_filter = f"name contains '{query}'" if query else None  # Apply search filter if provided

    while True:
        results = service.files().list(
            pageSize=100,  # Fetch 100 files per API request
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageToken=page_token,
            q=query_filter  # Apply search filter
        ).execute()

        all_files.extend(results.get('files', []))

        # Stop early if we reach the requested limit
        if max_results and len(all_files) >= max_results:
            return all_files[:max_results]

        page_token = results.get('nextPageToken')
        if not page_token:
            break  # No more pages left

    return all_files

# Get all authenticated buckets
def get_all_authenticated_buckets():
    return [f.replace(".json", "").replace("bucket_", "") for f in os.listdir(TOKEN_DIR) if f.startswith("bucket_")]

# Check storage usage for a bucket
def check_storage(service, bucket):
    try:
        res = service.about().get(fields='storageQuota').execute()
        limit = int(res['storageQuota']['limit'])
        usage = int(res['storageQuota']['usage'])
        return limit, usage
    except Exception as e:
        print(f"Error for {bucket}: {e}")
        return 0, 0

# Check storage for all buckets
def check_all_storage():
    total_storage = 0
    total_used = 0
    buckets = get_all_authenticated_buckets()
    if not buckets:
        print("No authenticated buckets found. Please add a new bucket first.")
        return
    for bucket in buckets:
        service = authenticate_account(bucket)
        storage, used = check_storage(service, bucket)
        total_storage += storage
        total_used += used
    return total_storage, total_used

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

# Upload a file to Google Drive
def upload_file(file_path, file_name, mimetype):
    file_size = os.path.getsize(file_path)
    buckets = get_all_authenticated_buckets()
    free_space = []

    for bucket in buckets:
        service = authenticate_account(bucket)
        total, used = check_storage(service, bucket)
        free = total - used
        if free > 0:
            free_space.append([free, bucket])

    if sum(free for free, _ in free_space) < file_size:
        messagebox.showerror("Error", "Not enough space in any bucket.")
        return

    free_space.sort(reverse=True, key=lambda x: x[0])
    metadata = {"file_name": file_name, "chunks": []}

    offset = 0
    chunk_index = 0

    with open(file_path, "rb") as file:
        while offset < file_size:
            free_space.sort(reverse=True, key=lambda x: x[0])
            bucket_free, bucket_id = free_space[0]
            chunk_size = min(bucket_free, file_size - offset)
            chunk_filename = f"{file_path}.part{chunk_index}"

            with open(chunk_filename, "wb") as chunk_file:
                chunk_file.write(file.read(chunk_size))

            service = authenticate_account(bucket_id)
            media = MediaFileUpload(chunk_filename, mimetype=mimetype, resumable=True)
            file_metadata = {'name': f"{file_name}_part{chunk_index + 1}"}
            result = service.files().create(body=file_metadata, media_body=media).execute()
            file_id = result.get("id")

            metadata["chunks"].append({
                "chunk_name": f"{file_name}_part{chunk_index + 1}",
                "file_id": file_id,
                "bucket": bucket_id
            })

            free_space[0][0] -= chunk_size
            offset += chunk_size
            chunk_index += 1

    with open(METADATA_FILE, "w") as meta_file:
        json.dump(metadata, meta_file, indent=4)
    messagebox.showinfo("Success", "File uploaded successfully.")

# List of common file extensions to check
COMMON_EXTENSIONS = ['.jpg', '.pdf', '.png', '.txt', '.csv', '.docx', '.xlsx']

# Download a file from Google Drive
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
                print(f"Downloading... {int(status.progress() * 100)}% completed")

        messagebox.showinfo("Success", f"Download complete: {save_file_path}")
        return save_file_path
    except Exception as e:
        messagebox.showerror("Error", f"Error downloading file: {e}")
        return None

# Merge chunks into a single file
def merge_chunks(file_paths, merged_file_path):
    with open(merged_file_path, "wb") as merged_file:
        for chunk_path in sorted(file_paths):
            with open(chunk_path, "rb") as chunk:
                merged_file.write(chunk.read())
    messagebox.showinfo("Success", f"Merged file saved at: {merged_file_path}")

# Download and merge chunks into a single file
def download_and_merge_chunks(service, file_name, save_path="downloads"):
    os.makedirs(save_path, exist_ok=True)

    query = f"name contains '{file_name}' and not name contains '.part'"
    result = service.files().list(q=query, fields="files(id, name)").execute()
    files = result.get("files", [])

    if files:
        file_id = files[0]["id"]
        return download_file(service, file_id, save_path)

    query = f"name contains '{file_name}.part'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    chunk_files = results.get("files", [])

    if not chunk_files:
        messagebox.showerror("Error", "File not found in Google Drive.")
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

# Download a file from all buckets
def download_from_all_buckets(file_name, save_path="downloads"):
    os.makedirs(save_path, exist_ok=True)
    bucket_numbers = get_all_authenticated_buckets()
    if not bucket_numbers:
        messagebox.showerror("Error", "No authenticated buckets found. Please add a new bucket first.")
        return

    for bucket in bucket_numbers:
        try:
            service = authenticate_account(bucket)
            result = download_and_merge_chunks(service, file_name, save_path)
            if result:
                return result
        except Exception as e:
            print(f"Error downloading from bucket {bucket}: {e}")

    messagebox.showerror("Error", "File not found in any bucket.")

# GUI Functions
def on_upload():
    file_path = filedialog.askopenfilename()
    if file_path:
        upload_file(file_path, os.path.basename(file_path), "application/octet-stream")

def on_download():
    file_name = file_name_entry.get()
    if file_name:
        save_path = filedialog.askdirectory()
        if save_path:
            download_from_all_buckets(file_name, save_path)

def on_view_files():
    files = list_drive_files(service)
    file_list.delete(0, tk.END)
    for file in files:
        file_list.insert(tk.END, file['name'])

def on_search_files():
    query = search_entry.get()
    if query:
        files = list_drive_files(service, query=query)
        file_list.delete(0, tk.END)
        for file in files:
            file_list.insert(tk.END, file['name'])

def on_add_bucket():
    bucket_number = len(get_all_authenticated_buckets()) + 1
    authenticate_account(bucket_number)
    messagebox.showinfo("Success", f"Bucket {bucket_number} added successfully!")

def on_check_storage():
    total_storage, total_used = check_all_storage()
    storage_label.config(text=f"Total Storage: {round(total_storage / (1024**3), 2)} GB\n"
                             f"Total Used: {round(total_used / (1024**3), 2)} GB\n"
                             f"Total Free: {round((total_storage - total_used) / (1024**3), 2)} GB")

# Create the main window
root = tk.Tk()
root.title("Syncly Demo 1")
root.geometry("600x400")

# Create a notebook (tabbed interface)
notebook = ttk.Notebook(root)
notebook.pack(fill=tk.BOTH, expand=True)

# Create tabs
upload_tab = ttk.Frame(notebook)
download_tab = ttk.Frame(notebook)
view_tab = ttk.Frame(notebook)
search_tab = ttk.Frame(notebook)
bucket_tab = ttk.Frame(notebook)

notebook.add(upload_tab, text="Upload")
notebook.add(download_tab, text="Download")
notebook.add(view_tab, text="View Files")
notebook.add(search_tab, text="Search Files")
notebook.add(bucket_tab, text="Add Bucket")

# Upload Tab
upload_button = ttk.Button(upload_tab, text="Upload File", command=on_upload)
upload_button.pack(pady=20)

# Download Tab
file_name_label = ttk.Label(download_tab, text="File Name:")
file_name_label.pack(pady=5)
file_name_entry = ttk.Entry(download_tab)
file_name_entry.pack(pady=5)
download_button = ttk.Button(download_tab, text="Download File", command=on_download)
download_button.pack(pady=20)

# View Files Tab
view_button = ttk.Button(view_tab, text="View Files", command=on_view_files)
view_button.pack(pady=20)
file_list = tk.Listbox(view_tab)
file_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

# Search Files Tab
search_label = ttk.Label(search_tab, text="Search Query:")
search_label.pack(pady=5)
search_entry = ttk.Entry(search_tab)
search_entry.pack(pady=5)
search_button = ttk.Button(search_tab, text="Search Files", command=on_search_files)
search_button.pack(pady=20)

# Add Bucket Tab
add_bucket_button = ttk.Button(bucket_tab, text="Add New Bucket", command=on_add_bucket)
add_bucket_button.pack(pady=20)

# Storage Info
storage_label = ttk.Label(root, text="Storage Info")
storage_label.pack(pady=10)
check_storage_button = ttk.Button(root, text="Check Storage", command=on_check_storage)
check_storage_button.pack(pady=10)

# Start the GUI event loop
root.mainloop()
