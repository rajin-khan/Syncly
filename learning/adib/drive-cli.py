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


def list_drive_files(service, max_results=10):
    results = service.files().list(
        pageSize=max_results,
        fields="files(id, name, mimeType, size)"
    ).execute()

    return results.get('files', [])

#get tokens for buckets
def get_all_authenticated_buckets():
    return [f.replace(".json", "").replace("bucket_", "") for f in os.listdir(TOKEN_DIR) if f.startswith("bucket_")]

#ls
def list_files_from_all_buckets():
    bucket_numbers = get_all_authenticated_buckets()
    if not bucket_numbers:
        print("No authenticated buckets found. Please add a new bucket first.")
        return

    all_files = []

    for idx, bucket in enumerate(bucket_numbers, start=1):
        print(f"\nAccessing Bucket {idx}...")
        try:
            service = authenticate_account(bucket)
            files = list_drive_files(service, max_results=10)
            for file in files:
                all_files.append((file['name'], file['id'], file.get('mimeType', 'Unknown'), file.get('size', 'Unknown')))
        except Exception as e:
            print(f"Error retrieving files for Bucket {idx}: {e}")

    # Sort files alphabetically by name
    all_files.sort(key=lambda x: x[0])

    # Display first 10 files after sorting
    print("\nFirst 10 Files Across All Buckets (Sorted Alphabetically):")
    for idx, (name, file_id, mime_type, size) in enumerate(all_files[:10], start=1):
        size_str = f"{size} bytes" if size != 'Unknown' else "Unknown size"
        print(f"{idx}. {name} ({mime_type}) - {size_str}")

def add_new_bucket():
    bucket_number = len(get_all_authenticated_buckets()) + 1
    print(f"\nAdding a new bucket: Bucket {bucket_number}...")
    authenticate_account(bucket_number)
    print(f" Bucket {bucket_number} added successfully!")

if __name__ == "__main__":
    print("Syncly Demo 1")

    while True:
        print("\nOptions:")
        print("1️. View Files (Sorted Alphabetically)")
        print("2️. Add New Bucket")
        print("3️. Exit")

        choice = input("Choose an option (Enter a number): ")

        if choice == "1":
            list_files_from_all_buckets()
        elif choice == "2":
            add_new_bucket()
        elif choice == "3":
            print("Thank you for using Syncly's Demo 1!")
            break
        else:
            print("Invalid option. Please try again.")