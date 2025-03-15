import os
import json
import dropbox
from dropbox.exceptions import AuthError, ApiError
from dropbox.oauth import DropboxOAuth2FlowNoRedirect

class DropboxService:
    def __init__(self, token_dir, app_key, app_secret):
        self.token_dir = token_dir
        self.app_key = app_key
        self.app_secret = app_secret
        self.client = None
        os.makedirs(self.token_dir, exist_ok=True)
    
    def authenticate(self, bucket_number):
        token_path = os.path.join(self.token_dir, f"bucket_{bucket_number}.json")
        tokens = self._load_tokens(token_path)
        
        if tokens:
            self.client = self._init_client(tokens["access_token"], tokens["refresh_token"])
            return tokens["access_token"]  # ✅ Return access token instead of client
        
        auth_flow = DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)
        authorize_url = auth_flow.start()
        print(f"Authorize this app: {authorize_url}")
        auth_code = input("Enter auth code: ").strip()
        
        try:
            oauth_result = auth_flow.finish(auth_code)
            self.client = self._init_client(oauth_result.access_token, oauth_result.refresh_token)
            self._save_tokens(token_path, oauth_result.access_token, oauth_result.refresh_token)
            return oauth_result.access_token  # ✅ Return access token
        except Exception as e:
            print(f"Error authenticating: {e}")
            return None

    
    def _init_client(self, access_token, refresh_token):
        try:
            client = dropbox.Dropbox(oauth2_access_token=access_token, oauth2_refresh_token=refresh_token,
                                     app_key=self.app_key, app_secret=self.app_secret)
            client.users_get_current_account()
            return client
        except ApiError:
            print("Invalid Dropbox credentials.")
            return None
    
    def _load_tokens(self, token_file):
        if os.path.exists(token_file):
            try:
                with open(token_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Corrupted token file: {token_file}. Re-authenticating.")
                os.remove(token_file)
        return None
    
    def _save_tokens(self, token_file, access_token, refresh_token):
        with open(token_file, "w") as f:
            json.dump({"access_token": access_token, "refresh_token": refresh_token}, f, indent=4)
        os.chmod(token_file, 0o600)
    
    def check_storage(self):
        if not self.client:
            raise ValueError("Service not authenticated. Call authenticate() first.")
        try:
            usage = self.client.users_get_space_usage()
            allocated = usage.allocation.get_individual().allocated
            used = usage.used
            return allocated, used
        except ApiError as e:
            print(f"Dropbox API error: {e}")
            return 0, 0
