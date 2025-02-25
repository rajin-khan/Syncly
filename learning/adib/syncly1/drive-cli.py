import os
import json
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

#load env variables
load_dotenv()

#api scope = read only
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

#get paths from env
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")  #default to "tokens" if not set
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")  #default to "credentials.json" if not set
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
            print("\nFetching all available files... This may take longer.")
        else:
            print("Invalid choice. Defaulting to 100 files.")
            max_files = 100
            
    max_files = None  #in search mode, fetch all matches

    all_files = []
    total_storage = 0
    total_used = 0

    for bucket in bucket_numbers:
        try:
            service = authenticate_account(bucket)
            files = list_drive_files(service, max_files, query)  #retrieve user-defined limit or search query
            for file in files:
                all_files.append((file['name'], file['id'], file.get('mimeType', 'Unknown'), file.get('size', 'Unknown')))

            #retrieve storage info from each bucket
            res = service.about().get(fields='storageQuota').execute()
            total_storage += int(res["storageQuota"]["limit"])
            total_used += int(res["storageQuota"]["usage"])

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
        print(f"\nTotal Storage: {round(total_storage / (1024**3), 2)} GB")
        print(f"Total Used: {round(total_used / (1024**3), 2)} GB")
        print(f"Total Free: {round((total_storage - total_used) / (1024**3), 2)} GB")

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
        print("\nOptions:")
        print("1: View Files")
        print("2: Search Files")
        print("3: Add New Bucket")
        print("4: Exit")

        choice = input("Choose an option (Enter a number): ")

        if choice == "1":
            list_files_from_all_buckets()
        elif choice == "2":
            search_files()
        elif choice == "3":
            add_new_bucket()
        elif choice == "4":
            print("Thank you for using Syncly's Demo 1!")
            break
        else:
            print("Invalid option. Please try again.")
