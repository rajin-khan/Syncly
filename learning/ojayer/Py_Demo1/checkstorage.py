import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

# Load or create .env file
ENV_PATH = '.env'
if not os.path.exists(ENV_PATH):
    with open(ENV_PATH, 'w') as f:
        f.write('')

load_dotenv()  # Load environment variables

# Load credentials
with open('credentials.json', 'r') as f:
    credentials = json.load(f)['installed']

SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']
TOTAL_ACCOUNTS = 3

def save_refresh_token(account_number, refresh_token):
    env_var = f"ACCOUNT_{account_number}_REFRESH_TOKEN"
    env_content = ""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'r') as f:
            env_content = f.read()
    
    # Replace existing token or append new one
    if env_var in env_content:
        env_content = '\n'.join(
            [line if not line.startswith(env_var) else f"{env_var}={refresh_token}" for line in env_content.split('\n')]
        )
    else:
        env_content += f"\n{env_var}={refresh_token}\n"
    
    with open(ENV_PATH, 'w') as f:
        f.write(env_content)
    print(f"Refresh token saved for Account {account_number}!")

def authorize_and_save_token(account_number):
    flow = InstalledAppFlow.from_client_config({"installed": credentials}, SCOPES)
    creds = flow.run_local_server(port=0,access_type='offline', prompt='consent')
    save_refresh_token(account_number, creds.refresh_token)

    print('\nAll tokens saved! Now checking storage...')
def check_storage(account):
    try:
            creds = Credentials(
                None,  # Access token (not needed, as we use refresh token)
                refresh_token=account['refresh_token'],
                client_id=credentials['client_id'],
                client_secret=credentials['client_secret'],
                token_uri='https://oauth2.googleapis.com/token'
            )
            drive_service = build('drive', 'v3', credentials=creds)
            res = drive_service.about().get(fields='storageQuota').execute()
            
            limit = int(res['storageQuota']['limit'])
            usage = int(res['storageQuota']['usage'])
            
            
            print(f"\n--- {account['name']} ---")
            print(f"Total: {round(limit / (1024**3))} GB")
            print(f"Used: {round(usage / (1024**3))} GB")
            
    except Exception as e:
            print(f"Error for {account['name']}: {e}")
    
    return limit,usage

def check_all_storage():
    accounts = [
        {"name": "Account 1", "refresh_token": os.getenv("ACCOUNT_1_REFRESH_TOKEN")},
        {"name": "Account 2", "refresh_token": os.getenv("ACCOUNT_2_REFRESH_TOKEN")},
        {"name": "Account 3", "refresh_token": os.getenv("ACCOUNT_3_REFRESH_TOKEN")},
    ]
    
    total_storage = 0
    total_used = 0
    
    for account in accounts:
        storage,used = check_storage(account)
        total_storage+=storage
        total_used+=used
    print("\n--- Storage details ---")
    print(f"Total Storage: {round(total_storage / (1024**3))} GB")
    print(f"Total Used: {round(total_used / (1024**3))} GB")
    print(f"Total Free: {round((total_storage - total_used) / (1024**3))} GB")

if __name__ == "__main__":
    check_all_storage()


if __name__ == "__main__":
    check_all_storage()
