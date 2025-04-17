# --- START OF FILE Dropbox.py ---

import os
import logging
import dropbox
from dropbox.exceptions import AuthError, ApiError
from dropbox.oauth import DropboxOAuth2Flow
from dropbox.files import FileMetadata, FolderMetadata, DeletedMetadata, SearchOptions, SearchOrderBy, FileStatus, SearchMode # Added more imports
from Service import Service
from Database import Database
from typing import List, Dict, Optional

# Set up logging
# logging.basicConfig(level=logging.INFO) # Configure in api.py or main script
logger = logging.getLogger(__name__)

class DropboxService(Service):
    def __init__(self, token_dir="tokens", app_key=None, app_secret=None):
        self.token_dir = token_dir
        self.app_key = app_key
        self.app_secret = app_secret
        self.service: Optional[dropbox.Dropbox] = None # Type hint for clarity
        self.bucket_number: Optional[int] = None # <--- Add bucket_number attribute
        os.makedirs(self.token_dir, exist_ok=True)
        self.db = Database().get_instance()

    def authenticate(self, bucket_number, user_id):
        """
        Authenticate with Dropbox using AuthManager.
        Stores the bucket_number on the instance upon successful authentication.
        """
        from AuthManager import AuthManager
        auth_manager = AuthManager(user_id, self.token_dir)
        # Pass app key/secret during authentication
        self.service = auth_manager.authenticate_dropbox(bucket_number, self.app_key, self.app_secret)
        if self.service:
            self.bucket_number = bucket_number # <--- Store bucket number on success
            logger.info(f"Dropbox instance authenticated for bucket {self.bucket_number}")
        else:
            logger.error(f"Dropbox authentication failed for bucket {bucket_number}")
            self.bucket_number = None
        return self.service

    def listFiles(self, folder_path="", query: Optional[str] = None, max_results: Optional[int] = None) -> List[Dict]:
        """
        List files from Dropbox. If query is provided, attempts a simple name filter.
        Non-recursive listing.
        (No changes needed here for Step D)
        """
        if not self.service:
            raise ValueError("Dropbox service not authenticated. Call authenticate() first.")

        files_list = []
        try:
            logger.info(f"Listing Dropbox files (Bucket {self.bucket_number}) in path: '{folder_path}' (Non-Recursive)")
            result = self.service.files_list_folder(
                path=folder_path if folder_path else "",
                recursive=False
            )

            while True:
                for entry in result.entries:
                    if not isinstance(entry, FileMetadata): continue # Skip folders/deleted

                    # Simple name filtering
                    if query and query.lower() not in entry.name.lower(): continue

                    # Try to get a temporary link (might fail)
                    try:
                        # Use path_display for temp link request
                        link_result = self.service.files_get_temporary_link(entry.path_display)
                        file_link = link_result.link
                    except ApiError as link_err:
                        logger.debug(f"Could not get temporary link for Dropbox file {entry.name}: {link_err}. Using path_lower.")
                        file_link = f"dropbox:{entry.path_lower}" # Use path_lower as identifier

                    files_list.append({
                        "id": entry.id,
                        "name": entry.name,
                        "size": entry.size, # Keep as number
                        "path_lower": entry.path_lower, # Include path_lower for identification
                        "path": file_link, # Keep display/temp link too
                        "provider": "Dropbox",
                        # "bucket": self.bucket_number # Add if needed elsewhere
                    })

                    if max_results and len(files_list) >= max_results:
                        logger.info(f"Reached max_results limit ({max_results}) for Dropbox listFiles.")
                        return files_list[:max_results]

                if not result.has_more: break
                logger.info("Fetching next page of Dropbox files...")
                result = self.service.files_list_folder_continue(result.cursor)

        except ApiError as err:
            if isinstance(err.error, dropbox.files.ListFolderError) and err.error.is_path() and err.error.get_path().is_not_folder():
                 logger.warning(f"Dropbox path '{folder_path}' is not a folder.")
                 return []
            else:
                logger.error(f"Dropbox API error during listFiles (Bucket {self.bucket_number}): {err}")
                return []
        except Exception as e:
            logger.error(f"An unexpected error occurred during Dropbox listFiles (Bucket {self.bucket_number}): {e}", exc_info=True)
            return []

        logger.info(f"Dropbox listFiles (Bucket {self.bucket_number}) found {len(files_list)} files in '{folder_path}'.")
        return files_list[:max_results] if max_results else files_list


    def check_storage(self) -> tuple[int, int]:
        """
        Check the storage quota for the authenticated Dropbox account.
        (No changes needed here for Step D)
        """
        if not self.service: logger.error("Service not authenticated."); return 0, 0
        try:
            usage = self.service.users_get_space_usage(); allocation = usage.allocation.get_individual() if usage.allocation.is_individual() else usage.allocation.get_team()
            limit = allocation.allocated if allocation else 0; usage_used = usage.used
            logger.info(f"Dropbox Storage (Bucket {self.bucket_number}): {usage_used / (1024**3):.2f} GB used / {limit / (1024**3):.2f} GB total.")
            return limit, usage_used
        except ApiError as err: logger.error(f"Dropbox API error checking storage (Bucket {self.bucket_number}): {err}"); return 0, 0
        except Exception as e: logger.error(f"Unexpected error checking Dropbox storage (Bucket {self.bucket_number}): {e}"); return 0, 0

    def searchFiles(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Searches for files matching ANY of the query keywords using files_search_v2.
        Returns file metadata including bucket number and access token.
        """
        if not self.service: logger.error("Dropbox service not authenticated for search."); return []
        if self.bucket_number is None: logger.error("Dropbox service authenticated but bucket_number is missing."); return []

        files_list = []
        try:
            # The query string itself for Dropbox search v2 often handles OR implicitly
            # We just pass the space-separated keywords extracted by the LLM.
            logger.info(f"Executing Dropbox search (Bucket {self.bucket_number}) with query terms: '{query}'")

            search_options = SearchOptions(
                max_results=min(limit * 2, 100), # Fetch more to filter folders/limit
                order_by=SearchOrderBy.relevance, # Use relevance
                file_status=FileStatus.active,
                # --- Use OR logic explicitly if simple query isn't enough ---
                # mode=SearchMode.filename_and_content # Search name and content
                # For v2, just passing the query string usually implies OR between terms for content search.
                # Let's stick with the default implicit OR for now.
            )

            # The query string is just the space-separated keywords
            result = self.service.files_search_v2(query=query, options=search_options)

            count = 0
            for match in result.matches:
                if count >= limit: break
                metadata = match.metadata.get_metadata()
                if isinstance(metadata, FileMetadata): # Only files
                    try:
                        link_result = self.service.files_get_temporary_link(metadata.path_display); file_link = link_result.link
                    except ApiError as link_err:
                        logger.debug(f"Could not get temp link for {metadata.name}: {link_err}."); file_link = f"dropbox:{metadata.path_lower}"

                    access_token = None
                    if hasattr(self.service, 'session') and hasattr(self.service.session, 'access_token'): access_token = self.service.session.access_token
                    elif hasattr(self.service, '_oauth2_access_token'): access_token = self.service._oauth2_access_token
                    if not access_token: logger.warning(f"Could not retrieve access token for Dropbox Bucket {self.bucket_number} during search.")

                    files_list.append({
                        "id": metadata.id, "name": metadata.name, "size": metadata.size,
                        "path_lower": metadata.path_lower, "path": file_link,
                        "provider": "Dropbox", "bucket": self.bucket_number,
                        "access_token": access_token
                    })
                    count += 1

            # TODO: Handle pagination with result.has_more and result.cursor if needed

        except ApiError as err: logger.error(f"Dropbox API error during searchFiles (Bucket {self.bucket_number}): {err}"); return files_list
        except Exception as e: logger.error(f"Unexpected error during Dropbox searchFiles (Bucket {self.bucket_number}): {e}"); return []

        logger.info(f"Dropbox search (Bucket {self.bucket_number}) found {len(files_list)} files for query '{query}'.")
        return files_list[:limit]


# --- END OF FILE Dropbox.py ---