import os
import json
import dropbox
import requests
from dropbox.exceptions import AuthError, ApiError
from dropbox.files import WriteMode
from service import service

# Constants
METADATA_FILE = "metadata.json"

# Dropbox OAuth2 endpoints
DROPBOX_OAUTH2_TOKEN_URL = "https://api.dropbox.com/oauth2/token"

class DropboxService(service):
    def __init__(self, token_dir="tokens", app_key=None, app_secret=None, use_pkce=True):
        """
        Initialize the DropboxService.
        :param token_dir: Directory to store token files.
        :param app_key: Dropbox app key.
        :param app_secret: Dropbox app secret.
        :param use_pkce: Use PKCE if no secret.
        """
        self.token_dir = token_dir
        self.app_key = app_key or os.getenv("DROPBOX_APP_KEY")
        self.app_secret = app_secret or os.getenv("DROPBOX_APP_SECRET")  # May be None
        self.use_pkce = use_pkce  # Use PKCE if no secret
        self.client = None
        self.bucket_number = None  # Bucket number for this drive
        os.makedirs(self.token_dir, exist_ok=True)

    def get_token_file(self, bucket_number):
        """
        Get the token file path for a specific bucket.
        :param bucket_number: The bucket number for this drive.
        :return: Path to the token file.
        """
        return os.path.join(self.token_dir, f"bucket_{bucket_number}.json")

    def authenticate(self, bucket_number):
        """
        Authenticate with Dropbox using OAuth2.
        :param bucket_number: The bucket number for this drive.
        """
        self.bucket_number = bucket_number
        token_file = self.get_token_file(bucket_number)
        tokens = self.load_tokens(token_file)
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
        with open(token_file, "w") as f:
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

    def load_tokens(self, token_file):
        """
        Load tokens from the token file.
        :param token_file: Path to the token file.
        :return: Tokens as a dictionary, or None if the file is missing or corrupted.
        """
        if os.path.exists(token_file):
            with open(token_file, "r") as f:
                try:
                    tokens = json.load(f)
                    return tokens
                except json.JSONDecodeError:
                    print(f"Error: {token_file} is corrupted. Deleting and re-authenticating.")
                    os.remove(token_file)
                    return None
        return None
    def list_drive_files(self, max_results = None, query = None):
        return super().list_drive_files(max_results, query)

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
