# --- START OF FILE api.py ---

import asyncio
import base64
import hashlib
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import JWTError, jwt
# from passlib.context import CryptContext # Not used currently
from datetime import datetime, timedelta
import os
from AuthManager import AuthManager
from DriveManager import DriveManager # Import DriveManager
from fastapi.staticfiles import StaticFiles
import shutil
from bson import ObjectId
import dropbox
import logging
import mimetypes
from typing import List, Optional, Dict # Added Dict
from fastapi.responses import FileResponse, RedirectResponse
from Database import Database
from GoogleDrive import GoogleDrive
from Dropbox import DropboxService
from GDriveFile import GoogleDriveFile
from DropBoxFile import DropBoxFile
from groq import Groq # Import Groq
from fastapi import Body
from dotenv import load_dotenv
from collections import defaultdict
import re # Import re for parsing

# --- Import for simple Keyword Extraction (Fallback) ---
import string
from stop_words import get_stop_words
# --- End Import ---


load_dotenv()

# Load Groq API key from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY") # Removed default
if not GROQ_API_KEY:
    print("Warning: GROQ_API_KEY environment variable not set.")
    # Decide if the app should fail to start or just disable LLM features
    # exit("Error: Groq API Key not configured.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# Set requests logger level higher to reduce noise if needed
# logging.getLogger("requests").setLevel(logging.WARNING)
# logging.getLogger("urllib3").setLevel(logging.WARNING)
# logging.getLogger("googleapiclient").setLevel(logging.WARNING)

logger = logging.getLogger("syncly-api")


app = FastAPI(title="Syncly API")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-please-change") # Emphasize changing default
if SECRET_KEY == "your-secret-key-please-change":
     logger.warning("Security warning: SECRET_KEY is set to the default value.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 240)) # Use env var

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") # Not used
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") # Relative URL works fine with FastAPI

# --- Pydantic Models (Keep as is) ---
# ... (UserCreate, UserResponse, Token, TokenData, StorageInfo, etc.) ...
class UserCreate(BaseModel): username: str; password: str; email: str
class UserResponse(BaseModel): username: str; email: str
class Token(BaseModel): access_token: str; token_type: str
class TokenData(BaseModel): username: str | None = None
class StorageInfo(BaseModel): provider: str; drive_number: int; storage_limit_gb: float; used_storage_gb: float; free_storage_gb: float
class StorageSummary(BaseModel): storages: List[StorageInfo]; total_storage_gb: float; used_storage_gb: float; free_storage_gb: float
class FileInfo(BaseModel): id: Optional[str] = None; name: str; provider: str; size: str; path: str
class AddDriveRequest(BaseModel): drive_type: str
class AskRequest(BaseModel): question: str; user_id: str
class ResetRequest(BaseModel): user_id: str


# Global session memory (Keep as is)
session_memory = defaultdict(list)

# --- Helper functions (Keep as is) ---
# ... (get_password_hash, verify_password, create_access_token) ...
def get_password_hash(password: str) -> str:
    sha256_hash = hashlib.sha256(password.encode('utf-8')).digest()
    return base64.b64encode(sha256_hash).decode('utf-8')
def verify_password(plain_password: str, hashed_password: str) -> bool:
    input_hash = get_password_hash(plain_password); return input_hash == hashed_password
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict:
    # (Keep implementation as is from previous step)
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None: raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError as e: raise credentials_exception from e
    db = Database().get_instance()
    user = db.users_collection.find_one({"username": token_data.username})
    if user is None: raise credentials_exception
    return user

# --- Simple Keyword Extraction Helper (Fallback - Keep as is) ---
def extract_keywords_simple(text: str, min_len: int = 3) -> str:
    # ... (Keep implementation as is) ...
    if not text: return ""
    try:
        text = text.lower().translate(str.maketrans('', '', string.punctuation))
        stop_words_list = get_stop_words('en')
        keywords = [word for word in text.split() if word not in stop_words_list and len(word) >= min_len]
        keyword_string = " ".join(keywords)
        logger.debug(f"Simple extracted keywords: '{keyword_string}' from text: '{text[:50]}...'")
        return keyword_string
    except Exception as e: logger.error(f"Error during simple keyword extraction: {e}", exc_info=True); return ""

# --- LLM-Based Keyword Extraction Helper (REVISED) ---
async def get_search_keywords_from_llm(question: str) -> str:
    """
    Uses a preliminary LLM call to extract search keywords from the user's question.
    Includes improved prompting and parsing.
    """
    if not question:
        return ""
    if not GROQ_API_KEY:
        logger.warning("Groq API key not available, cannot use LLM for keyword extraction.")
        return "" # Cannot proceed without API key

    keyword_model = "llama-3.1-8b-instant" # Fast model suitable for this task

    # --- Revised System Prompt ---
    system_prompt = (
        "Your task is to extract the 1-3 main keywords or topics from the User Question below, "
        "which will be used to search a file system. Focus on nouns and essential terms. "
        "Output *only* the keywords, separated by a single space. Do not use punctuation. Do not add any explanation or introductory text. "
        "Example 1: User Question: 'Do I have notes about the French Revolution?' Output: 'french revolution notes'\n"
        "Example 2: User Question: 'search for budget spreadsheet 2024' Output: 'budget spreadsheet 2024'\n"
        "Example 3: User Question: 'what files mention the Project Alpha deadline?' Output: 'project alpha deadline'"
    )
    # --- End Revised System Prompt ---

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"User Question: '{question}'"} # Clearly label input
    ]

    try:
        logger.info(f"Getting search keywords from LLM ({keyword_model}) for question: '{question[:50]}...'")
        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model=keyword_model,
            messages=messages,
            temperature=0.1, # Very low temperature for deterministic output
            max_tokens=50,  # Limit output length significantly
            # Consider adding stop sequences if the model tends to add extra phrases
            # stop=["\n", "Keywords:", "Output:"]
        )
        raw_keywords = completion.choices[0].message.content.strip()
        logger.info(f"Raw LLM keyword response: '{raw_keywords}'") # Log the raw response

        # --- Revised Parsing ---
        # Lowercase, remove potential leading/trailing quotes, colons, etc.
        keywords = raw_keywords.lower()
        # Remove common prefixes the LLM might still add
        prefixes_to_remove = ["keywords:", "output:", "keywords ", "output "]
        for prefix in prefixes_to_remove:
            if keywords.startswith(prefix):
                keywords = keywords[len(prefix):].strip()
        # Remove punctuation just in case
        keywords = keywords.translate(str.maketrans('', '', string.punctuation))
        # Remove extra whitespace
        keywords = re.sub(r'\s+', ' ', keywords).strip()
        # --- End Revised Parsing ---

        if not keywords:
             logger.warning("LLM keyword extraction returned an empty string after parsing.")
             # Fallback? Or just return empty? Let's try fallback.
             logger.warning("Falling back to simple keyword extraction due to empty LLM response.")
             return extract_keywords_simple(question)

        logger.info(f"Cleaned LLM extracted keywords: '{keywords}'")
        return keywords

    except Exception as e:
        logger.error(f"Groq API call failed during keyword extraction: {e}", exc_info=True)
        logger.warning("Falling back to simple keyword extraction due to API error.")
        return extract_keywords_simple(question)

# --- API Endpoints (Authentication, Storage, Drives - Keep as is) ---
@app.post("/register", status_code=status.HTTP_201_CREATED, tags=["Auth"])
async def register(user_data: UserCreate): # Use UserCreate model
    db = Database().get_instance()
    if db.users_collection.find_one({"username": {"$regex": f"^{user_data.username}$", "$options": "i"}}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
    if db.users_collection.find_one({"email": {"$regex": f"^{user_data.email}$", "$options": "i"}}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    hashed_password = get_password_hash(user_data.password)
    user_doc = {
        "username": user_data.username, "password": hashed_password, "email": user_data.email,
        "drives": [], "created_at": datetime.utcnow()
    }
    result = db.users_collection.insert_one(user_doc)
    logger.info(f"User '{user_data.username}' registered successfully with ID: {result.inserted_id}")
    return {"message": "User registered successfully"}

@app.post("/token", response_model=Token, tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    db = Database().get_instance(); user = db.users_collection.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user["password"]):
        logger.warning(f"Login failed for username: {form_data.username}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    access_token = create_access_token(data={"sub": user["username"]})
    logger.info(f"Login successful for {form_data.username}")
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/validate-token", tags=["Auth"])
async def validate_token(token: str = Query(..., description="JWT token to validate")):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]); username: str | None = payload.get("sub")
        if username is None: raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: No username found")
        db = Database().get_instance();
        if not db.users_collection.find_one({"username": username}): raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: User not found")
        return {"username": username}
    except JWTError as e: logger.error(f"JWT decoding failed during validation: {str(e)}"); raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    except HTTPException as e: raise e
    except Exception as e: logger.error(f"Unexpected error during token validation: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Token validation error")

@app.get("/users/me", response_model=UserResponse, tags=["Users"])
async def read_users_me(current_user: Dict = Depends(get_current_user)):
    return UserResponse(username=current_user["username"], email=current_user["email"])

@app.get("/storage", response_model=StorageSummary, tags=["Storage"])
async def get_storage_info(current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id)
    if not drive_manager.drives: return StorageSummary(storages=[], total_storage_gb=0, used_storage_gb=0, free_storage_gb=0)
    storages_info, total_limit, total_usage = drive_manager.check_all_storages()
    storage_details = [StorageInfo(provider=s["Provider"], drive_number=s["Drive Number"], storage_limit_gb=s["Storage Limit (bytes)"], used_storage_gb=s["Used Storage (bytes)"], free_storage_gb=s["Free Storage"]) for s in storages_info]
    total_storage_gb = round(total_limit / (1024**3), 2) if total_limit else 0
    used_storage_gb = round(total_usage / (1024**3), 2) if total_usage else 0
    free_storage_gb = round((total_limit - total_usage) / (1024**3), 2) if (total_limit - total_usage) > 0 else 0
    return StorageSummary(storages=storage_details, total_storage_gb=total_storage_gb, used_storage_gb=used_storage_gb, free_storage_gb=free_storage_gb)

@app.post("/drives", tags=["Storage"])
async def add_drive(request: AddDriveRequest, current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); db = Database().get_instance()
    existing_drives_count = db.drives_collection.count_documents({"user_id": user_id}); bucket_number = existing_drives_count + 1
    logger.info(f"Attempting to add drive type '{request.drive_type}' as bucket #{bucket_number} for user {current_user['username']}")
    response_data = {"status": "failed", "message": "Unknown drive type"}
    try:
        if request.drive_type == "GoogleDrive":
            google_drive_instance = GoogleDrive(); drive_manager.add_drive(google_drive_instance, bucket_number, drive_type="GoogleDrive")
            response_data = {"status": "success", "message": f"Google Drive added as bucket {bucket_number}. Please follow any browser prompts."}
        elif request.drive_type == "Dropbox":
            dropbox_app_key=os.getenv("DROPBOX_APP_KEY", "w84emdpux17qpnj"); dropbox_app_secret=os.getenv("DROPBOX_APP_SECRET", "x6ce7dtmj51xqc7")
            if not dropbox_app_key or not dropbox_app_secret: raise HTTPException(status_code=500, detail="Dropbox app key/secret not configured.")
            dropbox_service_instance = DropboxService(app_key=dropbox_app_key, app_secret=dropbox_app_secret)
            drive_manager.add_drive(dropbox_service_instance, bucket_number, drive_type="Dropbox")
            response_data = {"status": "success", "message": f"Dropbox added as bucket {bucket_number}. Please follow browser prompts."}
        else: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid drive type. Choose 'GoogleDrive' or 'Dropbox'")
        return response_data
    except HTTPException as e: raise e
    except Exception as e: logger.error(f"Failed to add drive for user {current_user['username']}: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to add {request.drive_type}. Error occurred.")

@app.get("/viewfiles", response_model=List[FileInfo], tags=["Files"])
async def list_files( query: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); username = current_user['username']
    if not drive_manager.drives: return []
    all_files = []; seen_files = set()
    for drive in drive_manager.drives:
        try:
            files = drive.listFiles(query=query); provider = type(drive).__name__
            for file in files:
                file_name = file.get("name", "Unknown")
                if file_name not in seen_files:
                    size = file.get("size", "Unknown"); size_str = str(size) if size is not None else "Unknown"
                    all_files.append(FileInfo(id=file.get("id"), name=file_name, provider=file.get("provider", provider), size=size_str, path=file.get("path", "N/A")))
                    seen_files.add(file_name)
        except Exception as e: logger.error(f"Error retrieving files from {type(drive).__name__} for user {username}: {e}", exc_info=True)
    all_files.sort(key=lambda x: x.name.lower()); paginated_files = all_files[offset : offset + limit]
    logger.info(f"Returning {len(paginated_files)} files (offset: {offset}, limit: {limit}) out of {len(all_files)} total found for user {username}")
    return paginated_files

@app.get("/search_files", response_model=List[FileInfo], tags=["Files"])
async def search_files( query: str = Query(...), limit: int = Query(10, ge=1, le=50), current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); username = current_user['username']
    if not drive_manager.drives: return []
    logger.info(f"User {username} (ID: {str(user_id)}) searching for '{query}' with limit {limit}")
    try:
        matching_files_data = drive_manager.search_files_for_llm(query=query, limit_per_drive=limit, total_limit=limit)
        results = []
        for file_data in matching_files_data:
             size = file_data.get("size", "Unknown"); size_str = str(size) if size is not None else "Unknown"
             results.append(FileInfo(id=file_data.get("id"), name=file_data.get("name", "Unknown"), provider=file_data.get("provider", "Unknown"), size=size_str, path=file_data.get("path", "N/A")))
        logger.info(f"Returning {len(results)} matching files for query '{query}' for user {username}")
        return results
    except Exception as e: logger.error(f"Error searching files for user {username}: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error searching files.")

@app.post("/files/upload", tags=["Files"])
async def upload_file_endpoint( file: UploadFile = File(...), current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; username = current_user["username"]; upload_dir = "uploads"; os.makedirs(upload_dir, exist_ok=True)
    safe_filename = os.path.basename(file.filename or "uploaded_file"); temp_file_location = os.path.join(upload_dir, f"{user_id}_{safe_filename}")
    try:
        with open(temp_file_location, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
        logger.info(f"Temporary file saved at: {temp_file_location} for user {username}")
    except Exception as e: logger.error(f"Failed to save temporary upload file for user {username}: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save uploaded file.")
    finally: file.file.close()
    drive_manager = DriveManager(user_id=user_id); sorted_buckets = drive_manager.get_sorted_buckets()
    if not drive_manager.drives: os.remove(temp_file_location); raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No connected drives found.")
    if not sorted_buckets: os.remove(temp_file_location); raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No available storage space found.")
    best_bucket_info = sorted_buckets[0]; best_drive_instance = best_bucket_info[1]; drive_index = best_bucket_info[2]; provider = type(best_drive_instance).__name__; bucket_display_number = drive_index + 1
    logger.info(f"Attempting to upload '{safe_filename}' to {provider} (Bucket {bucket_display_number}) for user {username}")
    try:
        if isinstance(best_drive_instance, GoogleDrive):
            gdrive_file_handler = GoogleDriveFile(drive_manager); mime_type = file.content_type or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
            gdrive_file_handler.upload_file(temp_file_location, safe_filename, mime_type)
        elif isinstance(best_drive_instance, DropboxService):
             if not hasattr(best_drive_instance, 'service') or not best_drive_instance.service: raise Exception("Dropbox service instance not properly authenticated.")
             access_token = None
             if hasattr(best_drive_instance.service, '_oauth2_access_token'): access_token = best_drive_instance.service._oauth2_access_token
             elif hasattr(best_drive_instance.service, 'session') and hasattr(best_drive_instance.service.session, 'access_token'): access_token = best_drive_instance.service.session.access_token
             if not access_token: logger.error("Could not retrieve access token from Dropbox."); raise Exception("Failed to get Dropbox access token for upload.")
             dropbox_file_handler = DropBoxFile(access_token, drive_manager); dropbox_file_handler.upload_file(temp_file_location, safe_filename)
        else: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported drive type: {provider}")
        logger.info(f"Successfully uploaded '{safe_filename}' to {provider} (Bucket {bucket_display_number}) for user {username}")
        return {"status": "success", "message": f"File '{safe_filename}' uploaded to {provider} (Bucket {bucket_display_number})"}
    except Exception as e: logger.error(f"Error uploading file to {provider} for user {username}: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload failed: {e}")
    finally:
        if os.path.exists(temp_file_location):
            try: os.remove(temp_file_location); logger.info(f"Cleaned up temp upload file: {temp_file_location}")
            except OSError as e: logger.warning(f"Could not remove temp upload file {temp_file_location}: {e}")

@app.get("/files/download", tags=["Files"])
async def download_file_endpoint( file_name: str = Query(...), current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; username = current_user["username"]; drive_manager = DriveManager(user_id=user_id); download_dir = "downloads"; os.makedirs(download_dir, exist_ok=True)
    logger.info(f"User {username} requesting download for file: '{file_name}'")
    if not drive_manager.drives: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No connected drives.")
    try: # GDrive
        gdrive_file_handler = GoogleDriveFile(drive_manager); user_download_path = os.path.join(download_dir, str(user_id))
        downloaded_file_path = gdrive_file_handler.download_from_all_buckets(file_name, user_download_path)
        if downloaded_file_path and os.path.exists(downloaded_file_path):
            mime_type, _ = mimetypes.guess_type(downloaded_file_path); fname=os.path.basename(downloaded_file_path)
            return FileResponse(path=downloaded_file_path, filename=fname, media_type=mime_type or "app/octet-stream", headers={"Content-Disposition": f"attachment; filename=\"{fname}\""})
    except Exception as e: logger.error(f"Error checking/downloading GDrive for user {username}, file '{file_name}': {e}", exc_info=True)
    try: # Dropbox
        dropbox_accounts = [d for d in drive_manager.drives if isinstance(d, DropboxService)]
        for dropbox_service in dropbox_accounts:
             access_token = None;
             if hasattr(dropbox_service.service, '_oauth2_access_token'): access_token = dropbox_service.service._oauth2_access_token
             if not access_token: logger.warning(f"Skipping Dropbox search for {username}: No access token."); continue
             dropbox_file_handler = DropBoxFile(access_token, drive_manager); dropbox_api_path = dropbox_file_handler.search_file(file_name)
             if dropbox_api_path:
                 user_download_path = os.path.join(download_dir, str(user_id)); os.makedirs(user_download_path, exist_ok=True); local_save_path = os.path.join(user_download_path, os.path.basename(dropbox_api_path))
                 dropbox_file_handler.download_file(dropbox_api_path, local_save_path)
                 if os.path.exists(local_save_path):
                     mime_type, _ = mimetypes.guess_type(local_save_path); fname=os.path.basename(local_save_path)
                     return FileResponse(path=local_save_path, filename=fname, media_type=mime_type or "app/octet-stream", headers={"Content-Disposition": f"attachment; filename=\"{fname}\""})
                 else: logger.error(f"Dropbox download OK but file missing at {local_save_path}")
    except Exception as e: logger.error(f"Error checking/downloading Dropbox for user {username}, file '{file_name}': {e}", exc_info=True)
    logger.warning(f"File '{file_name}' not found for user {username}.")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File '{file_name}' not found.")


# --- LLM Endpoints ---
@app.post("/llm/ask", tags=["LLM"])
async def llm_ask_endpoint(
    request_data: AskRequest, # Use Pydantic model for request body
    current_user: Dict = Depends(get_current_user) # Enforce JWT authentication
):
    """Handles LLM queries, incorporating conversation memory and file context derived from LLM-extracted keywords."""
    original_question = request_data.question
    telegram_user_id = request_data.user_id # For memory lookup
    user_id = current_user["_id"] # MongoDB ObjectId
    username = current_user["username"]

    if not GROQ_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM service is not configured (API key missing).")

    logger.info(f"User {username} (TG ID: {telegram_user_id}) asking LLM: '{original_question}'")

    # --- Step 1: Get Search Keywords using LLM ---
    search_query = await get_search_keywords_from_llm(original_question) # Await the async helper
    if not search_query:
        logger.info("LLM did not provide keywords, or failed. Skipping file search.")
        file_context_str = "\n(Note: Could not determine relevant keywords from the question to search files.)"
    else:
        logger.info(f"Using LLM-extracted keywords for file search: '{search_query}'")
        # --- Step 2: Fetch File Context using extracted keywords ---
        file_context_str = ""
        try:
            drive_manager = DriveManager(user_id=user_id)
            relevant_files = drive_manager.search_files_for_llm(
                query=search_query, # Use LLM-generated keywords
                limit_per_drive=5,
                total_limit=10
            )

            if relevant_files:
                file_lines = ["Based on your question, I found these potentially relevant files:"]
                for file in relevant_files:
                    file_lines.append(f"- {file.get('name', 'Unknown Name')} ({file.get('provider', 'Unknown Provider')})")
                file_context_str = "\n".join(file_lines)
                logger.info(f"Generated file context:\n{file_context_str}")
            else:
                logger.info("No relevant files found for extracted keywords.")
                file_context_str = "\n(Note: No specific files matching the likely keywords were found in your drives.)"

        except Exception as e:
            logger.error(f"Error fetching file context for user {username}: {e}", exc_info=True)
            file_context_str = "\n(Note: Could not retrieve file context due to an error.)"
    # --- End Fetch File Context ---


    # --- Step 3: Prepare messages for Final Groq Answer ---
    memory = session_memory.get(telegram_user_id, [])

    system_prompt = (
        "You are Syncly AI, a helpful assistant integrated into the Syncly file management application. "
        "Answer the user's questions concisely based *primarily* on the provided conversation history and the list of potentially relevant files found in their connected cloud drives. "
        "The file list was generated based on keywords extracted from the user's most recent question. "
        "If the file list is empty or irrelevant, state that clearly and answer based on the conversation or general knowledge if appropriate. "
        "You cannot access file contents. Explicitly state that you can only see file names and types based on the search, not the content inside."
    )

    full_messages = [{"role": "system", "content": system_prompt}]
    full_messages.extend([msg for msg in memory if msg.get("role") != "system"])

    # Add file context *before* the user's question
    if file_context_str:
        full_messages.append({"role": "system", "content": f"File Context: {file_context_str}"})

    # Add the *original* user question
    full_messages.append({"role": "user", "content": original_question})

    # --- Memory Trimming (Keep as before) ---
    MAX_MEMORY_MESSAGES = 10 # Keep last 5 turns (10 user/assistant messages)
    non_system_messages = [m for m in full_messages if m['role'] != 'system']
    if len(non_system_messages) > MAX_MEMORY_MESSAGES:
        num_to_keep = MAX_MEMORY_MESSAGES
        system_prompts = [m for m in full_messages if m['role'] == 'system']
        latest_exchanges = non_system_messages[-num_to_keep:]
        full_messages = system_prompts + latest_exchanges
        logger.info(f"Trimmed message history to {len(full_messages)} total messages ({len(latest_exchanges)} non-system).")


    # --- Step 4: Call Groq API for the Final Answer ---
    try:
        logger.debug(f"Sending final messages to Groq: {full_messages}")
        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile", # Model for the main answer
            messages=full_messages,
            temperature=0.7,
        )

        response_text = completion.choices[0].message.content.strip()
        logger.info(f"Groq final answer received for user {username}.")
        logger.debug(f"Groq response text: {response_text}")

        # --- Step 5: Update Memory ---
        current_memory = session_memory[telegram_user_id]
        current_memory.append({"role": "user", "content": original_question}) # Original question
        current_memory.append({"role": "assistant", "content": response_text})
        session_memory[telegram_user_id] = current_memory[-MAX_MEMORY_MESSAGES:]

        return {"response": response_text}

    except Exception as e:
        logger.error(f"Groq API call failed for final answer: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"LLM request failed during final answer generation: {e}")


@app.post("/llm/reset", tags=["LLM"])
async def reset_llm_memory(request_data: ResetRequest): # Use Pydantic model
    """Resets the conversation memory for a given user ID."""
    telegram_user_id = request_data.user_id
    logger.info(f"Resetting memory for Telegram User ID: {telegram_user_id}")
    # Use pop with default to avoid KeyError if user_id not in memory
    session_memory.pop(telegram_user_id, None)
    return {"message": f"Memory reset for user {telegram_user_id}"}


# --- Main Application Runner ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000)) # Use PORT env var or default 8000
    host = os.getenv("HOST", "0.0.0.0") # Use HOST env var or default 0.0.0.0
    logger.info(f"Starting Syncly API server on {host}:{port}")
    # Reverted this line to use the app object directly
    uvicorn.run(app, host=host, port=port)

# --- END OF FILE api.py ---