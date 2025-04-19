# --- START OF FILE api.py ---

import asyncio
import base64
import hashlib
import io
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Query, Body
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import uuid
from pymongo import IndexModel, ASCENDING
from AuthManager import AuthManager
from DriveManager import DriveManager
from fastapi.staticfiles import StaticFiles
import shutil
from bson import ObjectId
import dropbox
import logging
import mimetypes
from typing import List, Optional, Dict, Tuple, Union
from fastapi.responses import FileResponse, RedirectResponse
from Database import Database # Use the updated Database class
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

# --- Environment Variable Checks ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
API_BASE_URL = os.getenv("API_BASE_URL")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("syncly-api")

# Critical Variable Checks
if not GROQ_API_KEY: logger.warning("GROQ_API_KEY not found in .env. LLM features disabled.")
if not SECRET_KEY or SECRET_KEY == "your-secret-key-please-change": logger.critical("FATAL: SECRET_KEY missing/default"); exit("SECRET_KEY not configured.")
if not API_BASE_URL: logger.critical("FATAL: API_BASE_URL missing"); exit("API_BASE_URL not configured.")


app = FastAPI(title="Syncly API")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Security settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 240))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Constants ---
LINK_EXPIRY_MINUTES = 5

# --- Pydantic Models ---
class UserCreate(BaseModel): username: str; password: str; email: str
class UserResponse(BaseModel): username: str; email: str
class Token(BaseModel): access_token: str; token_type: str = "bearer"
class TokenData(BaseModel): username: str | None = None
class StorageInfo(BaseModel): provider: str; drive_number: int; storage_limit_gb: float; used_storage_gb: float; free_storage_gb: float
class StorageSummary(BaseModel): storages: List[StorageInfo]; total_storage_gb: float; used_storage_gb: float; free_storage_gb: float
class FileInfo(BaseModel):
    id: Optional[str] = None; name: str; provider: str; size: Optional[int] = None; path: str
    mimeType: Optional[str] = None; bucket: Optional[int] = None; path_lower: Optional[str] = None
    access_token: Optional[str] = Field(None, exclude=True)
class AddDriveRequest(BaseModel): drive_type: str
class AskRequest(BaseModel): question: str; user_id: str
class ResetRequest(BaseModel): user_id: str
class TokenRequestForm(BaseModel): username: str; password: str; link_id: Optional[str] = None
class CreateLinkRequest(BaseModel): telegram_id: str
class CreateLinkResponse(BaseModel): link_id: str; login_url: str
class CompleteLinkRequest(BaseModel): link_id: str; telegram_id: str
class CompleteLinkResponse(BaseModel): access_token: str; token_type: str = "bearer"; username: str

# Global session memory for LLM
session_memory = defaultdict(list)

# --- Database Initialization and Index Setup ---
@app.on_event("startup")
async def startup_event():
    logger.info("Running startup database index setup...")
    db_instance = Database().get_instance()
    if not db_instance or not db_instance.client: logger.error("FATAL: DB connection failed on startup."); return
    try:
        db = db_instance.db
        # Setup pending_links Collection
        logger.info("Checking/Setting up 'pending_links' indexes...")
        pending_links_collection = db_instance.pending_links_collection
        if pending_links_collection is None: raise Exception("'pending_links' collection not initialized.")
        idx_pending = pending_links_collection.index_information()
        ttl_name = "expires_at_ttl"; link_id_name = "link_id_1"
        if ttl_name not in idx_pending: logger.info(f"Creating {ttl_name} index..."); pending_links_collection.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0, name=ttl_name); logger.info("Index created.")
        else: logger.info(f"Index {ttl_name} exists.")
        if link_id_name not in idx_pending: logger.info(f"Creating {link_id_name} index..."); pending_links_collection.create_index([("link_id", ASCENDING)], unique=True, name=link_id_name); logger.info("Index created.")
        else: logger.info(f"Index {link_id_name} exists.")
        # Setup users Collection
        logger.info("Checking/Setting up 'users' indexes...")
        users_collection = db_instance.users_collection
        if users_collection is None: raise Exception("'users' collection not initialized.")
        idx_users = users_collection.index_information()
        tg_id_name = "telegram_id_1"
        if tg_id_name not in idx_users: logger.info(f"Creating {tg_id_name} index..."); users_collection.create_index([("telegram_id", ASCENDING)], sparse=True, name=tg_id_name); logger.info("Index created.")
        else: logger.info(f"Index {tg_id_name} exists.")
        logger.info("DB index setup check complete.")
    except Exception as e: logger.error(f"DB index setup error: {e}", exc_info=True)

# --- Helper functions ---
def get_password_hash(password: str) -> str: sha256_hash = hashlib.sha256(password.encode('utf-8')).digest(); return base64.b64encode(sha256_hash).decode('utf-8')
def verify_password(plain_password: str, hashed_password: str) -> bool: input_hash = get_password_hash(plain_password); return input_hash == hashed_password
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None): to_encode = data.copy(); expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)); to_encode.update({"exp": expire}); return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Authentication Middleware ---
async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try: payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]); username: str | None = payload.get("sub");
    except JWTError as e: logger.warning(f"JWT validation failed: {e}"); raise credentials_exception from e
    if username is None: raise credentials_exception
    db = Database().get_instance()
    if not db or db.users_collection is None: logger.error("DB unavailable for get_current_user."); raise HTTPException(status_code=503, detail="Database error")
    user = db.users_collection.find_one({"username": username})
    if user is None: logger.warning(f"User '{username}' not found during JWT validation."); raise credentials_exception
    user["user_id_str"] = str(user["_id"]); return user

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
async def register(user_data: UserCreate): # (Keep as is)
    db = Database().get_instance()
    if not db or db.users_collection is None: raise HTTPException(status_code=503, detail="Database error")
    if db.users_collection.find_one({"username": {"$regex": f"^{user_data.username}$", "$options": "i"}}): raise HTTPException(status_code=400, detail="Username exists")
    if db.users_collection.find_one({"email": {"$regex": f"^{user_data.email}$", "$options": "i"}}): raise HTTPException(status_code=400, detail="Email exists")
    hashed_password = get_password_hash(user_data.password); user_doc = {"username": user_data.username, "password": hashed_password, "email": user_data.email, "drives": [], "created_at": datetime.utcnow()}
    result = db.users_collection.insert_one(user_doc); logger.info(f"User '{user_data.username}' registered ID: {result.inserted_id}"); return {"message": "User registered"}

# --- MODIFIED /token Endpoint ---
@app.post("/token", response_model=Union[Token, Dict[str, str]], tags=["Auth"])
async def login_for_access_token_or_link(form_data: TokenRequestForm = Body(...)):
    db = Database().get_instance()
    # Corrected DB Check
    if db is None or db.users_collection is None or db.pending_links_collection is None:
        logger.error("Login failed: DB connection or collection missing.")
        raise HTTPException(status_code=503, detail="Database unavailable")
    user = db.users_collection.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user["password"]): logger.warning(f"Login failed for {form_data.username}"); raise HTTPException(status_code=401, detail="Incorrect credentials")
    user_id = user["_id"]; username = user["username"]; link_id = form_data.link_id
    if link_id: # Link Flow
        logger.info(f"Processing login link flow: {link_id}")
        pending_link = db.pending_links_collection.find_one({"link_id": link_id, "expires_at": {"$gt": datetime.utcnow()}})
        if not pending_link: logger.warning(f"Link not found/expired: {link_id}"); raise HTTPException(status_code=404, detail="Link not found or expired.")
        if pending_link.get('validated', False): logger.warning(f"Link already used: {link_id}"); raise HTTPException(status_code=410, detail="Link already used.")
        update_result = db.pending_links_collection.update_one({"link_id": link_id, "validated": False}, {"$set": {"user_id": user_id, "validated": True}})
        if update_result.modified_count == 1: logger.info(f"Link {link_id} validated for user {username}"); return {"message": "Login successful! Return to Telegram."}
        else: logger.error(f"Failed update pending link {link_id}"); raise HTTPException(status_code=409, detail="Failed processing link.")
    else: # Default Flow
        logger.info(f"Standard login successful for {username}"); access_token = create_access_token(data={"sub": username}); return Token(access_token=access_token)

# --- NEW /auth/create_link Endpoint ---
@app.post("/auth/create_link", response_model=CreateLinkResponse, tags=["Auth Helper"])
async def create_auth_link(request: CreateLinkRequest):
    db = Database().get_instance()
    # Corrected DB Check
    if db is None or db.pending_links_collection is None:
        logger.error("Create link failed: DB unavailable."); raise HTTPException(status_code=503, detail="Database unavailable")
    link_id = str(uuid.uuid4()); now = datetime.utcnow(); expires = now + timedelta(minutes=LINK_EXPIRY_MINUTES)
    try:
        db.pending_links_collection.insert_one({"link_id": link_id, "telegram_id": request.telegram_id, "user_id": None, "validated": False, "created_at": now, "expires_at": expires})
        logger.info(f"Created pending link {link_id} for telegram_id {request.telegram_id}")
        login_url = f"{API_BASE_URL.rstrip('/')}/static/login.html?link_id={link_id}"
        return CreateLinkResponse(link_id=link_id, login_url=login_url)
    except Exception as e: logger.error(f"Failed insert pending link: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Failed to create login link.")

# --- NEW /auth/complete_link Endpoint ---
@app.post("/auth/complete_link", response_model=CompleteLinkResponse, tags=["Auth Helper"])
async def complete_auth_link(request: CompleteLinkRequest):
    db = Database().get_instance()
    # Corrected DB Check
    if db is None or db.pending_links_collection is None or db.users_collection is None:
        logger.error("Complete link failed: DB unavailable."); raise HTTPException(status_code=503, detail="Database unavailable")
    logger.info(f"Attempting complete link: {request.link_id}, telegram_id: {request.telegram_id}")
    link_data = db.pending_links_collection.find_one({"link_id": request.link_id, "expires_at": {"$gt": datetime.utcnow()}})
    if not link_data: logger.warning(f"Complete link failed: {request.link_id} not found/expired."); raise HTTPException(status_code=404, detail="Link not found or expired.")
    if link_data.get("telegram_id") != request.telegram_id: logger.error(f"TG ID mismatch: {request.link_id}."); db.pending_links_collection.delete_one({"link_id": request.link_id}); raise HTTPException(status_code=403, detail="Invalid link (User mismatch).")
    if not link_data.get("validated", False) or not link_data.get("user_id"): logger.warning(f"Link not validated via web: {request.link_id}."); raise HTTPException(status_code=400, detail="Link not completed via web yet.")
    user_id = link_data["user_id"]
    user = db.users_collection.find_one({"_id": user_id})
    if not user: logger.error(f"User not found for link: {request.link_id}, user_id: {user_id}."); db.pending_links_collection.delete_one({"link_id": request.link_id}); raise HTTPException(status_code=404, detail="Associated user not found.")
    username = user["username"]
    if user.get("telegram_id") != request.telegram_id:
        db.users_collection.update_one({"_id": user_id}, {"$set": {"telegram_id": request.telegram_id}}); logger.info(f"Stored telegram_id {request.telegram_id} for user {username}")
    access_token = create_access_token(data={"sub": username})
    delete_result = db.pending_links_collection.delete_one({"link_id": request.link_id}); logger.info(f"Completed/deleted link {request.link_id} for user {username} (Deleted: {delete_result.deleted_count})")
    return CompleteLinkResponse(access_token=access_token, username=username)

@app.post("/validate-token", tags=["Auth"])
async def validate_token(token: str = Query(...)): # (Keep as is)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]); username: str | None = payload.get("sub")
        if username is None: raise HTTPException(status_code=401, detail="Invalid token: No username")
        db = Database().get_instance();
        if not db or db.users_collection is None : raise HTTPException(status_code=503, detail="Database unavailable")
        if not db.users_collection.find_one({"username": username}): raise HTTPException(status_code=401, detail="Invalid token: User not found")
        return {"username": username}
    except JWTError as e: logger.error(f"JWT validation failed: {e}"); raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e: logger.error(f"Token validation error: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Token validation error")

# --- User Endpoints ---
@app.get("/users/me", response_model=UserResponse, tags=["Users"])
async def read_users_me(current_user: Dict = Depends(get_current_user)): # (Keep as is)
    return UserResponse(username=current_user["username"], email=current_user["email"])

# --- Storage Endpoints ---
@app.get("/storage", response_model=StorageSummary, tags=["Storage"])
async def get_storage_info(current_user: Dict = Depends(get_current_user)): # (Keep as is)
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id)
    if not drive_manager.drives: return StorageSummary(storages=[], total_storage_gb=0, used_storage_gb=0, free_storage_gb=0)
    storages_info, total_limit, total_usage = drive_manager.check_all_storages()
    storage_details = []
    for s in storages_info:
         limit_gb = s.get("Storage Limit (bytes)", 0) / (1024**3) if s.get("Storage Limit (bytes)") else 0; used_gb = s.get("Used Storage (bytes)", 0) / (1024**3) if s.get("Used Storage (bytes)") else 0; free_gb = s.get("Free Storage", 0) / (1024**3) if s.get("Free Storage") else 0
         storage_details.append(StorageInfo(provider=s["Provider"], drive_number=s["Drive Number"], storage_limit_gb=limit_gb, used_storage_gb=used_gb, free_storage_gb=free_gb))
    total_gb = round(total_limit / (1024**3), 2); used_gb = round(total_usage / (1024**3), 2); free_gb = round((total_limit - total_usage) / (1024**3), 2) if total_limit > total_usage else 0
    return StorageSummary(storages=storage_details, total_storage_gb=total_gb, used_storage_gb=used_gb, free_storage_gb=free_gb)

@app.post("/drives", tags=["Storage"])
async def add_drive(request: AddDriveRequest, current_user: Dict = Depends(get_current_user)): # (Keep as is)
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); db = Database().get_instance()
    if not db or db.drives_collection is None: raise HTTPException(status_code=503, detail="Database unavailable")
    existing_drives_count = db.drives_collection.count_documents({"user_id": user_id}); bucket_number = existing_drives_count + 1
    logger.info(f"Adding {request.drive_type} as bucket {bucket_number} for {current_user['username']}")
    try:
        if request.drive_type == "GoogleDrive": instance = GoogleDrive(); drive_manager.add_drive(instance, bucket_number, "GoogleDrive"); return {"status": "success", "message": f"GDrive {bucket_number} added."}
        elif request.drive_type == "Dropbox": key=os.getenv("DROPBOX_APP_KEY"); secret=os.getenv("DROPBOX_APP_SECRET"); assert key and secret and key != "YOUR_DROPBOX_APP_KEY"; instance = DropboxService(app_key=key, app_secret=secret); drive_manager.add_drive(instance, bucket_number, "Dropbox"); return {"status": "success", "message": f"Dropbox {bucket_number} added."}
        else: raise HTTPException(status_code=400, detail="Invalid drive type.")
    except AssertionError: raise HTTPException(status_code=500, detail="Dropbox keys not configured.")
    except Exception as e: logger.error(f"Failed add drive: {e}", exc_info=True); raise HTTPException(status_code=500, detail=f"Failed add drive: {e}")

# --- File Endpoints ---
@app.get("/viewfiles", response_model=List[FileInfo], tags=["Files"])
async def list_files( query: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), current_user: Dict = Depends(get_current_user)): # (Keep as is)
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); username = current_user['username']
    if not drive_manager.drives: return []
    all_files = []; seen_files = set(); logger.info(f"Listing files for {username} (q={query}, l={limit}, o={offset})")
    for drive in drive_manager.drives:
        try:
            files_data = drive.listFiles(query=query); provider = type(drive).__name__
            for file_data in files_data:
                file_name = file_data.get("name", "Unknown")
                if file_name not in seen_files:
                    try: all_files.append(FileInfo(**file_data))
                    except Exception as model_err: logger.warning(f"Skip file: bad model data {model_err}. Data: {file_data}")
                    seen_files.add(file_name)
        except Exception as e: logger.error(f"Error listing from {provider}: {e}", exc_info=True)
    all_files.sort(key=lambda x: x.name.lower()); paginated_files = all_files[offset : offset + limit]
    logger.info(f"Return {len(paginated_files)}/{len(all_files)} files for {username}"); return paginated_files

@app.get("/search_files", response_model=List[FileInfo], tags=["Files"])
async def search_files_endpoint( query: str = Query(...), limit: int = Query(10, ge=1, le=50), current_user: Dict = Depends(get_current_user)): # (Keep as is)
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); username = current_user['username']
    if not drive_manager.drives: return []
    logger.info(f"{username} searching '{query}' (limit {limit})")
    try:
        matching_files_data = drive_manager.search_files_for_llm(query=query, limit_per_drive=limit, total_limit=limit)
        results = []
        for file_data in matching_files_data:
             try: results.append(FileInfo(**file_data))
             except Exception as model_err: logger.warning(f"Skip search result: bad model data {model_err}. Data: {file_data}")
        logger.info(f"Return {len(results)} search results for '{query}' for {username}"); return results
    except Exception as e: logger.error(f"Search error: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Error searching files.")

@app.post("/files/upload", tags=["Files"])
async def upload_file_endpoint( file: UploadFile = File(...), current_user: Dict = Depends(get_current_user)): # (Keep as is)
    user_id = current_user["_id"]; username = current_user["username"]; upload_dir = "uploads"; os.makedirs(upload_dir, exist_ok=True)
    safe_filename = os.path.basename(file.filename or "uploaded_file"); temp_file_location = os.path.join(upload_dir, f"{user_id}_{safe_filename}")
    try:
        with open(temp_file_location, "wb") as buffer: shutil.copyfileobj(file.file, buffer); logger.info(f"Temp file saved: {temp_file_location}")
    except Exception as e: logger.error(f"Failed save temp: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Failed save upload.")
    finally: file.file.close()
    drive_manager = DriveManager(user_id=user_id);
    try: # Add try block around drive logic and upload
        if not drive_manager.drives: raise HTTPException(status_code=400, detail="No drives connected.")
        sorted_buckets_info = drive_manager.get_sorted_buckets()
        if not sorted_buckets_info: raise HTTPException(status_code=400, detail="No storage space.")
        best_drive_instance = sorted_buckets_info[0][1]; best_bucket_number = getattr(best_drive_instance, 'bucket_number', None)
        if best_bucket_number is None: raise HTTPException(status_code=500, detail="Internal bucket error.")
        provider = type(best_drive_instance).__name__; logger.info(f"Uploading '{safe_filename}' to {provider} Bucket {best_bucket_number}")
        if isinstance(best_drive_instance, GoogleDrive):
            handler = GoogleDriveFile(drive_manager); mime = file.content_type or mimetypes.guess_type(safe_filename)[0] or "app/octet-stream"
            handler.upload_file(temp_file_location, safe_filename, mime)
        elif isinstance(best_drive_instance, DropboxService):
             token = None;
             if hasattr(best_drive_instance.service, 'session'): token = best_drive_instance.service.session.access_token
             elif hasattr(best_drive_instance.service, '_oauth2_access_token'): token = best_drive_instance.service._oauth2_access_token
             if not token: raise Exception("Failed get Dropbox token.")
             handler = DropBoxFile(token, drive_manager); handler.upload_file(temp_file_location, safe_filename)
        else: raise HTTPException(status_code=400, detail=f"Unsupported drive: {provider}")
        logger.info(f"Upload success: '{safe_filename}' to {provider} Bucket {best_bucket_number}")
        return {"status": "success", "message": f"File '{safe_filename}' uploaded to {provider} Bucket {best_bucket_number}"}
    except Exception as e: # Catch any exception during drive logic or upload
        logger.error(f"Upload failed for {safe_filename}: {e}", exc_info=True)
        # Reraise specific types or generic 500
        if isinstance(e, HTTPException): raise e
        if isinstance(e, NotImplementedError): raise HTTPException(status_code=501, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    finally: # Ensure cleanup happens even if drive logic fails
        if os.path.exists(temp_file_location): 
            try: os.remove(temp_file_location); logger.info("Cleaned temp upload.")
            except OSError as e: logger.warning(f"Could not remove temp upload: {e}")

@app.get("/files/download", tags=["Files"])
async def download_file_endpoint( file_name: str = Query(...), current_user: Dict = Depends(get_current_user)): # (Keep as is)
    user_id = current_user["_id"]; username = current_user["username"]; drive_manager = DriveManager(user_id=user_id); download_dir = "downloads"; os.makedirs(download_dir, exist_ok=True)
    logger.info(f"{username} requesting download: '{file_name}'")
    if not drive_manager.drives: raise HTTPException(status_code=404, detail="No drives connected.")
    try: # GDrive
        gdrive_handler = GoogleDriveFile(drive_manager); user_dl_path = os.path.join(download_dir, str(user_id))
        downloaded_path = gdrive_handler.download_from_all_buckets(file_name, user_dl_path)
        if downloaded_path and os.path.exists(downloaded_path):
            mime, _ = mimetypes.guess_type(downloaded_path); fname=os.path.basename(downloaded_path)
            logger.info(f"Returning GDrive file: '{fname}'"); return FileResponse(path=downloaded_path, filename=fname, media_type=mime or "app/octet-stream")
    except Exception as e: logger.error(f"GDrive download check failed: {e}", exc_info=True)
    try: # Dropbox
        dbx_accounts = [d for d in drive_manager.drives if isinstance(d, DropboxService) and d.service]
        for dbx_instance in dbx_accounts:
             token = None;
             if hasattr(dbx_instance.service, 'session'): token = dbx_instance.service.session.access_token
             elif hasattr(dbx_instance.service, '_oauth2_access_token'): token = dbx_instance.service._oauth2_access_token
             if not token: logger.warning(f"Skipping DBX Bucket {dbx_instance.bucket_number}: No token."); continue
             dbx_handler = DropBoxFile(token, drive_manager); dbx_api_path = dbx_handler.search_file(file_name)
             if dbx_api_path:
                 user_dl_path = os.path.join(download_dir, str(user_id)); os.makedirs(user_dl_path, exist_ok=True); local_path = os.path.join(user_dl_path, os.path.basename(dbx_api_path))
                 downloaded_path = dbx_handler.download_file(dbx_api_path, local_path)
                 if downloaded_path and os.path.exists(downloaded_path):
                     mime, _ = mimetypes.guess_type(downloaded_path); fname=os.path.basename(downloaded_path)
                     logger.info(f"Returning Dropbox file: '{fname}'"); return FileResponse(path=downloaded_path, filename=fname, media_type=mime or "app/octet-stream")
                 else: logger.error(f"Dropbox download failed for {local_path}"); break # Stop if found but failed download
    except Exception as e: logger.error(f"Dropbox download check failed: {e}", exc_info=True)
    logger.warning(f"File '{file_name}' not found for download by {username}.")
    raise HTTPException(status_code=404, detail=f"File '{file_name}' not found.")

# --- LLM Endpoints ---
def _get_drive_service_instance(drive_manager: DriveManager, provider: str, bucket: int) -> Optional[object]: # (Keep as is)
    target_class = GoogleDrive if provider == "GoogleDrive" else DropboxService if provider == "Dropbox" else None;
    if not target_class: return None
    for drive in drive_manager.drives:
        if isinstance(drive, target_class) and hasattr(drive, 'bucket_number') and drive.bucket_number == bucket: return drive.service
    return None

@app.post("/llm/ask", tags=["LLM"])
async def llm_ask_endpoint( request_data: AskRequest, current_user: Dict = Depends(get_current_user)):
    original_question = request_data.question; telegram_user_id = request_data.user_id
    user_id = current_user["_id"]; username = current_user["username"]
    if not GROQ_API_KEY: raise HTTPException(status_code=503, detail="LLM unavailable.")
    logger.info(f"{username} (TG:{telegram_user_id}) asking: '{original_question}'")
    search_query = await get_search_keywords_from_llm(original_question)
    file_metadata_context = ""; extracted_snippets_context = ""; relevant_files = []
    if not search_query: file_metadata_context = "\n(Note: Could not find keywords.)"
    else:
        logger.info(f"Using keywords: '{search_query}'");
        try:
            drive_manager = DriveManager(user_id=user_id); raw_files = drive_manager.search_files_for_llm(query=search_query, limit_per_drive=5, total_limit=10)
            if raw_files:
                file_lines = ["Found relevant files:"]; parsed_files = []
                for data in raw_files: 
                    try: parsed_files.append(FileInfo(**data)); 
                    except Exception as e: logger.warning(f"Skipping file data, parse error: {e}. Data: {data}")
                relevant_files = parsed_files
                file_lines.extend([f"- {f.name} ({f.provider})" for f in relevant_files])
                if len(file_lines)>1: file_metadata_context = "\n".join(file_lines); logger.info("Got metadata.")
                else: file_metadata_context = "\n(Note: No valid files found.)" # Changed message
            else: file_metadata_context = "\n(Note: No files found matching keywords.)" # Changed message

            # --- CORRECTED Snippet Extraction Logic ---
            if relevant_files:
                # --- FIX: Filter duplicates before selecting ---
                seen_file_identifiers = set()
                unique_relevant_files = []
                for file in relevant_files:
                    identifier = f"{file.provider}:{file.id or file.path_lower}" # Unique ID
                    if identifier not in seen_file_identifiers:
                        unique_relevant_files.append(file)
                        seen_file_identifiers.add(identifier)
                # --- END FIX ---

                # --- FIX: Increase extraction limit ---
                MAX_FILES_TO_EXTRACT = 5 # Increased limit
                count = 0
                files_to_extract = []
                # Select from the UNIQUE list
                for file in unique_relevant_files:
                    if count >= MAX_FILES_TO_EXTRACT: break
                    file_ext = os.path.splitext(file.name)[1].lower()
                    if file_ext in SUPPORTED_TEXT_EXTENSIONS:
                        files_to_extract.append(file)
                        count += 1
                # --- END FIX ---

                if files_to_extract:
                    logger.info(f"Attempting extraction from (up to {MAX_FILES_TO_EXTRACT}): {[f.name for f in files_to_extract]}") # Log unique files
                    snippet_lines = ["\n\nExtracted Content Snippets:"]; MAX_LEN=2500; TOTAL_MAX=8000; total_len=0
                    gdrive_handler = GoogleDriveFile(drive_manager)
                    # dbx_handler created inside loop

                    for file in files_to_extract: # Iterate through the selected unique files
                        if total_len >= TOTAL_MAX: logger.warning("Max snippet length reached."); snippet_lines.append("\n(More snippets omitted...)"); break
                        extracted = None; buffer = None
                        try: # Wrap download/extraction
                            if file.provider == "GoogleDrive" and file.id and file.bucket:
                                service = _get_drive_service_instance(drive_manager, "GoogleDrive", file.bucket)
                                if service: buffer = gdrive_handler.download_file_content_by_id(service, file.id, file.size)
                                if buffer: extracted = gdrive_handler.extract_text_from_content(buffer, file.name, file.mimeType)
                                else: logger.warning(f"Failed download GDrive buffer {file.name}")
                            elif file.provider == "Dropbox" and file.path_lower and file.access_token:
                                 dbx_handler = DropBoxFile(file.access_token, drive_manager)
                                 buffer = dbx_handler.download_file_content_by_path(file.path_lower)
                                 if buffer: extracted = dbx_handler.extract_text_from_content(buffer, file.name)
                                 else: logger.warning(f"Failed download Dropbox buffer {file.name}")
                        except Exception as ex_err: logger.error(f"Extract error {file.name}: {ex_err}", exc_info=True)
                        finally:
                             if buffer: 
                                 try: buffer.close() 
                                 except: pass # Cleanup buffer

                        # Append snippet or failure note
                        if extracted: snippet = extracted[:MAX_LEN] + ("..." if len(extracted) > MAX_LEN else ""); snippet_lines.extend([f"\n--- Snippet: {file.name} ---", snippet, f"--- End: {file.name} ---"]); total_len += len(snippet)
                        else: snippet_lines.append(f"\n(Could not extract text from {file.name})")
                    # --- End For Loop ---

                    if len(snippet_lines) > 1: extracted_snippets_context = "\n".join(snippet_lines); logger.info("Generated snippets context.")
            # --- End Snippet Extraction Logic (Corrected) ---

        except Exception as e: logger.error(f"File search/extract error: {e}", exc_info=True); file_metadata_context = "\n(Note: Error getting file context.)"; extracted_snippets_context = ""

    # --- Prepare and Call Final LLM (Keep as is) ---
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
        "Speak as if you either know or don't know the information directly. Do not mention where you found the extractd snippets unless explicitly asked."
        "Do NOT claim to have 'read' the entire file; you only see the provided snippets. Be factual about your limitations, but again, do not mention where you found the extractd snippets unless explicitly asked."
    )
    full_messages = [{"role": "system", "content": system_prompt}] + [m for m in memory if m.get("role") != "system"]
    combined_context = file_metadata_context + extracted_snippets_context;
    if combined_context.strip(): full_messages.append({"role": "system", "content": f"File Context: {combined_context}"})
    full_messages.append({"role": "user", "content": original_question}); MAX_MEMORY = 10
    non_system = [m for m in full_messages if m['role'] != 'system'];
    if len(non_system) > MAX_MEMORY: full_messages = [m for m in full_messages if m['role'] == 'system'] + non_system[-MAX_MEMORY:]
    try: # Call Groq
        logger.debug(f"Sending to Groq (Snippets: {extracted_snippets_context[:100]}...)"); client = Groq(api_key=GROQ_API_KEY)
        completion = await asyncio.to_thread(client.chat.completions.create, model="llama-3.3-70b-versatile", messages=full_messages, temperature=0.7) # Model Changed
        response_text = completion.choices[0].message.content.strip(); logger.info(f"Groq answer received.")
        current_memory = session_memory[telegram_user_id]; current_memory.append({"role": "user", "content": original_question}); current_memory.append({"role": "assistant", "content": response_text})
        session_memory[telegram_user_id] = current_memory[-MAX_MEMORY:]; return {"response": response_text}
    except Exception as e: logger.error(f"Groq call failed: {e}", exc_info=True); raise HTTPException(status_code=503, detail=f"LLM request failed: {e}")

@app.post("/llm/reset", tags=["LLM"])
async def reset_llm_memory(request_data: ResetRequest): # (Keep as is)
    if not request_data.user_id: raise HTTPException(status_code=400, detail="Missing user_id")
    logger.info(f"Resetting memory for TG ID: {request_data.user_id}")
    session_memory.pop(request_data.user_id, None); return {"message": f"Memory reset for user {request_data.user_id}"}

# --- Main Application Runner ---
if __name__ == "__main__":
    import uvicorn
    # Startup event handles index setup when running via uvicorn command
    port = int(os.getenv("PORT", 8000)); host = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Starting Syncly API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port) # Use app object directly

# --- END OF FILE api.py ---