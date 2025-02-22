import os
import json
import dropbox
from dropbox.exceptions import AuthError, ApiError
from dropbox import Dropbox
from dropbox.oauth import DropboxOAuth2FlowNoRedirect
from service import service

class DropboxService(service):
    def __init__(self, token_dir, app_key, app_secret):
        self.token_dir = token_dir
        self.app_key = app_key  # client_id
        self.app_secret = app_secret  # client_secret
        self.client = None
        os.makedirs(self.token_dir, exist_ok=True)

    def authenticate(self, bucket_number):
        """Authenticate Dropbox and save the tokens to a JSON file."""
        token_path = os.path.join(self.token_dir, f"dropbox_token_{bucket_number}.json")

        # Load existing tokens if they exist
        tokens = self.load_tokens(token_path)
        if tokens:
            access_token = tokens.get("access_token")
            refresh_token = tokens.get("refresh_token")
        else:
            access_token = None
            refresh_token = None

        # If no valid tokens, prompt the user to log in
        if not access_token or not refresh_token:
            auth_flow = DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)
            authorize_url = auth_flow.start()
            print(f"Authorize this app: {authorize_url}")
            auth_code = input("Enter auth code: ").strip()

            try:
                oauth_result = auth_flow.finish(auth_code)
                access_token = oauth_result.access_token
                refresh_token = oauth_result.refresh_token
            except Exception as e:
                print(f"Error authenticating: {e}")
                return None

            # Save the new tokens and client credentials to the JSON file
            self.save_tokens(token_path, access_token, refresh_token)

        # Initialize the Dropbox client
        self.client = Dropbox(oauth2_access_token=access_token, oauth2_refresh_token=refresh_token,
                              app_key=self.app_key, app_secret=self.app_secret)
        return self.client

    def refresh_tokens(self, bucket_number):
        """Refresh the Dropbox tokens and save them to the JSON file."""
        token_path = os.path.join(self.token_dir, f"dropbox_token_{bucket_number}.json")

        # Load existing tokens
        tokens = self.load_tokens(token_path)
        if not tokens:
            print("No token file found. Please authenticate first.")
            return None

        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            print("No refresh token found. Please authenticate again.")
            return None

        # Refresh the tokens
        try:
            print("Refreshing tokens...")
            new_tokens = self.client.refresh_access_token(refresh_token)
            access_token = new_tokens.access_token
            refresh_token = new_tokens.refresh_token

            # Save the new tokens and client credentials to the JSON file
            self.save_tokens(token_path, access_token, refresh_token)

            print("Tokens refreshed and saved successfully.")
            return access_token
        except Exception as e:
            print(f"Error refreshing tokens: {e}")
            return None

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

    def save_tokens(self, token_file, access_token, refresh_token):
        """
        Save tokens to the token file.
        :param token_file: Path to the token file.
        :param access_token: The access token.
        :param refresh_token: The refresh token.
        """
        with open(token_file, "w") as f:
            json.dump({
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.app_key,
                "client_secret": self.app_secret,
                "access_token": access_token
            }, f, indent=4)

    def list_drive_files(self, max_results=None, query=None):
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
