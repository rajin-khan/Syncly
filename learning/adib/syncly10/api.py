# --- START OF FILE api.py ---

import asyncio
import base64
import hashlib
import io
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Query, Body, Path
from fastapi.security import OAuth2PasswordBearer # Keep for get_current_user
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import uuid # Needed for link_id
from pymongo import ASCENDING # Needed for index creation
from AuthManager import AuthManager
from DriveManager import DriveManager
from fastapi.staticfiles import StaticFiles
import shutil
from bson import ObjectId
import dropbox
import logging
import mimetypes
from typing import List, Optional, Dict, Tuple, Union, Any # Added Union, Any
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse # Added JSONResponse
from Database import Database # Use the corrected Database class
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
API_BASE_URL = os.getenv("API_BASE_URL") # Needed for constructing login URLs

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
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") # Used by get_current_user

# --- Constants ---
LINK_EXPIRY_MINUTES = 5 # Link validity duration

# --- Pydantic Models (Matching the "buggy" version) ---
class UserCreate(BaseModel): username: str; password: str; email: str
class UserResponse(BaseModel): username: str; email: str
class Token(BaseModel): access_token: str; token_type: str = "bearer"
class TokenData(BaseModel): username: str | None = None
class StorageInfo(BaseModel): provider: str; drive_number: int; storage_limit_gb: float; used_storage_gb: float; free_storage_gb: float
class StorageSummary(BaseModel): storages: List[StorageInfo]; total_storage_gb: float; used_storage_gb: float; free_storage_gb: float
class FileInfo(BaseModel):
    id: Optional[str] = None; name: str; provider: str; size: Optional[int] = None; path: str
    mimeType: Optional[str] = None; bucket: Optional[int] = None; path_lower: Optional[str] = None
    # Exclude token from default serialization unless specifically requested
    access_token: Optional[str] = Field(None, exclude=True) # Correct use of Field(exclude=True)
class AddDriveRequest(BaseModel): drive_type: str
class AskRequest(BaseModel): question: str; user_id: str # user_id = telegram_id
class ResetRequest(BaseModel): user_id: str # user_id = telegram_id

# Models for Bot Link Auth Flow
class TokenRequestForm(BaseModel): # Used by /token
    username: str; password: str; link_id: Optional[str] = None
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
    db_instance = Database.get_instance() # Use class method
    if not db_instance or not db_instance.client:
        logger.critical("FATAL: DB connection failed on startup. API cannot function.")
        # Consider exiting or preventing FastAPI startup fully if DB is critical
        # For now, just log critical error. Endpoints will fail later.
        return

    # Ensure collections are accessible
    if db_instance.pending_links_collection is None or db_instance.users_collection is None:
         logger.critical("FATAL: DB collections ('pending_links' or 'users') not available on startup.")
         return

    try:
        # Setup pending_links Collection TTL Index and Unique Link ID Index
        pending_links_collection = db_instance.pending_links_collection
        idx_pending_info = pending_links_collection.index_information()
        ttl_index_name = "expires_at_ttl_index" # More descriptive name
        link_id_index_name = "link_id_unique_index"

        if ttl_index_name not in idx_pending_info:
            logger.info(f"Creating TTL index '{ttl_index_name}' on 'pending_links.expires_at'...")
            pending_links_collection.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0, name=ttl_index_name)
            logger.info(f"Index '{ttl_index_name}' created.")
        else: logger.info(f"Index '{ttl_index_name}' already exists.")

        if link_id_index_name not in idx_pending_info:
            logger.info(f"Creating unique index '{link_id_index_name}' on 'pending_links.link_id'...")
            pending_links_collection.create_index([("link_id", ASCENDING)], unique=True, name=link_id_index_name)
            logger.info(f"Index '{link_id_index_name}' created.")
        else: logger.info(f"Index '{link_id_index_name}' already exists.")

        # Setup users Collection sparse index on telegram_id
        users_collection = db_instance.users_collection
        idx_users_info = users_collection.index_information()
        tg_id_index_name = "telegram_id_sparse_index"
        if tg_id_index_name not in idx_users_info:
            logger.info(f"Creating sparse index '{tg_id_index_name}' on 'users.telegram_id'...")
            # Use sparse=True so only documents with telegram_id are indexed
            users_collection.create_index([("telegram_id", ASCENDING)], sparse=True, name=tg_id_index_name)
            logger.info(f"Index '{tg_id_index_name}' created.")
        else: logger.info(f"Index '{tg_id_index_name}' already exists.")

        logger.info("DB index setup check complete.")
    except Exception as e:
        logger.error(f"DB index setup error during startup: {e}", exc_info=True)
        # Depending on severity, might want to stop the app here

# --- Helper functions ---
def get_password_hash(password: str) -> str: sha256_hash = hashlib.sha256(password.encode('utf-8')).digest(); return base64.b64encode(sha256_hash).decode('utf-8')
def verify_password(plain_password: str, hashed_password: str) -> bool: input_hash = get_password_hash(plain_password); return input_hash == hashed_password
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None): to_encode = data.copy(); expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)); to_encode.update({"exp": expire}); return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Authentication Middleware (get_current_user - as provided in "buggy") ---
async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try: payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]); username: str | None = payload.get("sub");
    except JWTError as e: logger.warning(f"JWT validation failed: {e}"); raise credentials_exception from e
    if username is None: raise credentials_exception
    db = Database.get_instance() # Use class method
    # Check if DB instance or collection is None
    if not db or db.users_collection is None:
        logger.error("DB unavailable for get_current_user.")
        raise HTTPException(status_code=503, detail="Database service unavailable")
    user = db.users_collection.find_one({"username": username})
    if user is None: logger.warning(f"User '{username}' not found during JWT validation."); raise credentials_exception
    user["user_id_str"] = str(user["_id"]); # Add string version of ObjectId
    user["telegram_id"] = user.get("telegram_id") # Include if present
    return user


# --- Keyword Extraction Helpers (Keep as is) ---
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
    if not question: return ""
    if not GROQ_API_KEY: logger.warning("Groq key missing, using simple keywords."); return extract_keywords_simple(question)
    keyword_model = "llama-3.1-8b-instant"; system_prompt = (...); messages = [...] # Keep full prompt/logic
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
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"User Question: '{question}'"}]
    try:
        logger.info(f"LLM keyword extraction for: '{question[:50]}...'"); client = Groq(api_key=GROQ_API_KEY)
        completion = await asyncio.to_thread(client.chat.completions.create, model=keyword_model, messages=messages, temperature=0.1, max_tokens=60)
        raw_keywords = completion.choices[0].message.content.strip(); logger.info(f"LLM keywords raw: '{raw_keywords}'")
        keywords = raw_keywords.lower(); prefixes = ["keywords:", "output:", "keywords ", "output "];
        for prefix in prefixes:
            if keywords.startswith(prefix): keywords = keywords[len(prefix):].strip()
        keywords = keywords.translate(str.maketrans('', '', string.punctuation)); keywords = re.sub(r'\s+', ' ', keywords).strip()
        if not keywords: logger.warning("LLM keywords empty after parsing."); return extract_keywords_simple(question)
        logger.info(f"LLM keywords clean: '{keywords}'"); return keywords
    except Exception as e: logger.error(f"LLM keyword error: {e}", exc_info=True); return extract_keywords_simple(question)


# --- API Endpoints ---

# --- Auth Endpoints ---
@app.post("/register", status_code=status.HTTP_201_CREATED, tags=["Auth"])
async def register(user_data: UserCreate): # Keep as is
    db = Database.get_instance()
    if not db or db.users_collection is None: raise HTTPException(status_code=503, detail="Database error")
    if db.users_collection.find_one({"username": {"$regex": f"^{user_data.username}$", "$options": "i"}}): raise HTTPException(status_code=400, detail="Username exists")
    if db.users_collection.find_one({"email": {"$regex": f"^{user_data.email}$", "$options": "i"}}): raise HTTPException(status_code=400, detail="Email exists")
    hashed_password = get_password_hash(user_data.password); user_doc = {"username": user_data.username, "password": hashed_password, "email": user_data.email, "drives": [], "created_at": datetime.utcnow(), "telegram_id": None}
    result = db.users_collection.insert_one(user_doc); logger.info(f"User '{user_data.username}' registered ID: {result.inserted_id}"); return {"message": "User registered"}

# --- Corrected /token Endpoint (Handles both flows) ---
@app.post("/token", response_model=Union[Token, Dict[str, str]], tags=["Auth"])
async def login_for_access_token_or_link(form_data: TokenRequestForm = Body(...)):
    db = Database.get_instance()
    if not db or db.users_collection is None or db.pending_links_collection is None:
        logger.error("Login failed: DB connection or required collection missing.")
        raise HTTPException(status_code=503, detail="Database service unavailable")

    user = db.users_collection.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user["password"]):
        logger.warning(f"Login failed for user: {form_data.username}")
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    user_id = user["_id"]; username = user["username"]; link_id = form_data.link_id

    # --- Bot Link Flow ---
    if link_id:
        logger.info(f"Processing login via link flow for link_id: {link_id}")
        pending_link = db.pending_links_collection.find_one({"link_id": link_id, "expires_at": {"$gt": datetime.utcnow()}})

        if not pending_link:
            logger.warning(f"Link ID {link_id} not found or expired.")
            raise HTTPException(status_code=404, detail="Login link not found or expired. Please try /login again.")

        if pending_link.get('validated', False):
            logger.warning(f"Link ID {link_id} has already been used.")
            raise HTTPException(status_code=410, detail="Login link has already been used. Please try /login again.") # 410 Gone

        # Atomically update the link document: set validated=True and user_id
        update_result = db.pending_links_collection.update_one(
            {"link_id": link_id, "validated": False}, # Ensure it wasn't validated concurrently
            {"$set": {"user_id": user_id, "validated": True}}
        )

        if update_result.modified_count == 1:
            logger.info(f"Link {link_id} successfully validated for user {username}")
            # Return success message for the web page
            return JSONResponse(content={"message": "Login successful! You can now return to Telegram."})
        else:
            # This could happen if the link was validated between the find_one and update_one calls (race condition)
            # Or if the document structure was unexpected.
            logger.error(f"Failed to update pending link {link_id} state (modified_count={update_result.modified_count}).")
            # Check again if it was already validated by another request
            check_again = db.pending_links_collection.find_one({"link_id": link_id})
            if check_again and check_again.get('validated'):
                 raise HTTPException(status_code=410, detail="Login link was already used.")
            else:
                 raise HTTPException(status_code=409, detail="Failed to process login link. Please try again.") # 409 Conflict

    # --- Standard Web/API Login Flow ---
    else:
        logger.info(f"Standard login successful for user: {username}")
        access_token = create_access_token(data={"sub": username})
        return Token(access_token=access_token)

# --- Corrected /auth/create_link Endpoint ---
@app.post("/auth/create_link", response_model=CreateLinkResponse, tags=["Auth Helper"])
async def create_auth_link(request: CreateLinkRequest):
    db = Database.get_instance()
    if not db or db.pending_links_collection is None:
        logger.error("Create link failed: DB connection or pending_links collection unavailable.")
        raise HTTPException(status_code=503, detail="Database service unavailable")

    link_id = str(uuid.uuid4())
    now = datetime.utcnow()
    expires = now + timedelta(minutes=LINK_EXPIRY_MINUTES)

    try:
        # Insert the new pending link document
        insert_result = db.pending_links_collection.insert_one({
            "link_id": link_id,
            "telegram_id": request.telegram_id,
            "user_id": None, # Initially null
            "validated": False, # Initially false
            "created_at": now,
            "expires_at": expires # TTL index will use this
        })
        logger.info(f"Created pending link {link_id} (DB ID: {insert_result.inserted_id}) for telegram_id {request.telegram_id}")

        # Construct the login URL for the web page
        login_url = f"{API_BASE_URL.rstrip('/')}/static/login.html?link_id={link_id}"

        return CreateLinkResponse(link_id=link_id, login_url=login_url)

    except Exception as e:
        logger.error(f"Failed to insert pending link document for telegram_id {request.telegram_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create login link due to a server error.")

# --- Corrected /auth/complete_link Endpoint ---
@app.post("/auth/complete_link", response_model=CompleteLinkResponse, tags=["Auth Helper"])
async def complete_auth_link(request: CompleteLinkRequest):
    db = Database.get_instance()
    if not db or db.pending_links_collection is None or db.users_collection is None:
        logger.error("Complete link failed: DB connection or required collections unavailable.")
        raise HTTPException(status_code=503, detail="Database service unavailable")

    logger.info(f"Attempting to complete link_id: {request.link_id} for telegram_id: {request.telegram_id}")

    # Find the link, ensuring it hasn't expired (TTL index handles deletion, but check anyway)
    link_data = db.pending_links_collection.find_one({"link_id": request.link_id, "expires_at": {"$gt": datetime.utcnow()}})

    if not link_data:
        logger.warning(f"Complete link failed: Link {request.link_id} not found or expired.")
        raise HTTPException(status_code=404, detail="Link not found or expired.") # 404 Not Found

    # Verify Telegram ID matches
    if link_data.get("telegram_id") != request.telegram_id:
        logger.error(f"Telegram ID mismatch for link {request.link_id}. Expected {link_data.get('telegram_id')}, got {request.telegram_id}.")
        # Consider deleting the mismatched link for security? Or just fail.
        # db.pending_links_collection.delete_one({"link_id": request.link_id})
        raise HTTPException(status_code=403, detail="Invalid link (User mismatch).") # 403 Forbidden

    # Check if the link was validated by the web login flow
    if not link_data.get("validated", False) or not link_data.get("user_id"):
        logger.warning(f"Link {request.link_id} was not validated via web login yet.")
        # Use 400 Bad Request, as the client (bot) called this endpoint prematurely
        raise HTTPException(status_code=400, detail="Link process not completed via web login yet.")

    user_id = link_data["user_id"]
    user = db.users_collection.find_one({"_id": ObjectId(user_id)}) # Ensure user_id is ObjectId

    if not user:
        logger.error(f"User (ID: {user_id}) associated with link {request.link_id} not found in users collection.")
        # Clean up the invalid link
        db.pending_links_collection.delete_one({"link_id": request.link_id})
        raise HTTPException(status_code=404, detail="Associated user account not found.")

    username = user["username"]

    # --- Associate Telegram ID with User Account in DB (if not already set) ---
    # This helps link the Telegram identity to the Syncly account permanently
    if user.get("telegram_id") != request.telegram_id:
        update_res = db.users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"telegram_id": request.telegram_id}}
        )
        if update_res.modified_count == 1:
            logger.info(f"Associated telegram_id {request.telegram_id} with user {username}")
        else:
            # Log if update failed, but proceed anyway as auth is the primary goal here
             logger.warning(f"Failed to update telegram_id for user {username}. Result: {update_res.raw_result}")


    # Generate the final JWT for the bot
    access_token = create_access_token(data={"sub": username})

    # --- CRITICAL: Delete the used link ---
    delete_result = db.pending_links_collection.delete_one({"link_id": request.link_id})
    if delete_result.deleted_count == 1:
        logger.info(f"Successfully completed and deleted link {request.link_id} for user {username}")
    else:
        # This shouldn't happen if find_one succeeded, but log defensively
        logger.error(f"Failed to delete completed link {request.link_id} (deleted_count={delete_result.deleted_count}).")

    return CompleteLinkResponse(access_token=access_token, username=username)


@app.post("/validate-token", tags=["Auth"]) # Keep as is
async def validate_token(token: str = Query(...)):
    try: payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]); username: str | None = payload.get("sub")
    except JWTError as e: logger.error(f"JWT validation failed: {e}"); raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    if username is None: raise HTTPException(status_code=401, detail="Invalid token: No username")
    db = Database.get_instance();
    if not db or db.users_collection is None : raise HTTPException(status_code=503, detail="Database unavailable")
    if not db.users_collection.find_one({"username": username}): raise HTTPException(status_code=401, detail="Invalid token: User not found")
    return {"username": username}

# --- User Endpoints (Keep as is) ---
@app.get("/users/me", response_model=UserResponse, tags=["Users"])
async def read_users_me(current_user: Dict = Depends(get_current_user)): return UserResponse(username=current_user["username"], email=current_user["email"])

# --- Storage Endpoints (Keep as is) ---
@app.get("/storage", response_model=StorageSummary, tags=["Storage"])
async def get_storage_info(current_user: Dict = Depends(get_current_user)):
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
async def add_drive(request: AddDriveRequest, current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); db = Database.get_instance()
    if not db or db.drives_collection is None: raise HTTPException(status_code=503, detail="Database unavailable")
    existing_drives_count = db.drives_collection.count_documents({"user_id": user_id}); bucket_number = existing_drives_count + 1
    logger.info(f"Adding {request.drive_type} as bucket {bucket_number} for {current_user['username']}")
    try:
        if request.drive_type == "GoogleDrive": instance = GoogleDrive(); drive_manager.add_drive(instance, bucket_number, "GoogleDrive"); return {"status": "success", "message": f"Google Drive bucket {bucket_number} added."}
        elif request.drive_type == "Dropbox": key=os.getenv("DROPBOX_APP_KEY"); secret=os.getenv("DROPBOX_APP_SECRET"); assert key and secret and key != "YOUR_DROPBOX_APP_KEY"; instance = DropboxService(app_key=key, app_secret=secret); drive_manager.add_drive(instance, bucket_number, "Dropbox"); return {"status": "success", "message": f"Dropbox bucket {bucket_number} added."}
        else: raise HTTPException(status_code=400, detail="Invalid drive type.")
    except AssertionError: raise HTTPException(status_code=500, detail="Server Error: Dropbox app keys not configured.")
    except Exception as e: logger.error(f"Failed add drive: {e}", exc_info=True); raise HTTPException(status_code=500, detail=f"Failed to add drive: {e}")

# --- File Endpoints (Keep as is, ensuring FileInfo(**data) works) ---
@app.get("/viewfiles", response_model=List[FileInfo], tags=["Files"])
async def list_files( query: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); username = current_user['username']
    if not drive_manager.drives: return []
    all_files_data = [] # Use list for raw data
    logger.info(f"Listing files for {username} (q='{query}', l={limit}, o={offset})")
    for drive in drive_manager.drives:
        provider = type(drive).__name__
        try:
            files_data = drive.listFiles(query=query) # listFiles should return list of dicts
            # Ensure provider and potentially access_token are added if missing
            for file_d in files_data:
                if "provider" not in file_d: file_d["provider"] = provider
                if "bucket" not in file_d and hasattr(drive, "bucket_number"): file_d["bucket"] = drive.bucket_number
                # Include token for Dropbox if needed downstream
                if provider == "Dropbox" and "access_token" not in file_d:
                     token = None
                     if hasattr(drive.service, 'session'): token = drive.service.session.access_token
                     elif hasattr(drive.service, '_oauth2_access_token'): token = drive.service._oauth2_access_token
                     file_d["access_token"] = token # Add token to the dict
            all_files_data.extend(files_data)
        except Exception as e: logger.error(f"Error listing from {provider}: {e}", exc_info=True)

    # De-duplicate based on a unique identifier
    unique_files_dict = {}
    for file_data in all_files_data:
         provider = file_data.get("provider", "?")
         key_id = file_data.get("id", file_data.get("path_lower", file_data.get("name", "Unknown")))
         key = (provider, key_id)
         if key not in unique_files_dict:
             unique_files_dict[key] = file_data

    # Sort unique files
    sorted_unique_files_data = sorted(unique_files_dict.values(), key=lambda x: x.get("name", "").lower())
    total_unique = len(sorted_unique_files_data)

    # Paginate the final list
    paginated_files_data = sorted_unique_files_data[offset : offset + limit]

    # Convert to Pydantic models safely
    results = []
    for file_data in paginated_files_data:
        try:
             # Ensure size is int or None
             size_val = file_data.get("size")
             file_data["size"] = int(size_val) if size_val is not None and str(size_val).isdigit() else None
             # Ensure all required fields for FileInfo are present or have defaults handled by Pydantic
             results.append(FileInfo(**file_data))
        except Exception as model_err: logger.warning(f"Skipping file model creation error: {model_err}. Data: {file_data}")

    logger.info(f"Returning {len(results)}/{total_unique} unique files for {username}"); return results

@app.get("/search_files", response_model=List[FileInfo], tags=["Files"])
async def search_files_endpoint( query: str = Query(...), limit: int = Query(10, ge=1, le=50), current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; drive_manager = DriveManager(user_id=user_id); username = current_user['username']
    if not drive_manager.drives: return []
    logger.info(f"{username} searching '{query}' (limit {limit})")
    try:
        matching_files_data = drive_manager.search_files_for_llm(query=query, limit_per_drive=limit, total_limit=limit) # Returns list of dicts
        results = []
        for file_data in matching_files_data:
             try:
                 # Ensure size is int or None
                 size_val = file_data.get("size")
                 file_data["size"] = int(size_val) if size_val is not None and str(size_val).isdigit() else None
                 results.append(FileInfo(**file_data)) # Unpack dict into model
             except Exception as model_err: logger.warning(f"Skipping search result model creation error: {model_err}. Data: {file_data}")
        logger.info(f"Returning {len(results)} search results for '{query}' for {username}"); return results
    except Exception as e: logger.error(f"Search error: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Error searching files.")

@app.post("/files/upload", tags=["Files"])
async def upload_file_endpoint( file: UploadFile = File(...), current_user: Dict = Depends(get_current_user)):
    user_id = current_user["_id"]; username = current_user["username"]; upload_dir = "uploads"; os.makedirs(upload_dir, exist_ok=True)
    # Ensure filename is safe for filesystem path
    safe_filename = os.path.basename(file.filename or "uploaded_file").replace("..", "").replace("/", "").replace("\\", "")
    if not safe_filename: safe_filename = "uploaded_file" # Handle empty case
    temp_file_location = os.path.join(upload_dir, f"{user_id}_{safe_filename}")
    try:
        with open(temp_file_location, "wb") as buffer: shutil.copyfileobj(file.file, buffer); logger.info(f"Temp file saved: {temp_file_location}")
    except Exception as e: logger.error(f"Failed save temp upload: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Failed to save upload.")
    finally: file.file.close()

    drive_manager = DriveManager(user_id=user_id);
    try:
        if not drive_manager.drives: raise HTTPException(status_code=400, detail="No drives connected.")
        sorted_buckets_info = drive_manager.get_sorted_buckets()
        if not sorted_buckets_info: raise HTTPException(status_code=400, detail="No available storage space.")
        best_drive_instance = sorted_buckets_info[0][1]; best_bucket_number = getattr(best_drive_instance, 'bucket_number', None)
        if best_bucket_number is None: raise HTTPException(status_code=500, detail="Internal error determining upload bucket.")
        provider = type(best_drive_instance).__name__; logger.info(f"Uploading '{safe_filename}' to {provider} Bucket {best_bucket_number}")

        if isinstance(best_drive_instance, GoogleDrive):
            handler = GoogleDriveFile(drive_manager); mime_type = file.content_type or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
            handler.upload_file(temp_file_location, safe_filename, mime_type)
        elif isinstance(best_drive_instance, DropboxService):
             access_token = None;
             # Get token from the specific service instance
             if hasattr(best_drive_instance.service, 'session') and hasattr(best_drive_instance.service.session, 'access_token'): access_token = best_drive_instance.service.session.access_token
             elif hasattr(best_drive_instance.service, '_oauth2_access_token'): access_token = best_drive_instance.service._oauth2_access_token
             if not access_token: raise Exception("Failed to get Dropbox access token for upload.")
             handler = DropBoxFile(access_token, drive_manager); # Instantiate handler with token
             handler.upload_file(temp_file_location, safe_filename) # Upload method handles the rest
        else: raise HTTPException(status_code=400, detail=f"Unsupported drive type selected: {provider}")

        logger.info(f"Upload success: '{safe_filename}' to {provider} Bucket {best_bucket_number}")
        return {"status": "success", "message": f"File '{safe_filename}' uploaded to {provider} (Bucket {best_bucket_number})"}
    except Exception as e: # Catch any exception during drive logic or upload
        logger.error(f"Upload failed for {safe_filename}: {e}", exc_info=True)
        if isinstance(e, HTTPException): raise e
        if isinstance(e, NotImplementedError): raise HTTPException(status_code=501, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    finally: # Ensure cleanup happens
        if os.path.exists(temp_file_location):
            try: os.remove(temp_file_location); logger.info(f"Cleaned up temp upload file: {temp_file_location}")
            except OSError as e: logger.warning(f"Could not remove temp upload file {temp_file_location}: {e}")

@app.get("/files/download", tags=["Files"])
async def download_file_endpoint( file_name: str = Query(...), current_user: Dict = Depends(get_current_user)): # Keep as is
    user_id = current_user["_id"]; username = current_user["username"]; drive_manager = DriveManager(user_id=user_id); download_dir = "downloads"; os.makedirs(download_dir, exist_ok=True)
    logger.info(f"{username} requesting download: '{file_name}'")
    if not drive_manager.drives: raise HTTPException(status_code=404, detail="No drives connected.")
    try: # GDrive
        gdrive_handler = GoogleDriveFile(drive_manager); user_dl_path = os.path.join(download_dir, str(user_id))
        downloaded_path = gdrive_handler.download_from_all_buckets(file_name, user_dl_path) # Assumes this method exists and works
        if downloaded_path and os.path.exists(downloaded_path):
            mime, _ = mimetypes.guess_type(downloaded_path); fname=os.path.basename(downloaded_path); logger.info(f"Returning GDrive file: '{fname}'"); return FileResponse(path=downloaded_path, filename=fname, media_type=mime or "application/octet-stream", headers={"Content-Disposition": f"attachment; filename=\"{fname}\""})
    except Exception as e: logger.error(f"GDrive download check failed: {e}", exc_info=True) # Continue
    try: # Dropbox
        dbx_accounts = [d for d in drive_manager.drives if isinstance(d, DropboxService) and d.service]
        for dbx_instance in dbx_accounts:
             token = None;
             if hasattr(dbx_instance.service, 'session'): token = dbx_instance.service.session.access_token
             elif hasattr(dbx_instance.service, '_oauth2_access_token'): token = dbx_instance.service._oauth2_access_token
             if not token: logger.warning(f"Skipping DBX Bucket {dbx_instance.bucket_number}: No token."); continue
             dbx_handler = DropBoxFile(token, drive_manager); dbx_api_path = dbx_handler.search_file(file_name) # Assumes returns path_lower or None
             if dbx_api_path:
                 user_dl_path = os.path.join(download_dir, str(user_id)); os.makedirs(user_dl_path, exist_ok=True); local_path = os.path.join(user_dl_path, os.path.basename(dbx_api_path))
                 downloaded_path = dbx_handler.download_file(dbx_api_path, local_path) # Assumes downloads to local path
                 if downloaded_path and os.path.exists(downloaded_path):
                     mime, _ = mimetypes.guess_type(downloaded_path); fname=os.path.basename(downloaded_path); logger.info(f"Returning Dropbox file: '{fname}'"); return FileResponse(path=downloaded_path, filename=fname, media_type=mime or "application/octet-stream", headers={"Content-Disposition": f"attachment; filename=\"{fname}\""})
                 else: logger.error(f"Dropbox download found but failed for {local_path}"); break # Stop if found but failed download
    except Exception as e: logger.error(f"Dropbox download check failed: {e}", exc_info=True)
    logger.warning(f"File '{file_name}' not found for download by {username}.")
    raise HTTPException(status_code=404, detail=f"File '{file_name}' not found.")

# --- LLM Endpoints (Keep as is, ensure FileInfo model is correctly used for extraction) ---
def _get_drive_service_instance(drive_manager: DriveManager, provider: str, bucket: int) -> Optional[object]: # Keep as is
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
    file_metadata_context = ""; extracted_snippets_context = ""; relevant_files: List[FileInfo] = [] # Use Pydantic model
    if not search_query: file_metadata_context = "\n(Note: Could not find keywords.)"
    else:
        logger.info(f"Using keywords: '{search_query}'");
        try:
            drive_manager = DriveManager(user_id=user_id); raw_files = drive_manager.search_files_for_llm(query=search_query, limit_per_drive=5, total_limit=10)
            if raw_files:
                parsed_files = []
                for data in raw_files:
                    try: parsed_files.append(FileInfo(**data)); # Convert dict to FileInfo
                    except Exception as e: logger.warning(f"Skipping file data, parse error: {e}. Data: {data}")
                relevant_files = parsed_files # Assign the list of FileInfo objects
                file_lines = ["Found relevant files:"];
                if relevant_files: file_lines.extend([f"- {f.name} ({f.provider})" for f in relevant_files])
                if len(file_lines)>1: file_metadata_context = "\n".join(file_lines); logger.info("Got metadata.")
                else: file_metadata_context = "\n(Note: No valid files found.)"
            else: file_metadata_context = "\n(Note: No files found matching keywords.)"

            if relevant_files: # Now relevant_files contains FileInfo objects
                seen_identifiers = set(); unique_files = []
                for file in relevant_files: # Iterate through FileInfo objects
                    identifier = f"{file.provider}:{file.id or file.path_lower}";
                    if identifier not in seen_identifiers: unique_files.append(file); seen_identifiers.add(identifier)

                MAX_EXTRACT=5; count=0; files_to_extract: List[FileInfo]=[]
                for file in unique_files:
                    if count >= MAX_EXTRACT: break
                    if file.name and os.path.splitext(file.name)[1].lower() in SUPPORTED_TEXT_EXTENSIONS: files_to_extract.append(file); count += 1

                if files_to_extract:
                    logger.info(f"Attempting extraction from (up to {MAX_EXTRACT}): {[f.name for f in files_to_extract]}")
                    snippet_lines = ["\n\nExtracted Content Snippets:"]; MAX_LEN=2500; TOTAL_MAX=8000; total_len=0
                    gdrive_handler = GoogleDriveFile(drive_manager)

                    for file in files_to_extract: # Iterate through FileInfo again
                        if total_len >= TOTAL_MAX: logger.warning("Max snippet length reached."); snippet_lines.append("\n(More snippets omitted...)"); break
                        extracted = None; buffer = None
                        try:
                            if file.provider == "GoogleDrive" and file.id and file.bucket:
                                service = _get_drive_service_instance(drive_manager, "GoogleDrive", file.bucket)
                                if service: buffer = gdrive_handler.download_file_content_by_id(service, file.id, file.size)
                                if buffer: extracted = gdrive_handler.extract_text_from_content(buffer, file.name, file.mimeType)
                            elif file.provider == "Dropbox" and file.path_lower and file.access_token: # Need access_token from FileInfo
                                 dbx_handler = DropBoxFile(file.access_token, drive_manager) # Instantiate with token from FileInfo
                                 buffer = dbx_handler.download_file_content_by_path(file.path_lower)
                                 if buffer: extracted = dbx_handler.extract_text_from_content(buffer, file.name)
                        except Exception as ex_err: logger.error(f"Extract error {file.name}: {ex_err}", exc_info=True)
                        finally:
                             if buffer:
                                 try: buffer.close()
                                 except: pass
                        if extracted: snippet = extracted[:MAX_LEN] + ("..." if len(extracted) > MAX_LEN else ""); snippet_lines.extend([f"\n--- Snippet: {file.name} ---", snippet, f"--- End: {file.name} ---"]); total_len += len(snippet)
                        else: snippet_lines.append(f"\n(Could not extract text from {file.name})")
                    if len(snippet_lines) > 1: extracted_snippets_context = "\n".join(snippet_lines); logger.info("Generated snippets context.")

        except Exception as e: logger.error(f"File search/extract error: {e}", exc_info=True); file_metadata_context = "\n(Note: Error getting file context.)"; extracted_snippets_context = ""

    # Prepare and Call Final LLM (Keep as is)
    memory = session_memory.get(telegram_user_id, []); system_prompt = (...); full_messages = [...] # Keep full logic
    system_prompt = (
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
        completion = await asyncio.to_thread(client.chat.completions.create, model="llama-3.3-70b-versatile", messages=full_messages, temperature=0.7) # Corrected Llama 3.1 model name
        response_text = completion.choices[0].message.content.strip(); logger.info(f"Groq answer received.")
        current_memory = session_memory[telegram_user_id]; current_memory.append({"role": "user", "content": original_question}); current_memory.append({"role": "assistant", "content": response_text})
        session_memory[telegram_user_id] = current_memory[-MAX_MEMORY:]; return {"response": response_text}
    except Exception as e: logger.error(f"Groq call failed: {e}", exc_info=True); raise HTTPException(status_code=503, detail=f"LLM request failed: {e}")

@app.post("/llm/reset", tags=["LLM"])
async def reset_llm_memory(request_data: ResetRequest): # Keep as is
    if not request_data.user_id: raise HTTPException(status_code=400, detail="Missing user_id")
    logger.info(f"Resetting memory for TG ID: {request_data.user_id}")
    session_memory.pop(request_data.user_id, None); return {"message": f"Memory reset for user {request_data.user_id}"}

# --- Main Application Runner ---
if __name__ == "__main__":
    import uvicorn
    # Startup event handles index setup
    port = int(os.getenv("PORT", 8000)); host = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Starting Syncly API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)

# --- END OF FILE api.py ---