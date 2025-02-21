import os
import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
from dropbox.exceptions import AuthError, ApiError
from service import service

class DropboxService(service):
    def __init__(self, token_dir="tokens", app_key=None, app_secret=None, use_pkce=True):
        self.token_dir = token_dir
        self.app_key = app_key or os.getenv("DROPBOX_APP_KEY")
        self.app_secret = app_secret or os.getenv("DROPBOX_APP_SECRET")  # May be None
        self.use_pkce = use_pkce  # Use PKCE if no secret
        self.client = None
        os.makedirs(self.token_dir, exist_ok=True)

    def authenticate(self, bucket_number):
        """
        Authenticate with Dropbox using OAuth2 and store the access token.
        If the token is expired, refresh it using the refresh token.
        """
        token_path = os.path.join(self.token_dir, f"bucket_{bucket_number}.json")
        refresh_token_path = os.path.join(self.token_dir, f"bucket_{bucket_number}_refresh.json")

        # Load existing tokens if they exist
        access_token = None
        refresh_token = None
        if os.path.exists(token_path):
            with open(token_path, "r") as f:
                access_token = f.read().strip()
        if os.path.exists(refresh_token_path):
            with open(refresh_token_path, "r") as f:
                refresh_token = f.read().strip()

        # If access token exists, try to initialize the client
        if access_token:
            self.client = dropbox.Dropbox(access_token)
            try:
                # Check if the token is valid by making a simple API call
                self.client.users_get_current_account()
                print("Using existing access token.")
                return
            except AuthError:
                print("Access token expired. Attempting to refresh...")
                self.client = None

        # If refresh token exists, use it to get a new access token
        if refresh_token:
            try:
                auth_flow = DropboxOAuth2FlowNoRedirect(
                    consumer_key=self.app_key,
                    consumer_secret=None if self.use_pkce else self.app_secret,
                    token_access_type='offline',
                    scope=['files.content.read', 'files.content.write'],
                    use_pkce=self.use_pkce
                )
                result = auth_flow.refresh_access_token(refresh_token)
                access_token = result.access_token
                refresh_token = result.refresh_token  # Update refresh token
                print("Access token refreshed successfully.")
            except AuthError as e:
                print(f"Failed to refresh access token: {e}")
                access_token = None
                refresh_token = None

        # If no valid tokens exist, start the OAuth2 flow
        if not access_token:
            auth_flow = DropboxOAuth2FlowNoRedirect(
                consumer_key=self.app_key,
                consumer_secret=None if self.use_pkce else self.app_secret,
                token_access_type='offline',
                scope=['files.content.read', 'files.content.write'],
                use_pkce=self.use_pkce
            )
            print(f"Authorize this app: {auth_flow.start()}")
            auth_code = input("Enter auth code: ").strip()
            try:
                result = auth_flow.finish(auth_code)
                access_token = result.access_token
                refresh_token = result.refresh_token
                print("New access token generated.")
            except AuthError as e:
                print(f"Authentication failed: {e}")
                return

        # Save tokens for future use
        with open(token_path, "w") as f:
            f.write(access_token)
        with open(refresh_token_path, "w") as f:
            f.write(refresh_token)

        # Initialize the Dropbox client
        self.client = dropbox.Dropbox(access_token)

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
    #     except:
    #         return f"https://www.dropbox.com/home{file_path}"

    # def download_file(self, file_path, destination_path):
    #     try:
    #         os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    #         self.client.files_download_to_file(destination_path, file_path)
    #         print(f"File downloaded to {destination_path}")
    #     except Exception as e:
    #         print(f"Failed to download file: {e}")
    #         raise