import os
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load env variables
load_dotenv()

# API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

# Get paths from env
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")  # Default to "tokens" if not set
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")  # Default to "credentials.json" if not set

# Get all authenticated buckets from the JSON file
def get_all_authenticated_buckets():
    return [f.replace(".json", "").replace("bucket_", "") for f in os.listdir(TOKEN_DIR) if f.startswith("bucket_")]

# Authenticate individual accounts
def authenticate_account(bucket_number):
    token_path = os.path.join(TOKEN_DIR, f"bucket_{bucket_number}.json")
    # Check if token file exists
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.valid:
            return build("drive", "v3", credentials=creds)

    # Re-authenticate if needed
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save creds
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)

# Function to check storage
def check_storage(service, bucket):
    try:
        res = service.about().get(fields='storageQuota').execute()
        
        limit = int(res['storageQuota']['limit'])
        usage = int(res['storageQuota']['usage'])
        
    except Exception as e:
        print(f"Error for {bucket}: {e}")
        return 0, 0
    
    return limit, usage

# Check storage for all authenticated accounts
def check_all_storage():
    total_storage = 0
    total_used = 0
    buckets = get_all_authenticated_buckets()
    if not buckets:
        print("No authenticated buckets found. Please add a new bucket first.")
        return 0
    for bucket in buckets:
        service = authenticate_account(bucket)
        # Retrieve storage info from each bucket
        storage, used = check_storage(service, bucket)
        total_storage += storage
        total_used += used

    total_free = round((total_storage - total_used) / (1024**3), 2)
    print(f"\nTotal Storage: {round(total_storage / (1024**3), 2)} GB")
    print(f"Total Used: {round(total_used / (1024**3), 2)} GB")
    print(f"Total Free: {total_free} GB")
    return total_free

def split_file(file_path, chunk_size):
    """Split the file into chunks of a given size."""
    file_size = os.path.getsize(file_path)
    chunk_paths = []
    
    with open(file_path, "rb") as file:
        chunk_index = 0
        while file_size > 0:
            chunk_filename = f"{file_path}.part{chunk_index}"
            with open(chunk_filename, "wb") as chunk_file:
                chunk = file.read(min(chunk_size, file_size))
                chunk_file.write(chunk)
            chunk_paths.append(chunk_filename)
            file_size -= len(chunk)
            chunk_index += 1
            
    return chunk_paths

def upload_chunk(service, chunk_path, mimetype, file_name, chunk_index):
    """Upload a single chunk to Google Drive."""
    media = MediaFileUpload(chunk_path, mimetype=mimetype, resumable=True)
    file_metadata = {'name': f'{file_name}_part{chunk_index + 1}'}
    service.files().create(media_body=media, body=file_metadata).execute()
    print(f'Uploaded chunk {chunk_index + 1} of {file_name} to Google Drive.')

def upload_file(file_path, file_name, mimetype):
    """Upload the file to Google Drive, splitting it if necessary."""
    print("Entered upload function")
    file_size = os.path.getsize(file_path)
    buckets = get_all_authenticated_buckets()
    free_space = []
    print(f"file size = {file_size}")
    # Check available storage on Google Drive
    for bucket in buckets:
        service = authenticate_account(bucket)
        storage, used = check_storage(service, bucket)
        free = storage - used
        if free > 0:  # Ignore full buckets
            free_space.append((free, bucket))

    # Sort the free space in descending order
    free_space.sort(reverse=True, key=lambda x: x[0])
    print(free_space)
    remaining_size = file_size
    while remaining_size > 0:
        # Get the largest available drive
        largest_free, best_bucket = free_space[1]
        print(f"largest file: {largest_free}")
        if largest_free >= remaining_size:
            # If the largest drive has enough space for the remaining file size
            print(f'Uploading the whole file to {best_bucket}.')
            service = authenticate_account(best_bucket)
            media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True)
            file_metadata = {'name': file_name}
            service.files().create(media_body=media, body=file_metadata).execute()
            print(f'Uploaded the whole file to {best_bucket}.')
            return
        # Split the file if not enough space
        print("Splitting the file across drives...")

        # Split the file into chunks
        chunk_size = min(largest_free, remaining_size)
        chunk_paths = split_file(file_path, chunk_size)
        print(f"Chunk Size:{chunk_size}")
        print(f"Chunk paths:{chunk_paths}")
        # Upload each chunk
        for chunk_index, chunk_path in enumerate(chunk_paths):
            # Get the largest available drive
            largest_free, best_bucket = free_space[0]

            # Upload the chunk to the largest drive available
            service = authenticate_account(best_bucket)
            upload_chunk(service, chunk_path, mimetype, file_name, chunk_index)

            # Update the remaining file size
            remaining_size -= os.path.getsize(chunk_path)
            print(f'Remaining file size: {remaining_size} bytes')
        
        # Update free space after each upload
        free_space = [(free - os.path.getsize(chunk_path), bucket) for free, bucket in free_space]

file_path = input("Enter file path:")
upload_file(file_path, file_name="Test_Object", mimetype="application/octet-stream")