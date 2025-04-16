# --- START OF FILE Dropbox.py ---

import os
import logging
import dropbox
from dropbox.exceptions import AuthError, ApiError
from dropbox.oauth import DropboxOAuth2Flow
from dropbox.files import FileMetadata, FolderMetadata, DeletedMetadata # Added imports
from Service import Service
from Database import Database
from typing import List, Dict, Optional # Added typing imports

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DropboxService(Service):
    def __init__(self, token_dir="tokens", app_key=None, app_secret=None):
        self.token_dir = token_dir
        self.app_key = app_key
        self.app_secret = app_secret
        self.service = None
        os.makedirs(self.token_dir, exist_ok=True)
        self.db = Database().get_instance()

    def authenticate(self, bucket_number, user_id):
        """
        Authenticate with Dropbox using AuthManager.
        """
        from AuthManager import AuthManager
        auth_manager = AuthManager(user_id, self.token_dir)
        self.service = auth_manager.authenticate_dropbox(bucket_number, self.app_key, self.app_secret)
        return self.service

    def listFiles(self, folder_path="", query: Optional[str] = None, max_results: Optional[int] = None) -> List[Dict]:
        """
        List files from Dropbox. If query is provided, attempts a simple name filter.
        Changed default to non-recursive listing for performance.
        """
        if not self.service:
            raise ValueError("Dropbox service not authenticated. Call authenticate() first.")

        files_list = []
        try:
            # --- The Key Change is Here ---
            logger.info(f"Listing Dropbox files in path: '{folder_path}' (Non-Recursive)")
            result = self.service.files_list_folder(
                path=folder_path if folder_path else "", # Ensure empty string for root
                recursive=False # <--- SET THIS TO FALSE
            )
            # --- End Key Change ---

            while True:
                for entry in result.entries:
                    # Skip folders and deleted files explicitly
                    if not isinstance(entry, FileMetadata):
                        continue

                    # Simple name filtering if query is provided
                    if query and query.lower() not in entry.name.lower():
                        continue

                    # Try to get a shareable link (might fail if not shared)
                    try:
                        link_result = self.service.files_get_temporary_link(entry.path_display)
                        file_link = link_result.link
                    except ApiError as link_err:
                        logger.debug(f"Could not get temporary link for Dropbox file {entry.name}: {link_err}. Using placeholder path.")
                        file_link = f"dropbox:{entry.path_display}" # Placeholder

                    files_list.append({
                        "id": entry.id,
                        "name": entry.name,
                        "size": entry.size,
                        "path": file_link,
                        "provider": "Dropbox"
                    })

                    # Stop if max_results is reached
                    if max_results and len(files_list) >= max_results:
                        logger.info(f"Reached max_results limit ({max_results}) for Dropbox listFiles.")
                        # Ensure exact limit is respected when returning early
                        return files_list[:max_results]


                # Check if there are more entries on the current page
                if not result.has_more:
                    break

                # Fetch the next page
                logger.info("Fetching next page of Dropbox files...")
                result = self.service.files_list_folder_continue(result.cursor)


        except ApiError as err:
            # Handle potential errors like path not found specifically
            if isinstance(err.error, dropbox.files.ListFolderError) and err.error.is_path() and err.error.get_path().is_not_folder():
                 logger.warning(f"Dropbox path '{folder_path}' is not a folder.")
                 return [] # Return empty list if path isn't a folder
            else:
                logger.error(f"Dropbox API error during listFiles: {err}")
                return [] # Return empty on other errors
        except Exception as e:
            logger.error(f"An unexpected error occurred during Dropbox listFiles: {e}", exc_info=True)
            return []

        logger.info(f"Dropbox listFiles found {len(files_list)} files in '{folder_path}'.")
        # Apply limit again in case the loop finished exactly at the limit or pagination ended
        return files_list[:max_results] if max_results else files_list

# ... rest of the DropboxService class (check_storage, searchFiles) ...
# (Make sure searchFiles still works as intended - it uses a different API call)
    def check_storage(self) -> tuple[int, int]:
        # (Keep implementation as is)
        if not self.service: logger.error("Service not authenticated."); return 0, 0
        try:
            usage = self.service.users_get_space_usage(); allocation = usage.allocation.get_individual() if usage.allocation.is_individual() else usage.allocation.get_team()
            limit = allocation.allocated if allocation else 0; usage_used = usage.used
            logger.info(f"Dropbox Storage: {usage_used / (1024**3):.2f} GB used / {limit / (1024**3):.2f} GB total.")
            return limit, usage_used
        except ApiError as err: logger.error(f"Dropbox API error checking storage: {err}"); return 0, 0
        except Exception as e: logger.error(f"Unexpected error checking Dropbox storage: {e}"); return 0, 0

    def searchFiles(self, query: str, limit: int = 10) -> List[Dict]:
        # (Keep implementation as is - uses files_search_v2)
        if not self.service: logger.error("Dropbox service not authenticated for search."); return []
        files_list = []
        try:
            logger.info(f"Executing Dropbox search with query: '{query}'")
            result = self.service.files_search_v2(query=query, options=dropbox.files.SearchOptions(max_results=min(limit * 2, 100), order_by=dropbox.files.SearchOrderBy.last_modified_time, file_status=dropbox.files.FileStatus.active))
            count = 0
            for match in result.matches:
                if count >= limit: break
                metadata = match.metadata.get_metadata()
                if isinstance(metadata, FileMetadata):
                    try: link_result = self.service.files_get_temporary_link(metadata.path_display); file_link = link_result.link
                    except ApiError as link_err: logger.debug(f"Could not get temp link for {metadata.name}: {link_err}."); file_link = f"dropbox:{metadata.path_display}"
                    files_list.append({"id": metadata.id, "name": metadata.name, "size": metadata.size, "path": file_link, "provider": "Dropbox"}); count += 1
        except ApiError as err: logger.error(f"Dropbox API error during searchFiles: {err}"); return files_list
        except Exception as e: logger.error(f"Unexpected error during Dropbox searchFiles: {e}"); return []
        logger.info(f"Dropbox search found {len(files_list)} files for query '{query}'.")
        return files_list[:limit]

# --- END OF FILE Dropbox.py ---