# --- START OF FILE GoogleDrive.py ---

import os
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError # Added HttpError import
from Service import Service
from Database import Database
from typing import List, Dict, Optional # Added typing imports

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleDrive(Service):
    def __init__(self, token_dir="tokens", credentials_file="credentials.json"):
        self.token_dir = token_dir
        self.credentials_file = credentials_file
        self.service = None
        os.makedirs(self.token_dir, exist_ok=True)
        self.db = Database().get_instance()

    def authenticate(self, bucket_number, user_id):
        """
        Authenticate with Google Drive using AuthManager.
        """
        from AuthManager import AuthManager
        auth_manager = AuthManager(user_id, self.token_dir)
        self.service = auth_manager.authenticate_google_drive(bucket_number, self.credentials_file)
        return self.service

    def listFiles(self, max_results: Optional[int] = None, query: Optional[str] = None) -> List[Dict]:
        """
        List files from Google Drive with correct web links.
        Includes an internal limit to prevent excessive fetching on large drives.
        """
        if not self.service:
            raise ValueError("Google Drive service not authenticated. Call authenticate() first.")

        files_list = []
        page_token = None
        # Simple name contains query for basic listing/filtering
        query_filter = f"name contains '{query}'" if query else None
        # Use max_results if provided and valid, otherwise default page size
        page_size = min(max_results, 100) if max_results and 0 < max_results <= 100 else 100
        # --- Internal Limit ---
        # Set a limit on the total number of files to process to prevent extreme delays
        # This acts as a safety net if max_results isn't specified or is large.
        INTERNAL_FETCH_LIMIT = 200 # Stop fetching pages after collecting this many files
        # --- End Internal Limit ---


        try:
            while True:
                # --- Check Internal Limit ---
                if len(files_list) >= INTERNAL_FETCH_LIMIT:
                     logger.info(f"Reached internal fetch limit ({INTERNAL_FETCH_LIMIT}) for Google Drive listFiles. Stopping page fetching.")
                     break
                # --- End Check ---

                logger.debug(f"Fetching Google Drive page, current count: {len(files_list)}, page_token: {page_token}")
                results = self.service.files().list(
                    pageSize=page_size,
                    fields="nextPageToken, files(id, name, mimeType, size, webViewLink)", # Added webViewLink
                    pageToken=page_token,
                    q=query_filter,
                    # Use default corpora and spaces (usually 'user' and 'drive')
                    orderBy="name" # Sort alphabetically
                ).execute()

                page_files = results.get("files", [])
                logger.debug(f"Got {len(page_files)} files from Google Drive page.")

                for file in page_files:
                    files_list.append({
                        "id": file.get("id"),
                        "name": file.get("name", "Unknown"),
                        "size": file.get("size", "Unknown"),
                        "path": file.get("webViewLink", f"https://drive.google.com/file/d/{file.get('id')}/view"), # Prefer webViewLink
                        "provider": "GoogleDrive"
                    })
                    # Stop if max_results (if specified by caller) is reached
                    if max_results and len(files_list) >= max_results:
                        logger.info(f"Reached requested max_results ({max_results}) for Google Drive listFiles.")
                        # Return exactly max_results
                        return files_list[:max_results]

                    # Also check internal limit after adding each file
                    if len(files_list) >= INTERNAL_FETCH_LIMIT:
                         break # Break inner loop too

                # Check internal limit again before fetching next page
                if len(files_list) >= INTERNAL_FETCH_LIMIT:
                    logger.info(f"Reached internal fetch limit ({INTERNAL_FETCH_LIMIT}) after processing page. Stopping.")
                    break


                page_token = results.get("nextPageToken")
                if not page_token:
                    logger.debug("No more pages found from Google Drive.")
                    break # No more pages

        except HttpError as error:
            logger.error(f"An HTTP error occurred during Google Drive listFiles: {error}")
            return [] # Return empty list on error
        except Exception as e:
             logger.error(f"An unexpected error occurred during Google Drive listFiles: {e}", exc_info=True)
             return []

        logger.info(f"Google Drive listFiles returning {len(files_list)} files.")
        # Apply max_results limit again at the end, just in case
        return files_list[:max_results] if max_results else files_list


    def check_storage(self) -> tuple[int, int]:
        """
        Check the storage quota for the authenticated Google Drive account.
        """
        # (Keep implementation as is)
        if not self.service: logger.error("Service not authenticated."); return 0, 0
        try:
            res = self.service.about().get(fields='storageQuota').execute()
            limit = int(res['storageQuota'].get('limit', 0)); usage = int(res['storageQuota'].get('usage', 0))
            logger.info(f"Google Drive Storage: {usage / (1024**3):.2f} GB used / {limit / (1024**3):.2f} GB total.")
            return limit, usage
        except HttpError as error: logger.error(f"An error occurred checking Google Drive storage: {error}"); return 0, 0
        except Exception as e: logger.error(f"Unexpected error checking GDrive storage: {e}"); return 0, 0

    def searchFiles(self, query: str, limit: int = 10) -> List[Dict]:
        """Searches for files matching the query string in name or content."""
        # (Keep implementation as is - search is usually faster/indexed differently)
        if not self.service: logger.error("Google Drive service not authenticated for search."); return []
        files_list = []
        page_token = None
        search_query = f"(name contains '{query}' or fullText contains '{query}') and trashed = false"
        logger.info(f"Executing Google Drive search with query: {search_query}")
        try:
            while len(files_list) < limit:
                results = self.service.files().list(
                    pageSize=min(limit - len(files_list), 100),
                    fields="nextPageToken, files(id, name, mimeType, size, webViewLink)",
                    pageToken=page_token, q=search_query, orderBy="modifiedTime desc"
                ).execute()
                for file in results.get("files", []):
                    files_list.append({"id": file.get("id"), "name": file.get("name", "Unknown"), "size": file.get("size", "Unknown"), "path": file.get("webViewLink", f"https://drive.google.com/file/d/{file.get('id')}/view"), "provider": "GoogleDrive"})
                    if len(files_list) >= limit: break
                page_token = results.get("nextPageToken")
                if not page_token: break
        except HttpError as error: logger.error(f"An HTTP error occurred during GDrive searchFiles: {error}"); return files_list
        except Exception as e: logger.error(f"Unexpected error during GDrive searchFiles: {e}"); return []
        logger.info(f"Google Drive search found {len(files_list)} files for query '{query}'.")
        return files_list[:limit]


# --- END OF FILE GoogleDrive.py ---