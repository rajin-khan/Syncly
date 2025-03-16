from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Query, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
import shutil
from bson import ObjectId
import logging
import mimetypes
import hashlib
import dropbox

from Database import Database
from DriveManager import DriveManager
from GoogleDrive import GoogleDrive
from Dropbox import DropboxService
from GDriveFile import GoogleDriveFile
from DropBoxFile import DropBoxFile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("syncly-api")

app = FastAPI(
    title="Syncly API",
    description="API for managing cloud storage across multiple providers",
    version="1.0.0"
)

# Configure CORS to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload directory exists
UPLOAD_FOLDER = "uploads"
DOWNLOAD_FOLDER = "downloads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Database initialization
db_instance = Database().get_instance()

### Pydantic Models ###
class UserAuth(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    user_id: str
    username: str

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
    drive_type: str = Field(..., description="Type of drive to add (GoogleDrive or Dropbox)")

### AuthManager ###
class AuthManager:
    def __init__(self):
        self.db = db_instance

    def register_user(self, username: str, password: str):
        """Register a new user."""
        if self.db.users_collection.find_one({"username": username}):
            raise HTTPException(status_code=400, detail="Username already exists.")
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        user_id = self.db.users_collection.insert_one({
            "username": username,
            "password": hashed_password,
            "drives": []
        }).inserted_id
        return {"message": "User registered successfully", "user_id": str(user_id)}

    def login_user(self, username: str, password: str):
        """Log in an existing user."""
        user = self.db.users_collection.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=401, detail="User not found.")
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        if user["password"] != hashed_password:
            raise HTTPException(status_code=401, detail="Incorrect password.")
        return {"message": "User logged in successfully", "user_id": str(user["_id"])}

### Helper Functions ###
def validate_user_id(user_id: str) -> ObjectId:
    """Validate and convert user_id string to ObjectId."""
    try:
        obj_id = ObjectId(user_id)
        if not db_instance.users_collection.find_one({"_id": obj_id}):
            raise HTTPException(status_code=401, detail="Invalid user ID")
        return obj_id
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

### Authentication Dependency ###
async def get_user_id(user_id: str = Query(..., description="User ID for authentication")):
    return validate_user_id(user_id)

### Routes ###
@app.get("/", tags=["Status"])
async def root():
    """Check if the API is running."""
    return {"status": "success", "message": "Syncly API is running"}

@app.post("/auth/register", response_model=UserResponse, tags=["Authentication"])
async def register_user(user: UserAuth):
    """Register a new user."""
    auth_manager = AuthManager()
    result = auth_manager.register_user(user.username, user.password)
    return {"user_id": result["user_id"], "username": user.username}

@app.post("/auth/login", response_model=UserResponse, tags=["Authentication"])
async def login_user(user: UserAuth):
    """Log in an existing user."""
    auth_manager = AuthManager()
    result = auth_manager.login_user(user.username, user.password)
    return {"user_id": result["user_id"], "username": user.username}

@app.get("/storage", response_model=StorageSummary, tags=["Storage"])
async def get_storage_info(user_id: ObjectId = Depends(get_user_id)):
    """Get storage information for all connected drives."""
    drive_manager = DriveManager(user_id=user_id)
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
    user_id: ObjectId = Depends(get_user_id)
):
    """Add a new storage drive."""
    drive_manager = DriveManager(user_id=user_id)
    
    try:
        bucket_number = len(drive_manager.get_all_authenticated_buckets()) + 1
        
        if request.drive_type == "GoogleDrive":
            google_drive_instance = GoogleDrive()
            drive_manager.add_drive(google_drive_instance, bucket_number, drive_type="GoogleDrive")
            return {"status": "success", "message": f"Google Drive bucket {bucket_number} added successfully"}
            
        elif request.drive_type == "Dropbox":
            # Initialize DropboxService with app credentials
            dropbox_service_instance = DropboxService(token_dir="tokens", app_key="w84emdpux17qpnj", app_secret="x6ce7dtmj51xqc7")
            
            # Start the OAuth flow (no redirect, server handles it)
            auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(dropbox_service_instance.app_key, dropbox_service_instance.app_secret)
            authorize_url = auth_flow.start()
            
            # Automatically complete the OAuth flow (server-side)
            print(f"Please visit this URL to authorize Dropbox: {authorize_url}")
            auth_code = input("Enter the authorization code: ").strip()
            
            # Finish the OAuth flow and get the access token
            oauth_result = auth_flow.finish(auth_code)
            access_token = oauth_result.access_token
            
            # Store the access token in the database
            db_instance.tokens_collection.update_one(
                {"user_id": user_id, "bucket_number": bucket_number, "service_type": "Dropbox"},
                {"$set": {"access_token": access_token}},
                upsert=True
            )
            
            # Add the Dropbox drive to the DriveManager
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
    user_id: ObjectId = Depends(get_user_id)
):
    """List files from all connected drives with optional search and limit."""
    try:
        drive_manager = DriveManager(user_id=user_id)
        
        all_files = []
        seen_files = set()
        
        # Collect files from all drives
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
                        
                        # Stop if we've reached the limit
                        if len(all_files) >= limit:
                            break
                if len(all_files) >= limit:
                    break
            except Exception as e:
                logger.error(f"Error retrieving files from {type(drive).__name__}: {e}")
        
        # Sort files by name
        all_files.sort(key=lambda x: x["name"])
        return all_files
    
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

@app.post("/files/upload", tags=["Files"])
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(...),
):
    """Upload a file to the best available cloud storage."""
    obj_id = validate_user_id(user_id)
    
    try:
        # Save uploaded file temporarily
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Initialize DriveManager with the correct user_id and token_dir
        drive_manager = DriveManager(user_id=obj_id, token_dir="tokens")
        
        # Check if drives are authenticated
        authenticated_buckets = drive_manager.get_all_authenticated_buckets()
        if not authenticated_buckets:
            os.remove(file_path)  # Clean up temp file
            raise HTTPException(status_code=400, detail="No authenticated drives found. Please add a drive first.")
        
        # Log authenticated buckets
        logger.info(f"Authenticated buckets: {authenticated_buckets}")
        
        # Get storage information for all drives
        storages_info, total_limit, total_usage = drive_manager.check_all_storages()
        logger.info(f"Storage information: {storages_info}")
        
        # Get sorted buckets (drives with free space)
        sorted_buckets = drive_manager.get_sorted_buckets()
        logger.info(f"Sorted buckets: {sorted_buckets}")
        
        if not sorted_buckets:
            os.remove(file_path)  # Clean up temp file
            raise HTTPException(status_code=400, detail="No available storage with free space")
        
        # Select the best bucket (drive with the most free space)
        best_bucket = sorted_buckets[0][1]  # Get the drive instance
        bucket_number = sorted_buckets[0][2]  # Get the bucket number
        logger.info(f"Selected best bucket: {type(best_bucket).__name__} (Bucket {bucket_number})")
        
        # Upload to the best available storage
        try:
            if isinstance(best_bucket, DropboxService):
                access_token = best_bucket.service._oauth2_access_token
                dropbox_file = DropBoxFile(access_token, drive_manager)
                dropbox_file.upload_file(file_path, file.filename)
                provider = "Dropbox"
                
            elif isinstance(best_bucket, GoogleDrive):
                gdrive_file = GoogleDriveFile(drive_manager)
                gdrive_file.upload_file(file_path, file.filename, "application/octet-stream")
                provider = "Google Drive"
                
            else:
                os.remove(file_path)  # Clean up temp file
                raise HTTPException(status_code=400, detail=f"Unsupported drive type: {type(best_bucket).__name__}")
                
            # Clean up temp file
            os.remove(file_path)
            
            return {
                "status": "success", 
                "message": f"File '{file.filename}' uploaded to {provider} (Bucket {bucket_number + 1})"
            }
            
        except Exception as e:
            # Clean up temp file in case of error
            if os.path.exists(file_path):
                os.remove(file_path)
            logger.error(f"Error uploading file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in upload process: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload process failed: {str(e)}")
    finally:
        # Ensure the temporary file is cleaned up
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Temporary file {file_path} cleaned up.")

@app.get("/files/download", tags=["Files"])
async def download_file(
    file_name: str,
    user_id: ObjectId = Depends(get_user_id)
):
    """Download a file from any connected drive."""
    try:
        drive_manager = DriveManager(user_id=user_id)
        
        # Try to find and download the file from Google Drive first
        google_drive_file = GoogleDriveFile(drive_manager)
        downloaded_file = google_drive_file.download_from_all_buckets(file_name, DOWNLOAD_FOLDER)
        
        if downloaded_file:
            # Determine the MIME type based on the file extension
            mime_type, _ = mimetypes.guess_type(downloaded_file)
            if not mime_type:
                mime_type = "application/octet-stream"  # Fallback for unknown types
            
            return FileResponse(
                path=downloaded_file,
                filename=os.path.basename(downloaded_file),
                media_type=mime_type
            )
        
        # If not found in Google Drive, try Dropbox
        dropbox_accounts = [drive for drive in drive_manager.drives if isinstance(drive, DropboxService)]
        
        for dropbox_service in dropbox_accounts:
            access_token = dropbox_service.service._oauth2_access_token
            dropbox_file = DropBoxFile(access_token, drive_manager)
            
            dropbox_file_path = dropbox_file.search_file(file_name)
            if dropbox_file_path:
                save_file_path = os.path.join(DOWNLOAD_FOLDER, os.path.basename(dropbox_file_path))
                dropbox_file.download_file(dropbox_file_path, save_file_path)
                
                # Determine the MIME type based on the file extension
                mime_type, _ = mimetypes.guess_type(save_file_path)
                if not mime_type:
                    mime_type = "application/octet-stream"  # Fallback for unknown types
                
                return FileResponse(
                    path=save_file_path,
                    filename=os.path.basename(save_file_path),
                    media_type=mime_type
                )
        
        # If file not found anywhere
        raise HTTPException(status_code=404, detail=f"File '{file_name}' not found in any connected storage")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)