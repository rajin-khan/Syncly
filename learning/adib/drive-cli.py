import os
import json
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

# api scope set to read only
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

# store auth tokens in a separate directory
TOKEN_DIR = "UNI/SEM10-SOFTENG-PROJECT/learning/adib/tokens"
CREDENTIALS_FILE = "UNI/SEM10-SOFTENG-PROJECT/learning/adib/client_secret_1018759720940-cldlj2e2vv7i79d66ttd6qf18s8qp9e7.apps.googleusercontent.com.json"
os.makedirs(TOKEN_DIR, exist_ok=True)

def authenticate_account(account_name):

    token_path = os.path.join(TOKEN_DIR, f"{account_name}.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.valid:
            return build("drive", "v3", credentials=creds)

    # re-authenticate if required
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server()

    # save creds
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)

def list_drive_files(service, max_results=10):

    results = service.files().list(
        pageSize=max_results,
        fields="files(id, name, mimeType, size)"
    ).execute()

    files = results.get('files', [])

    if not files:
        print("No files found.")
    else:
        print("\nFiles in Google Drive:")
        for file in files:
            print(f"{file['name']} ({file.get('mimeType')})")

def switch_accounts():

    accounts = [f.replace(".json", "") for f in os.listdir(TOKEN_DIR) if f.endswith(".json")]

    if not accounts:
        print("No authenticated accounts found. Please authenticate a new account first.")
        email = input("Enter a unique name for this account (e.g., 'user1', 'user2'): ")
        return authenticate_account(email)

    print("\nAvailable Google Accounts:")
    for idx, account in enumerate(accounts, start=1):
        print(f"{idx}. {account}")

    choice = input("\nSelect an account number (or type 'new' to add another): ")
    if choice.lower() == "new":
        email = input("Enter a unique name for this account: ")
        return authenticate_account(email)
    elif choice.isdigit() and 1 <= int(choice) <= len(accounts):
        return authenticate_account(accounts[int(choice) - 1])
    else:
        print("Invalid choice.")
        return None

if __name__ == "__main__":
    print("drive cli beta (viewer)")

    service = switch_accounts()
    if service:
        list_drive_files(service)