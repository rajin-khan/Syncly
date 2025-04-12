import asyncio
import base64
import hashlib
import json
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Query
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
from typing import List, Optional
from fastapi.responses import FileResponse
from Database import Database
from GoogleDrive import GoogleDrive
from Dropbox import DropboxService
from GDriveFile import GoogleDriveFile
from DropBoxFile import DropBoxFile

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("syncly-api")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 240

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Pydantic models
class User(BaseModel):
    username: str
    password: str
    email: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None

class StorageInfo(BaseModel):
    provider: str
    drive_number: int
    storage_limit_gb: float
    used_storage_gb: float
    free_storage_gb: float

class StorageSummary(BaseModel):
    storages: List[StorageInfo]
    total_storage_gb: float
    used_storage_gb: float
    free_storage_gb: float

class FileInfo(BaseModel):
    name: str
    provider: str
    size: str
    path: str

class AddDriveRequest(BaseModel):
    drive_type: str

# Helper functions
def get_password_hash(password: str) -> str:
    """Hash password using SHA256 and encode with base64"""
    sha256_hash = hashlib.sha256(password.encode('utf-8')).digest()
    return base64.b64encode(sha256_hash).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password by hashing input and comparing with stored base64 hash"""
    input_hash = get_password_hash(plain_password)
    return input_hash == hashed_password

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    db = Database().get_instance()
    user = db.users_collection.find_one({"username": token_data.username})
    if user is None:
        raise credentials_exception
    return user

# Register endpoint
@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: User):
    db = Database().get_instance()
    if db.users_collection.find_one({"username": user.username}):
        raise HTTPException(status_code=400, detail="Username already exists")

    if db.users_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already exists")

    hashed_password = get_password_hash(user.password)
    db.users_collection.insert_one({
        "username": user.username,
        "password": hashed_password,
        "email": user.email,
        "drives": []
    })
    logger.info(f"User {user.username} registered successfully")
    return {"message": "User registered successfully"}

# Login endpoint
@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = Database().get_instance()
    logger.info(f"Login attempt for username: {form_data.username}")
    
    user = db.users_collection.find_one({"username": form_data.username})
    if not user:
        logger.error(f"User not found: {form_data.username}")
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    hashed_input = get_password_hash(form_data.password)
    logger.info(f"Input hash (base64): {hashed_input}")
    logger.info(f"Stored hash (base64): {user['password']}")
    if user["password"] != hashed_input:
        logger.error("Password mismatch")
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    logger.info(f"Login successful for {form_data.username}")
    return {"access_token": access_token, "token_type": "bearer"}

# New endpoint: Complete Telegram login
@app.post("/complete-login", tags=["Auth"])
async def complete_login(
    code: str = Query(..., description="Login code from Telegram"),
    telegram_id: str = Query(..., description="Telegram user ID"),
    token: str = Depends(oauth2_scheme)
):
    db = Database().get_instance()
    if not db.client:
        logger.error("Database connection unavailable")
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            logger.error("No username in token")
            raise HTTPException(status_code=401, detail="Invalid token")

        expires_at = datetime.utcnow() + timedelta(minutes=5)
        result = db.login_sessions_collection.update_one(
            {"code": code},
            {
                "$set": {
                    "telegram_id": telegram_id,
                    "jwt": token,
                    "username": username,
                    "expires": expires_at
                }
            },
            upsert=True
        )
        logger.info(f"Login completed for {username} with code {code}, modified: {result.modified_count}, upserted: {result.upserted_id}")
        return {"message": "Login completed successfully"}
    except JWTError:
        logger.error("JWT decoding failed")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Error completing login: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# New endpoint: Check Telegram login status
@app.get("/check-login", tags=["Auth"])
async def check_login(code: str = Query(...), telegram_id: str = Query(...)):
    db = Database().get_instance()
    if not db.client:
        logger.error("Database connection unavailable")
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    session = db.login_sessions_collection.find_one({"code": code})
    if not session or session["telegram_id"] != telegram_id or session["expires"] < datetime.utcnow():
        if session and session["expires"] < datetime.utcnow():
            db.login_sessions_collection.delete_one({"code": code})
            logger.info(f"Deleted expired session for code {code}")
        logger.info(f"No valid session found for code {code} and telegram_id {telegram_id}")
        raise HTTPException(status_code=404, detail="Login code invalid or expired")
    
    response = {"jwt": session["jwt"], "username": session["username"]}
    db.login_sessions_collection.delete_one({"code": code})
    logger.info(f"Session retrieved and deleted for code {code}")
    return response

@app.post("/validate-token", tags=["Auth"])
async def validate_token(token: str = Query(..., description="JWT token to validate")):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token: No username found")
        return {"username": username}
    except JWTError as e:
        logger.error(f"JWT decoding failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/protected")
async def protected_route(current_user: dict = Depends(get_current_user)):
    return {"message": f"Hello, {current_user['username']}! You are authenticated."}

@app.get("/storage", response_model=StorageSummary, tags=["Storage"])
async def get_storage_info(current_user: dict = Depends(get_current_user)):
    drive_manager = DriveManager(user_id=str(current_user["_id"]), token_dir="tokens")
    logger.info(f"Loading drives for user {current_user['username']} (ID: {current_user['_id']})")
    drive_manager.load_user_drives()
    logger.info(f"Drives loaded: {[type(drive).__name__ for drive in drive_manager.drives]}")
    storages_info, total_limit, total_usage = drive_manager.check_all_storages()

    logger.info(f"Storage info: {storages_info}")
    logger.info(f"Total limit: {total_limit} bytes, Total usage: {total_usage} bytes")

    return {
        "storages": [
            {
                "provider": storage["Provider"],
                "drive_number": storage["Drive Number"],
                "storage_limit_gb": storage["Storage Limit (bytes)"],
                "used_storage_gb": storage["Used Storage (bytes)"],
                "free_storage_gb": storage["Free Storage"]
            } for storage in storages_info
        ],
        "total_storage_gb": round(total_limit / 1024**3, 2),
        "used_storage_gb": round(total_usage / 1024**3, 2),
        "free_storage_gb": round((total_limit - total_usage) / 1024**3, 2)
    }

@app.post("/drives", tags=["Storage"])
async def add_drive(request: AddDriveRequest, current_user: dict = Depends(get_current_user)):
    drive_manager = DriveManager(user_id=current_user["_id"])
    bucket_number = len(drive_manager.get_all_authenticated_buckets()) + 1
    
    try:
        if request.drive_type == "GoogleDrive":
            google_drive_instance = GoogleDrive()
            drive_manager.add_drive(google_drive_instance, bucket_number, drive_type="GoogleDrive")
            return {"status": "success", "message": f"Google Drive bucket {bucket_number} added successfully"}
        
        elif request.drive_type == "Dropbox":
            dropbox_service_instance = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
            
            async def authenticate_dropbox():
                try:
                    drive_manager.add_drive(dropbox_service_instance, bucket_number, drive_type="Dropbox")
                    return {"status": "success", "message": f"Dropbox bucket {bucket_number} added successfully"}
                except Exception as e:
                    logger.error(f"Failed to authenticate Dropbox: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Failed to add Dropbox: {str(e)}")
            
            task = asyncio.create_task(authenticate_dropbox())
            for _ in range(60):
                if task.done():
                    return await task
                await asyncio.sleep(1)
            
            task.cancel()
            raise HTTPException(status_code=408, detail="Dropbox authentication timed out. Please complete authorization in the browser.")
        
        else:
            raise HTTPException(status_code=400, detail="Invalid drive type. Choose 'GoogleDrive' or 'Dropbox'")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to add drive: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add drive: {str(e)}")


@app.get("/viewfiles", response_model=List[FileInfo], tags=["Files"])
async def list_files(
    query: Optional[str] = None,
    limit: Optional[int] = Query(50, description="Number of files to retrieve per page (default: 50)"),
    offset: Optional[int] = Query(0, description="Offset for pagination (default: 0)"),
    current_user: dict = Depends(get_current_user)
):
    try:
        drive_manager = DriveManager(user_id=str(current_user["_id"]), token_dir="tokens")
        logger.info(f"Loading drives for user {current_user['username']} (ID: {current_user['_id']}) to list files")
        drive_manager.load_user_drives()
        logger.info(f"Drives loaded: {[type(drive).__name__ for drive in drive_manager.drives]}")
        
        if not drive_manager.drives:
            logger.warning("No authenticated drives found for user")
            raise HTTPException(status_code=400, detail="No authenticated drives found. Please add a bucket first.")
        
        all_files = []
        seen_file_ids = set()  # Use IDs for deduplication
        
        for drive in drive_manager.drives:
            try:
                files = drive.listFiles(query=query)
                logger.info(f"Retrieved {len(files)} files from {type(drive).__name__}: {[f['name'] for f in files]}")
                for file in files:
                    file_id = file.get("id", file.get("name", "Unknown"))  # Fallback to name if no ID
                    if file_id not in seen_file_ids:
                        size = file.get("size", "Unknown")
                        if isinstance(size, (int, float)):
                            size = str(size)
                        all_files.append({
                            "name": file.get("name", "Unknown"),
                            "provider": file.get("provider", type(drive).__name__),
                            "size": size,
                            "path": file.get("path", "N/A")
                        })
                        seen_file_ids.add(file_id)
            except Exception as e:
                logger.error(f"Error retrieving files from {type(drive).__name__}: {e}")
        
        all_files.sort(key=lambda x: x["name"])
        total_files = len(all_files)
        paginated_files = all_files[offset:offset + limit]
        
        logger.info(f"Returning {len(paginated_files)} files (offset: {offset}, limit: {limit}) out of {total_files} total for user {current_user['username']}")
        return paginated_files
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

@app.get("/search_files", response_model=List[FileInfo], tags=["Files"])
async def search_files(
    query: str = Query(..., description="Filename to search for"),
    limit: int = Query(10, description="Number of matching files to return (default: 10)"),
    exact_match: bool = Query(False, description="Require exact filename match (default: contains)"),
    current_user: dict = Depends(get_current_user)
):
    try:
        drive_manager = DriveManager(user_id=str(current_user["_id"]))
        logger.info(f"User {current_user['username']} (ID: {str(current_user['_id'])}) searching for '{query}' with limit {limit}, exact_match={exact_match}")
        drive_manager.load_user_drives()  # Ensure drives are loaded
        
        if not drive_manager.drives:
            logger.warning("No authenticated drives found for user")
            raise HTTPException(status_code=400, detail="No authenticated drives found. Please add a bucket first.")

        matching_files = []
        seen_file_ids = set()  # Deduplicate by file ID
        
        for drive in drive_manager.drives:
            try:
                # Use exact match in query if required
                query_str = query if not exact_match else f"'{query}'"  # Exact match needs quotes for Google Drive
                files = drive.listFiles(query=query_str)
                logger.info(f"Retrieved {len(files)} files from {type(drive).__name__} for query '{query_str}'")
                for file in files:
                    file_id = file.get("id", file.get("name", "Unknown"))
                    file_name = file.get("name", "Unknown")
                    if file_id in seen_file_ids:
                        continue
                    # Additional check for exact match if service doesn't support it
                    if exact_match and file_name != query:
                        continue
                    size = file.get("size", "Unknown")
                    if isinstance(size, (int, float)):
                        size = str(size)
                    file_info = {
                        "name": file_name,
                        "provider": file.get("provider", type(drive).__name__),
                        "size": size,
                        "path": file.get("path", "N/A")
                    }
                    matching_files.append(file_info)
                    seen_file_ids.add(file_id)
                    if len(matching_files) >= limit:
                        break
                if len(matching_files) >= limit:
                    break
            except Exception as e:
                logger.error(f"Error retrieving files from {type(drive).__name__}: {e}")

        logger.info(f"Returning {len(matching_files)} matching files for query '{query}' for user {current_user['username']}")
        return matching_files
    except Exception as e:
        logger.error(f"Error searching files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching files: {str(e)}")

@app.post("/files/upload", tags=["Files"])
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    os.makedirs("uploads", exist_ok=True)
    file_location = f"uploads/{file.filename}"
    with open(file_location, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    drive_manager = DriveManager(user_id=str(current_user["_id"]))
    logger.info(f"Loading drives for user {current_user['username']} (ID: {current_user['_id']}) for upload")
    drive_manager.load_user_drives()  # Ensure drives are loaded
    
    authenticated_buckets = drive_manager.get_all_authenticated_buckets()
    if not authenticated_buckets:
        os.remove(file_location)
        raise HTTPException(status_code=400, detail="No authenticated drives found. Please add a drive first.")
    
    storages_info, total_limit, total_usage = drive_manager.check_all_storages()
    sorted_buckets = drive_manager.get_sorted_buckets()
    if not sorted_buckets:
        os.remove(file_location)
        raise HTTPException(status_code=400, detail="No available storage with free space")
    
    best_bucket = sorted_buckets[0][1]
    bucket_number = sorted_buckets[0][2]
    
    try:
        if isinstance(best_bucket, DropboxService):
            access_token = best_bucket.service._oauth2_access_token
            dropbox_file = DropBoxFile(access_token, drive_manager)
            dropbox_file.upload_file(file_location, file.filename)
            provider = "Dropbox"
        elif isinstance(best_bucket, GoogleDrive):
            gdrive_file = GoogleDriveFile(drive_manager)
            gdrive_file.upload_file(file_location, file.filename, "application/octet-stream")
            provider = "Google Drive"
        else:
            os.remove(file_location)
            raise HTTPException(status_code=400, detail=f"Unsupported drive type: {type(best_bucket).__name__}")
        
        os.remove(file_location)
        return {"status": "success", "message": f"File '{file.filename}' uploaded to {provider} (Bucket {bucket_number + 1})"}
    
    except Exception as e:
        if os.path.exists(file_location):
            os.remove(file_location)
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/files/download", tags=["Files"])
async def download_file(
    file_name: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        drive_manager = DriveManager(user_id=str(current_user["_id"]), token_dir="tokens")
        logger.info(f"Loading drives for user {current_user['username']} (ID: {current_user['_id']}) to download '{file_name}'")
        drive_manager.load_user_drives()  # Ensure drives are loaded
        
        if not drive_manager.drives:
            logger.warning("No authenticated drives found for user")
            raise HTTPException(status_code=400, detail="No authenticated drives found. Please add a drive first.")
        
        # Common file extensions to try
        common_extensions = ['.jpg', '.pdf', '.png', '.txt', '.csv', '.docx', '.xlsx', '.java', '.py']
        search_names = [file_name] + [f"{file_name}{ext}" for ext in common_extensions]
        
        downloaded_file = None
        for search_name in search_names:
            logger.info(f"Searching for file '{search_name}' across all drives")
            for drive in drive_manager.drives:
                try:
                    if isinstance(drive, GoogleDrive):
                        google_drive_file = GoogleDriveFile(drive_manager)
                        downloaded_file = google_drive_file.download_from_all_buckets(search_name, "downloads")
                        if downloaded_file:
                            logger.info(f"File '{search_name}' found and downloaded from Google Drive")
                            break
                    elif isinstance(drive, DropboxService):
                        access_token = drive.service._oauth2_access_token
                        dropbox_file = DropBoxFile(access_token, drive_manager)
                        dropbox_file_path = dropbox_file.search_file(search_name)
                        if dropbox_file_path:
                            save_file_path = os.path.join("downloads", os.path.basename(dropbox_file_path))
                            dropbox_file.download_file(dropbox_file_path, save_file_path)
                            downloaded_file = save_file_path
                            logger.info(f"File '{search_name}' found and downloaded from Dropbox")
                            break
                except Exception as e:
                    logger.error(f"Error searching '{search_name}' in {type(drive).__name__}: {str(e)}")
                    continue
            if downloaded_file:
                break
        
        if downloaded_file and os.path.exists(downloaded_file):
            mime_type, _ = mimetypes.guess_type(downloaded_file)
            if not mime_type:
                mime_type = "application/octet-stream"
            logger.info(f"Returning file '{downloaded_file}' with MIME type '{mime_type}'")
            return FileResponse(
                path=downloaded_file,
                filename=os.path.basename(downloaded_file),
                media_type=mime_type
            )
        
        logger.warning(f"File '{file_name}' not found in any connected storage")
        raise HTTPException(status_code=404, detail=f"File '{file_name}' not found in any connected storage")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file '{file_name}': {str(e)}")
        if downloaded_file and os.path.exists(downloaded_file):
            os.remove(downloaded_file)
            logger.info(f"Cleaned up temporary file '{downloaded_file}'")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)