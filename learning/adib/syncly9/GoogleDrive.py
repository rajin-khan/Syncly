# --- START OF FILE GoogleDrive.py ---

import os
import logging
import io # Keep io import if used elsewhere, not directly needed here
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from Service import Service
from Database import Database
from typing import List, Dict, Optional

# Set up logging
# logging.basicConfig(level=logging.INFO) # Configure in api.py or main script
logger = logging.getLogger(__name__)

class GoogleDrive(Service):
    def __init__(self, token_dir="tokens", credentials_file="credentials.json"):
        self.token_dir = token_dir
        self.credentials_file = credentials_file
        self.service = None
        self.bucket_number: Optional[int] = None # <--- Add bucket_number attribute
        os.makedirs(self.token_dir, exist_ok=True)
        self.db = Database().get_instance()

    def authenticate(self, bucket_number, user_id):
        """
        Authenticate with Google Drive using AuthManager.
        Stores the bucket_number on the instance upon successful authentication.
        """
        from AuthManager import AuthManager
        auth_manager = AuthManager(user_id, self.token_dir)
        self.service = auth_manager.authenticate_google_drive(bucket_number, self.credentials_file)
        if self.service:
            self.bucket_number = bucket_number # <--- Store bucket number on success
            logger.info(f"GoogleDrive instance authenticated for bucket {self.bucket_number}")
        else:
            logger.error(f"GoogleDrive authentication failed for bucket {bucket_number}")
            self.bucket_number = None
        return self.service

    def listFiles(self, max_results: Optional[int] = None, query: Optional[str] = None) -> List[Dict]:
        """
        List files from Google Drive with correct web links.
        Includes an internal limit to prevent excessive fetching on large drives.
        (No changes needed here for Step D)
        """
        if not self.service:
            raise ValueError("Google Drive service not authenticated. Call authenticate() first.")

        files_list = []
        page_token = None
        query_filter = f"trashed = false" # Basic filter: not in trash
        if query:
            # Escape single quotes in user query for safety
            safe_query = query.replace("'", "\\'")
            query_filter += f" and name contains '{safe_query}'"

        page_size = min(max_results, 100) if max_results and 0 < max_results <= 100 else 100
        INTERNAL_FETCH_LIMIT = 200 # Stop fetching pages after collecting this many files

        try:
            while True:
                if len(files_list) >= INTERNAL_FETCH_LIMIT:
                     logger.info(f"Reached internal fetch limit ({INTERNAL_FETCH_LIMIT}) for Google Drive listFiles. Stopping page fetching.")
                     break

                logger.debug(f"Fetching Google Drive page, current count: {len(files_list)}, page_token: {page_token}, query: {query_filter}")
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
                        "size": file.get("size"), # Keep as number or None
                        "mimeType": file.get("mimeType"), # Include mimeType
                        "path": file.get("webViewLink", f"https://drive.google.com/file/d/{file.get('id')}/view"), # Prefer webViewLink
                        "provider": "GoogleDrive",
                        # "bucket": self.bucket_number # Add bucket if needed for listing elsewhere
                    })
                    if max_results and len(files_list) >= max_results:
                        logger.info(f"Reached requested max_results ({max_results}) for Google Drive listFiles.")
                        return files_list[:max_results]
                    if len(files_list) >= INTERNAL_FETCH_LIMIT:
                         break

                if len(files_list) >= INTERNAL_FETCH_LIMIT:
                    logger.info(f"Reached internal fetch limit ({INTERNAL_FETCH_LIMIT}) after processing page. Stopping.")
                    break

                page_token = results.get("nextPageToken")
                if not page_token:
                    logger.debug("No more pages found from Google Drive.")
                    break

        except HttpError as error:
            logger.error(f"An HTTP error occurred during Google Drive listFiles: {error}")
            return [] # Return empty list on error
        except Exception as e:
             logger.error(f"An unexpected error occurred during Google Drive listFiles: {e}", exc_info=True)
             return []

        logger.info(f"Google Drive listFiles returning {len(files_list)} files.")
        return files_list[:max_results] if max_results else files_list


    def check_storage(self) -> tuple[int, int]:
        """
        Check the storage quota for the authenticated Google Drive account.
        (No changes needed here for Step D)
        """
        if not self.service: logger.error("Service not authenticated."); return 0, 0
        try:
            res = self.service.about().get(fields='storageQuota').execute()
            limit = int(res['storageQuota'].get('limit', 0)); usage = int(res['storageQuota'].get('usage', 0))
            logger.info(f"Google Drive Storage (Bucket {self.bucket_number}): {usage / (1024**3):.2f} GB used / {limit / (1024**3):.2f} GB total.")
            return limit, usage
        except HttpError as error: logger.error(f"An error occurred checking Google Drive storage (Bucket {self.bucket_number}): {error}"); return 0, 0
        except Exception as e: logger.error(f"Unexpected error checking GDrive storage (Bucket {self.bucket_number}): {e}"); return 0, 0

# In GoogleDrive.py

    def searchFiles(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Searches for files matching the query string (keywords) in name or content using OR logic.
        Returns file metadata including the bucket number.
        """
        if not self.service: logger.error("Google Drive service not authenticated for search."); return []
        if self.bucket_number is None: logger.error("Google Drive service authenticated but bucket_number is missing."); return []

        files_list = []
        page_token = None

        # --- Build OR Query ---
        keywords = query.split() # Assumes keywords are space-separated
        if not keywords:
             logger.warning("Empty keyword list received for GDrive search.")
             return []

        query_parts = []
        for keyword in keywords:
            safe_keyword = keyword.replace("'", "\\'") # Escape single quotes
            if safe_keyword: # Avoid empty strings
                query_parts.append(f"name contains '{safe_keyword}'")
                query_parts.append(f"fullText contains '{safe_keyword}'")

        if not query_parts:
             logger.warning("No valid query parts generated for GDrive search.")
             return []

        # Combine parts with 'or', add 'trashed = false'
        search_query = f"({' or '.join(query_parts)}) and trashed = false"
        # --- End Build OR Query ---

        logger.info(f"Executing Google Drive OR search (Bucket {self.bucket_number}) with query: {search_query}")

        try:
            # (Rest of the search loop logic remains the same as before)
            while len(files_list) < limit:
                page_size = min(limit - len(files_list), 100)
                results = self.service.files().list(
                    pageSize=page_size,
                    fields="nextPageToken, files(id, name, mimeType, size, webViewLink)",
                    pageToken=page_token,
                    q=search_query,
                    orderBy="modifiedTime desc" # Prioritize recently modified? Or relevance? Drive default might be okay.
                ).execute()

                for file in results.get("files", []):
                    files_list.append({
                        "id": file.get("id"), "name": file.get("name", "Unknown"),
                        "size": file.get("size"), "mimeType": file.get("mimeType"),
                        "path": file.get("webViewLink", f"https://drive.google.com/file/d/{file.get('id')}/view"),
                        "provider": "GoogleDrive", "bucket": self.bucket_number
                    })
                    if len(files_list) >= limit: break
                if len(files_list) >= limit: break

                page_token = results.get("nextPageToken")
                if not page_token: break

        except HttpError as error: logger.error(f"An HTTP error occurred during GDrive searchFiles (Bucket {self.bucket_number}): {error}"); return files_list
        except Exception as e: logger.error(f"Unexpected error during GDrive searchFiles (Bucket {self.bucket_number}): {e}"); return []

        logger.info(f"Google Drive search (Bucket {self.bucket_number}) found {len(files_list)} files for OR query.")
        return files_list[:limit]

# --- END OF FILE GoogleDrive.py ---