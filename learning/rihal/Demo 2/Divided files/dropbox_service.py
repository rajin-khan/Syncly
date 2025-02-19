import os
import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
from main import CloudService

class DropboxService(CloudService):
    def authenticate(self):
        if os.path.exists(self.token_path):
            with open(self.token_path, 'r') as f:
                access_token = f.read().strip()
            self.client = dropbox.Dropbox(access_token)
            try:
                self.client.users_get_current_account()
            except dropbox.exceptions.AuthError:
                self._full_auth()
        else:
            self._full_auth()

    def _full_auth(self):
        app_key = os.getenv("DROPBOX_APP_KEY")
        app_secret = os.getenv("DROPBOX_APP_SECRET")
        auth_flow = DropboxOAuth2FlowNoRedirect(
            app_key, app_secret,
            token_access_type='offline',
            scope=['files.content.read']
        )
        print("Authorize this app:", auth_flow.start())
        auth_code = input("Enter auth code: ").strip()
        result = auth_flow.finish(auth_code)
        with open(self.token_path, 'w') as f:
            f.write(result.access_token)
        self.client = dropbox.Dropbox(result.access_token)

    def check_storage(self):
        try:
            usage = self.client.users_get_space_usage()
            return usage.allocation.get_individual().allocated, usage.used
        except Exception as e:
            print(f"Dropbox storage error: {e}")
            return 0, 0

    def list_files(self, max_results=None, query=None):
        files = []
        result = self.client.files_list_folder(path="", recursive=True)
        while True:
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    files.append({
                        'id': entry.id,
                        'name': entry.name,
                        'size': entry.size,
                        'path': entry.path_display
                    })
            if not result.has_more or (max_results and len(files) >= max_results):
                break
            result = self.client.files_list_folder_continue(result.cursor)
        return files[:max_results] if max_results else files

    def get_file_url(self, file_path):
        try:
            return self.client.sharing_create_shared_link(file_path).url
        except:
            return f"https://www.dropbox.com/home{file_path}"

    def download_file(self, file_path, destination_path):
        try:
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            self.client.files_download_to_file(destination_path, file_path)
            print(f"File downloaded to {destination_path}")
        except Exception as e:
            print(f"Failed to download file: {e}")
            raise
        