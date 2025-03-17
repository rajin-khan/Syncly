from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pymongo import MongoClient
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import os
from AuthManager import AuthManager
from DriveManager import DriveManager
from fastapi.staticfiles import StaticFiles
from fastapi import HTTPException
from fastapi import Query

import shutil
from bson import ObjectId
import logging
import mimetypes
from typing import List, Optional


from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
import shutil
from bson import ObjectId
import logging
import mimetypes
import dropbox

from Database import Database
from DriveManager import DriveManager
from GoogleDrive import GoogleDrive
from Dropbox import DropboxService
from GDriveFile import GoogleDriveFile
from DropBoxFile import DropBoxFile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("syncly-api")

# FastAPI app
app = FastAPI()

# Add this line after creating the FastAPI app
app.mount("/static", StaticFiles(directory="static"), name="static")

# MongoDB connection
client = MongoClient("mongodb://localhost:27017/")
db = client["Syncly"]
users_collection = db["users"]

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
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
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
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

    user = users_collection.find_one({"username": token_data.username})
    if user is None:
        raise credentials_exception
    return user

# Routes
@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: User):
    if users_collection.find_one({"username": user.username}):
        raise HTTPException(status_code=400, detail="Username already exists")

    if users_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already exists")

    hashed_password = get_password_hash(user.password)
    users_collection.insert_one({
        "username": user.username,
        "password": hashed_password,
        "email": user.email,
        "drives": []  # Initialize an empty drives list
    })
    return {"message": "User registered successfully"}

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_collection.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )

    # Log the token for debugging
    print("Generated JWT:", access_token)

    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/protected")
async def protected_route(current_user: dict = Depends(get_current_user)):
    return {"message": f"Hello, {current_user['username']}! You are authenticated."}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    file_location = f"uploads/{file.filename}"
    with open(file_location, "wb") as buffer:
        buffer.write(file.file.read())
    return {"message": f"File '{file.filename}' uploaded successfully"}

@app.post("/validate-token")
async def validate_token(token: str = Query(..., description="The JWT token to validate")):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("JWT payload:", payload)  # Log the payload for debugging
        return {"username": payload.get("sub")}
    except JWTError as e:
        print("JWT validation error:", e)  # Log the error for debugging
        raise HTTPException(status_code=401, detail="Invalid token")

# Integrated functionality from the old API
@app.get("/storage", response_model=StorageSummary, tags=["Storage"])
async def get_storage_info(current_user: dict = Depends(get_current_user)):
    """Get storage information for all connected drives."""
    drive_manager = DriveManager(user_id=current_user["_id"])
    storages_info, total_limit, total_usage = drive_manager.check_all_storages()
    
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
async def add_drive(
    request: AddDriveRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a new storage drive."""
    drive_manager = DriveManager(user_id=current_user["_id"])
    
    try:
        bucket_number = len(drive_manager.get_all_authenticated_buckets()) + 1
        
        if request.drive_type == "GoogleDrive":
            google_drive_instance = GoogleDrive()
            drive_manager.add_drive(google_drive_instance, bucket_number, drive_type="GoogleDrive")
            return {"status": "success", "message": f"Google Drive bucket {bucket_number} added successfully"}
            
        elif request.drive_type == "Dropbox":
            dropbox_service_instance = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
            auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(dropbox_service_instance.app_key, dropbox_service_instance.app_secret)
            authorize_url = auth_flow.start()
            print(f"Please visit this URL to authorize Dropbox: {authorize_url}")
            auth_code = input("Enter the authorization code: ").strip()
            oauth_result = auth_flow.finish(auth_code)
            access_token = oauth_result.access_token
            
            db.tokens_collection.update_one(
                {"user_id": current_user["_id"], "bucket_number": bucket_number, "service_type": "Dropbox"},
                {"$set": {"access_token": access_token}},
                upsert=True
            )
            
            drive_manager.add_drive(dropbox_service_instance, bucket_number, drive_type="Dropbox")
            return {"status": "success", "message": f"Dropbox bucket {bucket_number} added successfully"}
            
        else:
            raise HTTPException(status_code=400, detail="Invalid drive type. Choose 'GoogleDrive' or 'Dropbox'")
            
    except Exception as e:
        logger.error(f"Failed to add drive: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add drive: {str(e)}")

@app.get("/files", response_model=List[FileInfo], tags=["Files"])
async def list_files(
    query: Optional[str] = None,
    limit: Optional[int] = Query(10, description="Number of files to retrieve (default: 10)"),
    current_user: dict = Depends(get_current_user)
):
    """List files from all connected drives with optional search and limit."""
    try:
        drive_manager = DriveManager(user_id=current_user["_id"])
        all_files = []
        seen_files = set()
        
        for drive in drive_manager.drives:
            try:
                files = drive.listFiles(query=query)
                for file in files:
                    file_name = file.get("name", "Unknown")
                    if file_name not in seen_files:
                        all_files.append({
                            "name": file_name,
                            "provider": file.get("provider", "Unknown"),
                            "size": file.get("size", "Unknown"),
                            "path": file.get("path", "N/A")
                        })
                        seen_files.add(file_name)
                        
                        if len(all_files) >= limit:
                            break
                if len(all_files) >= limit:
                    break
            except Exception as e:
                logger.error(f"Error retrieving files from {type(drive).__name__}: {e}")
        
        all_files.sort(key=lambda x: x["name"])
        return all_files
    
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

@app.post("/files/upload", tags=["Files"])
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload a file to the best available cloud storage."""
    file_location = f"uploads/{file.filename}"
    with open(file_location, "wb") as buffer:
        buffer.write(file.file.read())
    
    drive_manager = DriveManager(user_id=current_user["_id"])
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
    """Download a file from any connected drive."""
    try:
        drive_manager = DriveManager(user_id=current_user["_id"])
        google_drive_file = GoogleDriveFile(drive_manager)
        downloaded_file = google_drive_file.download_from_all_buckets(file_name, "downloads")
        
        if downloaded_file:
            mime_type, _ = mimetypes.guess_type(downloaded_file)
            if not mime_type:
                mime_type = "application/octet-stream"
            
            return FileResponse(
                path=downloaded_file,
                filename=os.path.basename(downloaded_file),
                media_type=mime_type
            )
        
        dropbox_accounts = [drive for drive in drive_manager.drives if isinstance(drive, DropboxService)]
        for dropbox_service in dropbox_accounts:
            access_token = dropbox_service.service._oauth2_access_token
            dropbox_file = DropBoxFile(access_token, drive_manager)
            dropbox_file_path = dropbox_file.search_file(file_name)
            if dropbox_file_path:
                save_file_path = os.path.join("downloads", os.path.basename(dropbox_file_path))
                dropbox_file.download_file(dropbox_file_path, save_file_path)
                
                mime_type, _ = mimetypes.guess_type(save_file_path)
                if not mime_type:
                    mime_type = "application/octet-stream"
                
                return FileResponse(
                    path=save_file_path,
                    filename=os.path.basename(save_file_path),
                    media_type=mime_type
                )
        
        raise HTTPException(status_code=404, detail=f"File '{file_name}' not found in any connected storage")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

# Run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)