import os
import hashlib
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from dropbox.oauth import DropboxOAuth2FlowNoRedirect
import dropbox
import logging
from Database import Database
from jose import JWTError, jwt
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthManager:
    """Centralized authentication manager for all cloud services"""
    
    def __init__(self, user_id=None, token_dir="tokens"):
        self.user_id = user_id
        self.token_dir = token_dir
        self.db = Database().get_instance()
        os.makedirs(self.token_dir, exist_ok=True)
        self.SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
        self.ALGORITHM = "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    
    def register_user(self, username, password):
        """Register a new user and return user_id"""
        if self.db.users_collection.find_one({"username": username}):
            print("Username already exists. Please choose a different username.")
            return None

        # Hash the password for security
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        # Insert the new user into the database
        user_id = self.db.users_collection.insert_one({
            "username": username,
            "password": hashed_password,
            "drives": []  # Initialize an empty list for drives
        }).inserted_id

        self.user_id = user_id
        print(f"User '{username}' registered successfully.")
        return user_id
    
    def login_user(self, username, password):
        """Login an existing user and return user_id"""
        user = self.db.users_collection.find_one({"username": username})
        if not user:
            print("User not found. Please register first.")
            return None

        # Verify the password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        if user["password"] != hashed_password:
            print("Incorrect password. Please try again.")
            return None

        self.user_id = user["_id"]
        print(f"User '{username}' logged in successfully.")
        return user["_id"]
    
    def create_access_token(self, data: dict, expires_delta: timedelta | None = None):
        """Create a JWT token for authentication"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM)
        return encoded_jwt

    def authenticate_google_drive(self, bucket_number, credentials_file="credentials.json"):
        """Authenticate with Google Drive using PKCE and refresh tokens"""
        SCOPES = ['https://www.googleapis.com/auth/drive']
        token_data = self.db.tokens_collection.find_one({
            "user_id": self.user_id, 
            "bucket_number": bucket_number,
            "service_type": "GoogleDrive"
        })
        
        creds = None
        if token_data:
            try:
                creds = Credentials.from_authorized_user_info(token_data)
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
            except Exception as e:
                logger.error(f"Error loading/refreshing Google Drive token: {e}")
                creds = None

        if not creds or not creds.valid:
            logger.info("Starting Google Drive authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

            token_data = {
                "user_id": self.user_id,
                "bucket_number": bucket_number,
                "service_type": "GoogleDrive",
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "token_uri": creds.token_uri,
                "scopes": creds.scopes
            }
            
            self._save_token(bucket_number, "GoogleDrive", token_data)
            logger.info("Google Drive authentication successful.")
        
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds)
    
    def authenticate_dropbox(self, bucket_number, app_key, app_secret):
        """Authenticate with Dropbox using PKCE and refresh tokens"""
        token_data = self.db.tokens_collection.find_one({
            "user_id": self.user_id, 
            "bucket_number": bucket_number,
            "service_type": "Dropbox"
        })
        
        dbx = None
        if token_data:
            try:
                dbx = dropbox.Dropbox(
                    oauth2_access_token=token_data.get("access_token"),
                    oauth2_refresh_token=token_data.get("refresh_token"),
                    app_key=app_key,
                    app_secret=app_secret
                )
                dbx.users_get_current_account()
                logger.info("Dropbox client initialized from saved token.")
                return dbx
            except Exception as e:
                logger.error(f"Error with Dropbox token: {e}")
                dbx = None
        
        logger.info("Starting Dropbox authentication...")
        auth_flow = DropboxOAuth2FlowNoRedirect(app_key, app_secret)
        authorize_url = auth_flow.start()
        print(f"\nAuthorize Dropbox app: {authorize_url}")
        auth_code = input("Enter auth code: ").strip()

        try:
            oauth_result = auth_flow.finish(auth_code)
            
            token_data = {
                "user_id": self.user_id,
                "bucket_number": bucket_number,
                "service_type": "Dropbox",
                "access_token": oauth_result.access_token,
                "refresh_token": oauth_result.refresh_token,
                "app_key": app_key,
                "app_secret": app_secret
            }
            
            self._save_token(bucket_number, "Dropbox", token_data)
            
            dbx = dropbox.Dropbox(
                oauth2_access_token=oauth_result.access_token,
                oauth2_refresh_token=oauth_result.refresh_token,
                app_key=app_key,
                app_secret=app_secret
            )
            logger.info("Dropbox authentication successful.")
            return dbx
            
        except Exception as e:
            logger.error(f"Dropbox authentication error: {e}")
            return None
    
    def _save_token(self, bucket_number, service_type, token_data):
        """Save tokens to MongoDB"""
        self.db.tokens_collection.update_one(
            {"user_id": self.user_id, "bucket_number": bucket_number, "service_type": service_type},
            {"$set": token_data},
            upsert=True
        )