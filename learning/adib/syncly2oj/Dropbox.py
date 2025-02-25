import os
import json
import logging
import dropbox
from Service import Service
from dropbox.exceptions import AuthError, ApiError
from dropbox.oauth import DropboxOAuth2FlowNoRedirect

# Set up logging
#logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DropboxService(Service):
    def __init__(self, token_dir, app_key, app_secret):
        self.token_dir = token_dir
        self.app_key = app_key
        self.app_secret = app_secret
        self.client = None
        os.makedirs(self.token_dir, exist_ok=True)

    def authenticate(self, bucket_number):
        token_path = os.path.join(self.token_dir, f"bucket_{bucket_number}.json")

        if os.path.exists(token_path):
            with open(token_path, "r") as f:
                tokens = json.load(f)
                access_token = tokens.get("access_token")
                refresh_token = tokens.get("refresh_token")
                self.client = dropbox.Dropbox(oauth2_access_token=access_token)
                return self.client

        self.bucket_number = bucket_number
        token_path = os.path.join(self.token_dir, f"dropbox_token_{bucket_number}.json")
        # logger.info(f"Authenticating bucket {bucket_number}...")

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
                # logger.info("Authentication successful.")
            except Exception as e:
                logger.error(f"Error authenticating: {e}")
                return None

            # Save the new tokens and client credentials to the JSON file
            self.save_tokens(token_path, access_token, refresh_token)

        # Initialize the Dropbox client
        try:
            self.client = dropbox.Dropbox(
                oauth2_access_token=access_token,
                oauth2_refresh_token=refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret,
            )
            # Test the client to ensure the token is valid
            self.client.users_get_current_account()
            # logger.info("Dropbox client initialized successfully.")
        except ApiError as e:
            if "expired_access_token" in str(e):
                # logger.info("Access token expired. Refreshing token...")
                try:
                    self.client = dropbox.Dropbox(
                        oauth2_refresh_token=refresh_token,
                        app_key=self.app_key,
                        app_secret=self.app_secret,
                    )
                    # Save the new access token
                    self.save_tokens(token_path, self.client._oauth2_access_token, refresh_token)
                    # logger.info("Token refreshed successfully.")
                except Exception as e:
                    logger.error(f"Error refreshing token: {e}")
                    return None
            else:
                logger.error(f"Dropbox API error: {e}")
                return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None

        return self.client

    def load_tokens(self, token_file):
        """
        Load tokens from the token file.

        Args:
            token_file (str): Path to the token file.

        Returns:
            dict: Dictionary containing tokens, or None if the file is corrupted or doesn't exist.
        """
        if os.path.exists(token_file):
            try:
                with open(token_file, "r") as f:
                    tokens = json.load(f)
                    # logger.info(f"Tokens loaded from {token_file}.")
                    return tokens
            except json.JSONDecodeError:
                logger.error(f"Error: {token_file} is corrupted. Deleting and re-authenticating.")
                os.remove(token_file)
                return None
        return None

    def save_tokens(self, token_file, access_token, refresh_token):
        """
        Save tokens to the token file.

        Args:
            token_file (str): Path to the token file.
            access_token (str): Dropbox access token.
            refresh_token (str): Dropbox refresh token.
        """
        with open(token_file, "w") as f:
            json.dump(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "app_key": self.app_key,
                    "app_secret": self.app_secret,
                },
                f,
                indent=4,
            )
        os.chmod(token_file, 0o600)  # Restrict file permissions
        # logger.info(f"Tokens saved to {token_file}.")

    def check_storage(self):
        """
        Check the storage quota for the authenticated Dropbox account.

        Returns:
            tuple: A tuple containing the total allocated space (in bytes) and the used space (in bytes).
                   If an error occurs, returns (0, 0).
        """
        if not self.client:
            raise ValueError("Service not authenticated. Call authenticate() first.")

        try:
            usage = self.client.users_get_space_usage()
            allocated = usage.allocation.get_individual().allocated
            used = usage.used
            # logger.info(f"Storage usage: {used} bytes used out of {allocated} bytes allocated.")
            return allocated, used
        except ApiError as e:
            if "rate_limit" in str(e):
                logger.error("Rate limit exceeded. Please try again later.")
            elif "insufficient_permissions" in str(e):
                logger.error("Insufficient permissions to access storage information.")
            else:
                logger.error(f"Dropbox API error: {e}")
            return 0, 0
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return 0, 0
    """Use these functions later"""
    
    def listFiles(self, folder_path="",query=None):
        """
        List all files in a Dropbox folder.
        """
        if not self.client:
            raise ValueError("Dropbox service not authenticated. Call authenticate() first.")

        files = []
        try:
            result = self.client.files_list_folder(folder_path)
            files.extend(result.entries)

            # Handle pagination
            while result.has_more:
                result = self.client.files_list_folder_continue(result.cursor)
                files.extend(result.entries)

            file_list = []
            for file in files:
                if isinstance(file, dropbox.files.FileMetadata):
                    file_list.append({
                        "name": file.name,
                        "size": file.size,
                        "path": f"https://www.dropbox.com/home/{file.path_display}",
                        "provider": "Dropbox"
                    })
            return file_list
        except dropbox.exceptions.ApiError as err:
            print(f"Dropbox API error: {err}")
            return []




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