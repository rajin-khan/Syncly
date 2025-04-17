# --- START OF FILE api.py ---

import asyncio
import base64
import hashlib
import io # <--- Import io
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Query, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from AuthManager import AuthManager
from DriveManager import DriveManager
from fastapi.staticfiles import StaticFiles
import shutil
from bson import ObjectId
import dropbox
import logging
import mimetypes
from typing import List, Optional, Dict, Tuple
from fastapi.responses import FileResponse, RedirectResponse
from Database import Database
from GoogleDrive import GoogleDrive
from Dropbox import DropboxService
from GDriveFile import GoogleDriveFile, SUPPORTED_TEXT_EXTENSIONS
from DropBoxFile import DropBoxFile
from groq import Groq
from dotenv import load_dotenv
from collections import defaultdict
import re

# --- Import for simple Keyword Extraction (Fallback) ---
import string
from stop_words import get_stop_words
# --- End Import ---


load_dotenv()

# Load Groq API key from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("\n" + "="*40)
    print("  WARNING: GROQ_API_KEY not found in .env")
    print("  LLM features will be disabled.")
    print("  Get a key from https://console.groq.com/keys")
    print("  And add it to your .env file.")
    print("="*40 + "\n")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("syncly-api")


app = FastAPI(title="Syncly API")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-please-change")
if SECRET_KEY == "your-secret-key-please-change":
     logger.warning("Security warning: SECRET_KEY is set to the default value.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 240))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Pydantic Models ---
class UserCreate(BaseModel): username: str; password: str; email: str
class UserResponse(BaseModel): username: str; email: str
class Token(BaseModel): access_token: str; token_type: str
class TokenData(BaseModel): username: str | None = None
class StorageInfo(BaseModel): provider: str; drive_number: int; storage_limit_gb: float; used_storage_gb: float; free_storage_gb: float
class StorageSummary(BaseModel): storages: List[StorageInfo]; total_storage_gb: float; used_storage_gb: float; free_storage_gb: float
class FileInfo(BaseModel):
    id: Optional[str] = None
    name: str
    provider: str
    size: Optional[int] = None # Make size numeric or None
    path: str
    mimeType: Optional[str] = None # Add mimeType
    bucket: Optional[int] = None # Add bucket
    path_lower: Optional[str] = None # Add path_lower for Dropbox
    access_token: Optional[str] = None # Keep token separate from model if sensitive? No, needed here.

class AddDriveRequest(BaseModel): drive_type: str
class AskRequest(BaseModel): question: str; user_id: str
class ResetRequest(BaseModel): user_id: str


# Global session memory
session_memory = defaultdict(list)

# --- Helper functions ---
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

# --- Authentication Middleware ---
async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None: raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError as e: raise credentials_exception from e
    db = Database().get_instance()
    if not db or not db.client:
        logger.error("Database connection failed. Cannot get current user.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database connection error")
    user = db.users_collection.find_one({"username": token_data.username})
    if user is None: raise credentials_exception
    # Add user_id as string for easier use later if needed, MongoDB returns ObjectId
    user["user_id_str"] = str(user["_id"])
    return user

# --- Keyword Extraction Helpers ---
def extract_keywords_simple(text: str, min_len: int = 3) -> str:
    if not text: return ""
    try:
        text = text.lower().translate(str.maketrans('', '', string.punctuation))
        stop_words_list = get_stop_words('en')
        keywords = [word for word in text.split() if word not in stop_words_list and len(word) >= min_len]
        keyword_string = " ".join(keywords)
        logger.debug(f"Simple extracted keywords: '{keyword_string}' from text: '{text[:50]}...'")
        return keyword_string
    except Exception as e: logger.error(f"Error during simple keyword extraction: {e}", exc_info=True); return ""

async def get_search_keywords_from_llm(question: str) -> str:
    """
    Uses a preliminary LLM call to extract search keywords from the user's question.
    Focuses ONLY on the current question, ignoring history.
    """
    if not question: return ""
    if not GROQ_API_KEY:
        logger.warning("Groq API key not available, using simple keyword extraction.")
        return extract_keywords_simple(question)

    keyword_model = "llama-3.1-8b-instant"

    # --- REFINED SYSTEM PROMPT ---
    system_prompt = (
        "Analyze the User Question below to identify the 1-5 core nouns, topics, or file identifiers "
        "that would be most useful for searching a file system (Google Drive, Dropbox) to find relevant documents. "
        "Focus ONLY on the current question. Ignore any conversational context or previous turns. "
        "Consider filenames, document types (e.g., 'schedule', 'meeting notes', 'report'), specific entities, dates, or project names mentioned. "
        "Output *only* the keywords, separated by a single space. Use lowercase. Do not use punctuation. Do not add any explanation or introductory text.\n"
        "Example 1: User Question: 'Do any of the parents teacher days or my separate meetings clash?' Output: 'parents teacher day meetings schedule clash dates'\n"
        "Example 2: User Question: 'search for the lora paper pdf' Output: 'lora paper pdf'\n"
        "Example 3: User Question: 'what files mention the Project Alpha deadline?' Output: 'project alpha deadline file'\n"
        "Example 4: User Question: 'summarize chapter 3 of my economics notes' Output: 'economics notes chapter 3'"
    )
    # --- END REFINED SYSTEM PROMPT ---

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"User Question: '{question}'"} # Clearly label input
    ]

    try:
        logger.info(f"Getting search keywords from LLM ({keyword_model}) for question: '{question[:50]}...'")
        client = Groq(api_key=GROQ_API_KEY)
        completion = await asyncio.to_thread( # Run blocking Groq call in thread
            client.chat.completions.create,
            model=keyword_model,
            messages=messages,
            temperature=0.1,
            max_tokens=60, # Slightly increased max tokens for potentially more keywords
        )
        raw_keywords = completion.choices[0].message.content.strip()
        logger.info(f"Raw LLM keyword response: '{raw_keywords}'")

        # --- Parsing (Keep as is) ---
        keywords = raw_keywords.lower()
        prefixes_to_remove = ["keywords:", "output:", "keywords ", "output "]
        for prefix in prefixes_to_remove:
            if keywords.startswith(prefix): keywords = keywords[len(prefix):].strip()
        keywords = keywords.translate(str.maketrans('', '', string.punctuation))
        keywords = re.sub(r'\s+', ' ', keywords).strip()
        # --- End Parsing ---

        if not keywords:
             logger.warning("LLM keyword extraction returned an empty string after parsing. Falling back.")
             return extract_keywords_simple(question)

        logger.info(f"Cleaned LLM extracted keywords: '{keywords}'")
        return keywords
    except Exception as e:
        logger.error(f"Groq API call failed during keyword extraction: {e}", exc_info=True)
        logger.warning("Falling back to simple keyword extraction due to API error.")
        return extract_keywords_simple(question)


# --- API Endpoints ---

# --- Auth Endpoints ---
@app.post("/register", status_code=status.HTTP_201_CREATED, tags=["Auth"])
async def register(user_data: UserCreate): # Use UserCreate model
    db = Database().get_instance()
    if not db or not db.client: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database connection error")
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
    db = Database().get_instance();
    if not db or not db.client: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database connection error")
    user = db.users_collection.find_one({"username": form_data.username})
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
        if not db or not db.client: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database connection error")
        if not db.users_collection.find_one({"username": username}): raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: User not found")
        return {"username": username}
    except JWTError as e: logger.error(f"JWT decoding failed during validation: {str(e)}"); raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    except HTTPException as e: raise e
    except Exception as e: logger.error(f"Unexpected error during token validation: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Token validation error")

# --- User Endpoints ---
@app.get("/users/me", response_model=UserResponse, tags=["Users"])
async def read_users_me(current_user: Dict = Depends(get_current_user)):
    # current_user already contains the user document from the DB via get_current_user
    return UserResponse(username=current_user["username"], email=current_user["email"])

# --- Storage Endpoints ---
@app.get("/storage", response_model=StorageSummary, tags=["Storage"])
async def get_storage_info(current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id)
    if not drive_manager.drives: return StorageSummary(storages=[], total_storage_gb=0, used_storage_gb=0, free_storage_gb=0)
    storages_info, total_limit, total_usage = drive_manager.check_all_storages()
    # Convert bytes to GB for the response model
    storage_details = []
    for s in storages_info:
         limit_gb = s.get("Storage Limit (bytes)", 0) / (1024**3) if s.get("Storage Limit (bytes)") else 0
         used_gb = s.get("Used Storage (bytes)", 0) / (1024**3) if s.get("Used Storage (bytes)") else 0
         free_gb = s.get("Free Storage", 0) / (1024**3) if s.get("Free Storage") else 0
         storage_details.append(StorageInfo(
             provider=s["Provider"], drive_number=s["Drive Number"],
             storage_limit_gb=limit_gb, used_storage_gb=used_gb, free_storage_gb=free_gb
         ))
    total_storage_gb = round(total_limit / (1024**3), 2) if total_limit else 0
    used_storage_gb = round(total_usage / (1024**3), 2) if total_usage else 0
    free_storage_gb = round((total_limit - total_usage) / (1024**3), 2) if (total_limit - total_usage) > 0 else 0
    return StorageSummary(storages=storage_details, total_storage_gb=total_storage_gb, used_storage_gb=used_storage_gb, free_storage_gb=free_storage_gb)

@app.post("/drives", tags=["Storage"])
async def add_drive(request: AddDriveRequest, current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); db = Database().get_instance()
    if not db or not db.client: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database connection error")
    # Use user_id (ObjectId) consistently
    existing_drives_count = db.drives_collection.count_documents({"user_id": user_id})
    bucket_number = existing_drives_count + 1
    logger.info(f"Attempting to add drive type '{request.drive_type}' as bucket #{bucket_number} for user {current_user['username']}")
    response_data = {"status": "failed", "message": "Unknown drive type"}
    try:
        if request.drive_type == "GoogleDrive":
            google_drive_instance = GoogleDrive()
            drive_manager.add_drive(google_drive_instance, bucket_number, drive_type="GoogleDrive") # add_drive handles auth
            response_data = {"status": "success", "message": f"Google Drive added as bucket {bucket_number}. Follow browser prompts if needed."}
        elif request.drive_type == "Dropbox":
            # Use environment variables for keys, default only for example
            dropbox_app_key=os.getenv("DROPBOX_APP_KEY", "YOUR_DROPBOX_APP_KEY") # Replace default
            dropbox_app_secret=os.getenv("DROPBOX_APP_SECRET", "YOUR_DROPBOX_APP_SECRET") # Replace default
            if not dropbox_app_key or dropbox_app_key == "YOUR_DROPBOX_APP_KEY":
                 raise HTTPException(status_code=500, detail="Dropbox app key not configured.")
            if not dropbox_app_secret or dropbox_app_secret == "YOUR_DROPBOX_APP_SECRET":
                  raise HTTPException(status_code=500, detail="Dropbox app secret not configured.")
            dropbox_service_instance = DropboxService(app_key=dropbox_app_key, app_secret=dropbox_app_secret)
            drive_manager.add_drive(dropbox_service_instance, bucket_number, drive_type="Dropbox")
            response_data = {"status": "success", "message": f"Dropbox added as bucket {bucket_number}. Follow browser prompts."}
        else: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid drive type. Choose 'GoogleDrive' or 'Dropbox'")
        return response_data
    except HTTPException as e: raise e
    except Exception as e: logger.error(f"Failed to add drive for user {current_user['username']}: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to add {request.drive_type}. Error: {e}")


# --- CORRECTED /viewfiles Endpoint ---
@app.get("/viewfiles", response_model=List[FileInfo], tags=["Files"])
async def list_files(
    query: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200), # User/Bot requested limit
    offset: int = Query(0, ge=0),
    current_user: Dict = Depends(get_current_user)
):
    user_id = current_user["_id"]
    drive_manager = DriveManager(user_id=user_id)
    username = current_user['username']
    if not drive_manager.drives:
        return []

    all_files_data = [] # Store raw dicts from all drives first
    logger.info(f"Listing files for {username} (q='{query}', limit={limit}, offset={offset})")

    for drive in drive_manager.drives:
        try:
            provider = type(drive).__name__
            # --- FIX: Call listFiles WITHOUT max_results from the API request ---
            # Let the underlying listFiles methods use their own internal limits/paging
            logger.debug(f"Calling {provider}.listFiles with query='{query}' (using internal limits)")
            files_data = drive.listFiles(query=query) # REMOVED max_results=limit
            # --- END FIX ---

            # Add provider info if missing and bucket number
            for file_d in files_data:
                 if "provider" not in file_d: file_d["provider"] = provider
                 if "bucket" not in file_d and hasattr(drive, "bucket_number"):
                     file_d["bucket"] = drive.bucket_number
            all_files_data.extend(files_data)
            logger.info(f"Collected {len(files_data)} files from {provider}")

        except Exception as e:
            logger.error(f"Error listing from {type(drive).__name__} for {username}: {e}", exc_info=True)

    # --- De-duplicate and Sort AFTER collecting from all drives ---
    logger.info(f"Collected {len(all_files_data)} total files before de-duplication.")
    unique_files_dict = {}
    for file_data in all_files_data:
        # Use provider and name as key for simple listing de-duplication
        key = (file_data.get("provider", "?"), file_data.get("name", "Unknown"))
        if key not in unique_files_dict:
             unique_files_dict[key] = file_data

    sorted_unique_files_data = sorted(unique_files_dict.values(), key=lambda x: x.get("name", "").lower())
    total_unique_files = len(sorted_unique_files_data)
    logger.info(f"Found {total_unique_files} unique files.")

    # --- Apply pagination to the final sorted, unique list ---
    paginated_files_data = sorted_unique_files_data[offset : offset + limit]

    # Convert final paginated list to FileInfo model
    results = []
    for file_data in paginated_files_data:
        try:
            # Convert size to int/None before model validation
            size_val = file_data.get("size")
            size_int = int(size_val) if size_val is not None and str(size_val).isdigit() else None
            file_data["size"] = size_int # Update dict before unpacking
            results.append(FileInfo(**file_data))
        except Exception as model_err:
            logger.warning(f"Skipping file model creation error: {model_err}. Data: {file_data}")

    logger.info(f"Returning {len(results)} files (offset={offset}, limit={limit}) out of {total_unique_files} unique files found for {username}")
    return results
# --- END CORRECTED /viewfiles ---

@app.get("/search_files", response_model=List[FileInfo], tags=["Files"])
async def search_files_endpoint( query: str = Query(...), limit: int = Query(10, ge=1, le=50), current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); username = current_user['username']
    if not drive_manager.drives: return []
    logger.info(f"User {username} (ID: {str(user_id)}) searching for '{query}' with limit {limit}")
    try:
        # search_files_for_llm calls searchFiles which now returns needed fields
        matching_files_data = drive_manager.search_files_for_llm(query=query, limit_per_drive=limit, total_limit=limit)
        # Convert raw dicts to FileInfo Pydantic model
        results = []
        for file_data in matching_files_data:
             size_val = file_data.get("size")
             size_int = int(size_val) if size_val is not None and str(size_val).isdigit() else None
             results.append(FileInfo(
                 id=file_data.get("id"), name=file_data.get("name", "Unknown"),
                 provider=file_data.get("provider", "Unknown"), size=size_int,
                 path=file_data.get("path", "N/A"), mimeType=file_data.get("mimeType"),
                 bucket=file_data.get("bucket"), path_lower=file_data.get("path_lower"),
                 access_token=file_data.get("access_token") # Pass token if needed by client? Maybe not.
             ))
        logger.info(f"Returning {len(results)} matching files for query '{query}' for user {username}")
        return results
    except Exception as e: logger.error(f"Error searching files for user {username}: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error searching files.")

@app.post("/files/upload", tags=["Files"])
async def upload_file_endpoint( file: UploadFile = File(...), current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; username = current_user["username"]; upload_dir = "uploads"; os.makedirs(upload_dir, exist_ok=True)
    safe_filename = os.path.basename(file.filename or "uploaded_file"); temp_file_location = os.path.join(upload_dir, f"{user_id}_{safe_filename}") # User-specific temp file
    try:
        with open(temp_file_location, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
        logger.info(f"Temporary file saved at: {temp_file_location} for user {username}")
    except Exception as e: logger.error(f"Failed to save temporary upload file for user {username}: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save uploaded file.")
    finally: file.file.close()

    drive_manager = DriveManager(user_id=user_id);
    if not drive_manager.drives: os.remove(temp_file_location); raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No connected drives found.")

    # Use DriveManager to find the best bucket (already checks storage)
    sorted_buckets_info = drive_manager.get_sorted_buckets() # Returns [(free_space, drive_instance, index), ...]
    if not sorted_buckets_info: os.remove(temp_file_location); raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No available storage space found or drives couldn't be checked.")

    # Select the best drive instance and its bucket number
    best_bucket_tuple = sorted_buckets_info[0]
    best_drive_instance = best_bucket_tuple[1] # The GoogleDrive or DropboxService instance
    drive_index = best_bucket_tuple[2] # Original index from drive_manager.drives
    # We need the actual bucket number stored in the DB (index+1 might be wrong if drives were deleted)
    # Let's rely on the bucket_number attribute we added
    best_bucket_number = getattr(best_drive_instance, 'bucket_number', None)
    if best_bucket_number is None:
         # Fallback? Or error? Error seems safer.
         logger.error(f"Could not determine bucket number for selected best drive instance (Index: {drive_index}, Type: {type(best_drive_instance).__name__})")
         os.remove(temp_file_location)
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error determining upload bucket.")

    provider = type(best_drive_instance).__name__
    logger.info(f"Attempting to upload '{safe_filename}' to {provider} (Bucket {best_bucket_number}) for user {username}")

    try:
        if isinstance(best_drive_instance, GoogleDrive):
            gdrive_file_handler = GoogleDriveFile(drive_manager)
            mime_type = file.content_type or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
            # upload_file should handle selecting the bucket via drive_manager logic now
            gdrive_file_handler.upload_file(temp_file_location, safe_filename, mime_type)
        elif isinstance(best_drive_instance, DropboxService):
             # Get the specific token for this instance
             access_token = None
             if hasattr(best_drive_instance.service, 'session') and hasattr(best_drive_instance.service.session, 'access_token'):
                 access_token = best_drive_instance.service.session.access_token
             elif hasattr(best_drive_instance.service, '_oauth2_access_token'):
                 access_token = best_drive_instance.service._oauth2_access_token

             if not access_token:
                 logger.error(f"Could not retrieve access token from selected Dropbox instance (Bucket {best_bucket_number}).")
                 raise Exception("Failed to get Dropbox access token for upload.")
             dropbox_file_handler = DropBoxFile(access_token, drive_manager);
             # upload_file should handle bucket selection logic
             dropbox_file_handler.upload_file(temp_file_location, safe_filename)
        else: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported drive type selected: {provider}")
        logger.info(f"Successfully uploaded '{safe_filename}' to {provider} (Bucket {best_bucket_number}) for user {username}")
        return {"status": "success", "message": f"File '{safe_filename}' uploaded to {provider} (Bucket {best_bucket_number})"}
    except NotImplementedError as nie: # Catch if splitting is required but not implemented
         logger.error(f"Upload error for {safe_filename}: {nie}")
         raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(nie))
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

    # --- Try Google Drive ---
    try:
        gdrive_file_handler = GoogleDriveFile(drive_manager)
        user_download_path = os.path.join(download_dir, str(user_id)) # User-specific download dir
        # This method handles searching across all GDrive buckets
        downloaded_file_path = gdrive_file_handler.download_from_all_buckets(file_name, user_download_path)
        if downloaded_file_path and os.path.exists(downloaded_file_path):
            mime_type, _ = mimetypes.guess_type(downloaded_file_path); fname=os.path.basename(downloaded_file_path)
            logger.info(f"Returning downloaded file '{fname}' from Google Drive.")
            # Use FileResponse to stream the file
            return FileResponse(path=downloaded_file_path, filename=fname, media_type=mime_type or "application/octet-stream", headers={"Content-Disposition": f"attachment; filename=\"{fname}\""})
    except Exception as e: logger.error(f"Error during Google Drive download check for user {username}, file '{file_name}': {e}", exc_info=True) # Continue to Dropbox

    # --- Try Dropbox ---
    try:
        # Iterate through Dropbox instances in DriveManager
        dropbox_accounts = [d for d in drive_manager.drives if isinstance(d, DropboxService) and d.service]
        for dropbox_service_instance in dropbox_accounts:
             access_token = None
             if hasattr(dropbox_service_instance.service, 'session') and hasattr(dropbox_service_instance.service.session, 'access_token'):
                 access_token = dropbox_service_instance.service.session.access_token
             elif hasattr(dropbox_service_instance.service, '_oauth2_access_token'):
                 access_token = dropbox_service_instance.service._oauth2_access_token

             if not access_token: logger.warning(f"Skipping Dropbox search (Bucket {dropbox_service_instance.bucket_number}): No access token found."); continue

             dropbox_file_handler = DropBoxFile(access_token, drive_manager)
             # search_file returns the Dropbox path_lower if found
             dropbox_api_path = dropbox_file_handler.search_file(file_name)
             if dropbox_api_path:
                 user_download_path = os.path.join(download_dir, str(user_id)); os.makedirs(user_download_path, exist_ok=True);
                 local_save_path = os.path.join(user_download_path, os.path.basename(dropbox_api_path)) # Use name from path
                 # download_file downloads to local disk
                 downloaded_path = dropbox_file_handler.download_file(dropbox_api_path, local_save_path)
                 if downloaded_path and os.path.exists(downloaded_path):
                     mime_type, _ = mimetypes.guess_type(downloaded_path); fname=os.path.basename(downloaded_path)
                     logger.info(f"Returning downloaded file '{fname}' from Dropbox.")
                     return FileResponse(path=downloaded_path, filename=fname, media_type=mime_type or "application/octet-stream", headers={"Content-Disposition": f"attachment; filename=\"{fname}\""})
                 else: logger.error(f"Dropbox download attempt failed or file missing locally at {local_save_path}")
                 # Stop checking other Dropbox accounts if found but failed to download
                 break
    except Exception as e: logger.error(f"Error during Dropbox download check for user {username}, file '{file_name}': {e}", exc_info=True)

    logger.warning(f"File '{file_name}' not found or download failed across all providers for user {username}.")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File '{file_name}' not found or could not be downloaded.")


# --- LLM Endpoints ---

# Helper function to get authenticated service instance from DriveManager
def _get_drive_service_instance(drive_manager: DriveManager, provider: str, bucket: int) -> Optional[object]:
    """Finds the specific authenticated service instance in DriveManager."""
    target_class = GoogleDrive if provider == "GoogleDrive" else DropboxService if provider == "Dropbox" else None
    if not target_class: logger.warning(f"Unsupported provider '{provider}' requested."); return None
    for drive in drive_manager.drives:
        if isinstance(drive, target_class) and hasattr(drive, 'bucket_number') and drive.bucket_number == bucket:
            return drive.service if hasattr(drive, 'service') else None
    logger.warning(f"No authenticated instance found for {provider} Bucket {bucket} in DriveManager.")
    return None

@app.post("/llm/ask", tags=["LLM"])
async def llm_ask_endpoint( request_data: AskRequest, current_user: Dict = Depends(get_current_user)):
    """Handles LLM queries, incorporating conversation memory and extracted file content snippets."""
    original_question = request_data.question
    telegram_user_id = request_data.user_id
    user_id = current_user["_id"]
    username = current_user["username"]

    if not GROQ_API_KEY: raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM service is not configured (API key missing).")
    logger.info(f"User {username} (TG ID: {telegram_user_id}) asking LLM: '{original_question}'")

    # --- Step 1: Get Search Keywords ---
    search_query = await get_search_keywords_from_llm(original_question)
    file_metadata_context = ""; extracted_snippets_context = ""; relevant_files = []
    if not search_query:
        logger.info("LLM did not provide keywords, or failed. Skipping file search.")
        file_metadata_context = "\n(Note: Could not determine relevant keywords from the question to search files.)"
    else:
        logger.info(f"Using LLM-extracted keywords for file search: '{search_query}'")
        # --- Step 2: Search Files ---
        try:
            drive_manager = DriveManager(user_id=user_id)
            raw_files_data = drive_manager.search_files_for_llm(query=search_query, limit_per_drive=5, total_limit=10)
            if raw_files_data:
                file_lines = ["Based on your question, I found these potentially relevant files:"]
                for file_data in raw_files_data:
                     size_val = file_data.get("size"); size_int = int(size_val) if size_val is not None and str(size_val).isdigit() else None
                     file_info = FileInfo( # Map to FileInfo model
                         id=file_data.get("id"), name=file_data.get("name", "Unknown"), provider=file_data.get("provider", "Unknown"),
                         size=size_int, path=file_data.get("path", "N/A"), mimeType=file_data.get("mimeType"),
                         bucket=file_data.get("bucket"), path_lower=file_data.get("path_lower"), access_token=file_data.get("access_token")
                     )
                     relevant_files.append(file_info)
                     file_lines.append(f"- {file_info.name} ({file_info.provider})")
                file_metadata_context = "\n".join(file_lines)
                logger.info(f"Generated file metadata context:\n{file_metadata_context}")
            else:
                logger.info("No relevant files found for extracted keywords.")
                file_metadata_context = "\n(Note: No specific files matching the likely keywords were found in your drives.)"

            # --- Step 3: Extract Text Snippets ---
            if relevant_files:
                files_to_extract_from = []; MAX_FILES_TO_EXTRACT = 5; count = 0
                for file in relevant_files:
                    if count >= MAX_FILES_TO_EXTRACT: break
                    file_ext = os.path.splitext(file.name)[1].lower()
                    if file_ext in SUPPORTED_TEXT_EXTENSIONS: files_to_extract_from.append(file); count += 1

                if files_to_extract_from:
                    logger.info(f"Attempting text extraction from {len(files_to_extract_from)} files: {[f.name for f in files_to_extract_from]}")
                    snippet_lines = ["\n\nExtracted Content Snippets:"]; MAX_SNIPPET_LENGTH = 2500; total_snippet_length = 0; MAX_TOTAL_SNIPPETS_LENGTH = 8000
                    gdrive_file_handler = GoogleDriveFile(drive_manager) # Instantiate once

                    for file in files_to_extract_from:
                        if total_snippet_length >= MAX_TOTAL_SNIPPETS_LENGTH:
                             logger.warning("Reached max total snippet length. Skipping further extraction."); snippet_lines.append("\n(Note: Further snippets omitted due to length limits.)"); break
                        extracted_text = None; content_buffer = None
                        try:
                            if file.provider == "GoogleDrive" and file.id and file.bucket:
                                gdrive_service = _get_drive_service_instance(drive_manager, "GoogleDrive", file.bucket)
                                if gdrive_service:
                                    content_buffer = gdrive_file_handler.download_file_content_by_id(gdrive_service, file.id, file.size)
                                    if content_buffer: extracted_text = gdrive_file_handler.extract_text_from_content(content_buffer, file.name, file.mimeType)
                                else: logger.error(f"Could not get GDrive service for bucket {file.bucket} to download {file.name}")
                            elif file.provider == "Dropbox" and file.path_lower and file.access_token:
                                 dropbox_file_handler = DropBoxFile(file.access_token, drive_manager) # Instantiate with specific token
                                 content_buffer = dropbox_file_handler.download_file_content_by_path(file.path_lower)
                                 if content_buffer: extracted_text = dropbox_file_handler.extract_text_from_content(content_buffer, file.name)
                            else: logger.warning(f"Cannot extract from {file.name}: Missing required info")
                        except Exception as extraction_err: logger.error(f"Error during download/extraction for {file.name}: {extraction_err}", exc_info=True)
                        finally:
                             if content_buffer:
                                 try: content_buffer.close()
                                 except Exception: pass
                        if extracted_text:
                            snippet = extracted_text[:MAX_SNIPPET_LENGTH]
                            if len(extracted_text) > MAX_SNIPPET_LENGTH: snippet += "..."
                            snippet_lines.append(f"\n--- Start Snippet from {file.name} ---"); snippet_lines.append(snippet); snippet_lines.append(f"--- End Snippet from {file.name} ---")
                            total_snippet_length += len(snippet)
                        else: snippet_lines.append(f"\n(Could not extract text content from {file.name})")
                    if len(snippet_lines) > 1:
                        extracted_snippets_context = "\n".join(snippet_lines); logger.info("Generated snippets context."); logger.debug(f"Snippets Context Preview:\n{extracted_snippets_context[:500]}...")
        except Exception as e:
            logger.error(f"Error during file search or text extraction for user {username}: {e}", exc_info=True)
            file_metadata_context = "\n(Note: Could not retrieve file context due to an error.)"; extracted_snippets_context = ""

    # --- Step 4: Prepare messages for Final Groq Answer ---
    memory = session_memory.get(telegram_user_id, [])
    system_prompt = ( # Refined system prompt
        "You are Syncly AI, a helpful assistant integrated into the Syncly file management application. "
        "Answer the user's questions concisely based *primarily* on the provided conversation history and the relevant file context."
        "The File Context includes:\n"
        "1. A list of potentially relevant files found by searching the user's cloud drives based on keywords from the latest question.\n"
        "2. Extracted text snippets from the beginning of some of those text-based files (like PDF, DOCX, TXT).\n"
        "Prioritize information from the extracted snippets if they are relevant to the question. "
        "If the snippets don't answer the question, use the file list and conversation history. "
        "If no relevant context is found (empty file list or snippets), state that clearly and answer based on general knowledge if appropriate. "
        "Speak as if you either know or don't know the information directly. Do not mention that you found information from the extracted snippets, just state the information you find."
        "Do NOT claim to have 'read' the entire file; you only see the provided snippets. Be factual about your limitations, but make no mention of extracted snippets, although you are allowed to retrieve extra information from it if needed for a query."
    )
    full_messages = [{"role": "system", "content": system_prompt}]
    full_messages.extend([msg for msg in memory if msg.get("role") != "system"])
    combined_file_context = file_metadata_context + extracted_snippets_context
    if combined_file_context.strip(): full_messages.append({"role": "system", "content": f"File Context: {combined_file_context}"})
    full_messages.append({"role": "user", "content": original_question})

    # --- Memory Trimming ---
    MAX_MEMORY_MESSAGES = 10
    non_system_messages = [m for m in full_messages if m['role'] != 'system']
    if len(non_system_messages) > MAX_MEMORY_MESSAGES:
        num_to_keep = MAX_MEMORY_MESSAGES; system_prompts = [m for m in full_messages if m['role'] == 'system']
        latest_exchanges = non_system_messages[-num_to_keep:]; full_messages = system_prompts + latest_exchanges
        logger.info(f"Trimmed message history to {len(full_messages)} total messages ({len(latest_exchanges)} non-system).")

    # --- Step 5: Call Groq API ---
    try:
        logger.debug(f"Sending final messages to Groq (Context Snippet Preview: {extracted_snippets_context[:100]}...)")
        client = Groq(api_key=GROQ_API_KEY)
        completion = await asyncio.to_thread( # Run blocking call in thread
            client.chat.completions.create, model="llama-3.3-70b-versatile", messages=full_messages, temperature=0.7,
        )
        response_text = completion.choices[0].message.content.strip()
        logger.info(f"Groq final answer received for user {username}.")
        logger.debug(f"Groq response text (first 100 chars): {response_text[:100]}")

        # --- Step 6: Update Memory ---
        current_memory = session_memory[telegram_user_id]
        current_memory.append({"role": "user", "content": original_question})
        current_memory.append({"role": "assistant", "content": response_text})
        session_memory[telegram_user_id] = current_memory[-MAX_MEMORY_MESSAGES:]

        return {"response": response_text}
    except Exception as e:
        logger.error(f"Groq API call failed for final answer: {e}", exc_info=True)
        error_detail = f"LLM request failed: {e}"
        if hasattr(e, 'response') and hasattr(e.response, 'text'): error_detail += f" | API Response: {e.response.text}"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error_detail)

@app.post("/llm/reset", tags=["LLM"])
async def reset_llm_memory(request_data: ResetRequest):
    """Resets the conversation memory for a given Telegram user ID."""
    telegram_user_id = request_data.user_id
    if not telegram_user_id: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing user_id")
    logger.info(f"Resetting memory for Telegram User ID: {telegram_user_id}")
    session_memory.pop(telegram_user_id, None)
    return {"message": f"Memory reset for user {telegram_user_id}"}


# --- Main Application Runner ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000)) # Use PORT env var or default 8000
    host = os.getenv("HOST", "0.0.0.0") # Use HOST env var or default 0.0.0.0
    logger.info(f"Starting Syncly API server on {host}:{port}")
    # --- Use the app object directly as requested ---
    uvicorn.run(app, host=host, port=port)
    # Note: This disables Uvicorn's built-in --reload feature.
    # For development with reload, run: uvicorn api:app --reload --port 8000

# --- END OF FILE api.py ---