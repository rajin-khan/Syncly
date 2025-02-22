import os
import json
import dropbox
import requests
from dropbox.exceptions import AuthError, ApiError
from dropbox.files import WriteMode

# Constants
METADATA_FILE = "metadata.json"
TOKEN_FILE = "token.json"  # File to store access and refresh tokens

# Dropbox OAuth2 endpoints
DROPBOX_OAUTH2_TOKEN_URL = "https://api.dropbox.com/oauth2/token"

class DropboxService:
    def __init__(self, token_dir="tokens", app_key=None, app_secret=None, use_pkce=True):
        self.token_dir = token_dir
        self.app_key = app_key or os.getenv("DROPBOX_APP_KEY")
        self.app_secret = app_secret or os.getenv("DROPBOX_APP_SECRET")  # May be None
        self.use_pkce = use_pkce  # Use PKCE if no secret
        self.client = None
        self.bucket_number = None  # Bucket number for this drive
        os.makedirs(self.token_dir, exist_ok=True)

    def authenticate(self, bucket_number):
        """
        Authenticate with Dropbox using OAuth2.
        :param bucket_number: The bucket number for this drive.
        """
        self.bucket_number = bucket_number
        tokens = self.load_tokens()
        refresh_token = tokens.get("refresh_token") if tokens else None

        if refresh_token:
            # Use the refresh token to get a new access token
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.app_key,
                "client_secret": self.app_secret,
            }
            try:
                print("Sending request to Dropbox API with data:", data)
                response = requests.post(DROPBOX_OAUTH2_TOKEN_URL, data=data)
                response.raise_for_status()
                token_data = response.json()
                access_token = token_data["access_token"]
                refresh_token = token_data.get("refresh_token", refresh_token)  # Use new refresh token if provided
                print("Access token refreshed successfully.")
            except requests.exceptions.RequestException as e:
                print(f"Failed to refresh access token: {e}")
                print("Response from Dropbox API:", response.text)  # Debugging: Print the API response
                return None
        else:
            # Start the OAuth2 flow to get a new access token and refresh token
            auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(
                self.app_key,
                self.app_secret,
                token_access_type='offline'
            )
            print(f"Authorize this app: {auth_flow.start()}")
            auth_code = input("Enter auth code: ").strip()
            try:
                result = auth_flow.finish(auth_code)
                access_token = result.access_token
                refresh_token = result.refresh_token
                print("New access token generated.")
            except dropbox.exceptions.AuthError as e:
                print(f"Authentication failed: {e}")
                return None

        # Save the new tokens
        with open(TOKEN_FILE, "w") as f:
            json.dump({"access_token": access_token, "refresh_token": refresh_token}, f)

        self.client = dropbox.Dropbox(access_token)
        return self.client

    def check_storage(self):
        """Returns (total allocated space, used space) in Dropbox."""
        if not self.client:
            raise ValueError("Service not authenticated. Call authenticate() first.")

        try:
            usage = self.client.users_get_space_usage()
            return usage.allocation.get_individual().allocated, usage.used
        except ApiError as e:
            print(f"Dropbox API error: {e}")
            return 0, 0
        except Exception as e:
            print(f"Unexpected error: {e}")
            return 0, 0

    def load_tokens(self):
        """Load tokens from the token file."""
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r") as f:
                try:
                    tokens = json.load(f)
                    return tokens
                except json.JSONDecodeError:
                    print("Error: token.json is corrupted. Deleting and re-authenticating.")
                    os.remove(TOKEN_FILE)
                    return None
        return None
    def list_drive_files(self, max_results=None, query=None):
        """List files in Dropbox with optional search query."""
        if not self.client:
            raise ValueError("Service not authenticated. Call authenticate() first.")

        files = []
        try:
            result = self.client.files_list_folder(path="", recursive=True)
            while True:
                for entry in result.entries:
                    if isinstance(entry, dropbox.files.FileMetadata):
                        if query and query.lower() not in entry.name.lower():
                            continue
                        files.append({
                            'id': entry.id,
                            'name': entry.name,
                            'mimeType': None,  # Dropbox doesn't provide MIME type directly
                            'size': entry.size,
                            'path': entry.path_display
                        })
                if not result.has_more or (max_results and len(files) >= max_results):
                    break
                result = self.client.files_list_folder_continue(result.cursor)
        except ApiError as e:
            print(f"Dropbox API error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        return files[:max_results] if max_results else files

    """Use these functions later"""
    # def get_file_url(self, file_path):
    #     try:
    #         return self.client.sharing_create_shared_link(file_path).url
    #    except:
    #        return f"https://www.dropbox.com/home{file_path}"
    # df download_file(self, file_path, destination_path):
    #     try:
    #         os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    #         self.client.files_download_to_file(destination_path, file_path)
    #         print(f"File downloaded to {destination_path}")
    #     except Exception as e:
    #         print(f"Failed to download file: {e}")
    #         raise
