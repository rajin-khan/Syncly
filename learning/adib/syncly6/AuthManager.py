import os
import base64
import hashlib
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from dropbox.oauth import DropboxOAuth2Flow
import dropbox
import logging
from Database import Database
from jose import JWTError, jwt
from datetime import datetime, timedelta

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
        self.DROPBOX_REDIRECT_URI = "http://localhost:8080"
    
    def register_user(self, username, password):
        if self.db.users_collection.find_one({"username": username}):
            print("Username already exists. Please choose a different username.")
            return None
        hashed_password = base64.b64encode(hashlib.sha256(password.encode()).digest()).decode('utf-8')  # Match api.py
        user_id = self.db.users_collection.insert_one({
            "username": username,
            "password": hashed_password,
            "drives": []
        }).inserted_id
        self.user_id = user_id
        print(f"User '{username}' registered successfully.")
        return user_id

    def login_user(self, username, password):
        user = self.db.users_collection.find_one({"username": username})
        if not user:
            print("User not found. Please register first.")
            return None
        hashed_password = base64.b64encode(hashlib.sha256(password.encode()).digest()).decode('utf-8')  # Match api.py
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
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES, redirect_uri="http://localhost:8080")
            creds = flow.run_local_server(port=8080)

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
        """Authenticate with Dropbox using a browser-based flow"""
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
        auth_flow = DropboxOAuth2Flow(
            consumer_key=app_key,
            consumer_secret=app_secret,
            redirect_uri=self.DROPBOX_REDIRECT_URI,
            session={},
            csrf_token_session_key="dropbox-auth-csrf-token"
        )
        
        authorize_url = auth_flow.start()
        logger.info(f"Opening browser for Dropbox auth: {authorize_url}")
        import webbrowser
        webbrowser.open(authorize_url)
        
        from http.server import HTTPServer, BaseHTTPRequestHandler
        from urllib.parse import urlparse, parse_qs
        
        class OAuthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = urlparse(self.path).query
                params = parse_qs(query)
                self.server.auth_code = params.get("code", [None])[0]
                self.server.state = params.get("state", [None])[0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"Authentication successful. You can close this window.")
        
        server = HTTPServer(("localhost", 8080), OAuthHandler)
        server.auth_code = None
        server.handle_request()  # Blocks until callback
        
        if not server.auth_code:
            logger.error("No auth code received from Dropbox.")
            raise Exception("Dropbox authentication failed: No code received")
        
        try:
            oauth_result = auth_flow.finish({"code": server.auth_code, "state": server.state})
            
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
            raise
    
    def _save_token(self, bucket_number, service_type, token_data):
        """Save tokens to MongoDB"""
        self.db.tokens_collection.update_one(
            {"user_id": self.user_id, "bucket_number": bucket_number, "service_type": service_type},
            {"$set": token_data},
            upsert=True
        )
    
    def _save_token(self, bucket_number, service_type, token_data):
        """Save tokens to MongoDB"""
        self.db.tokens_collection.update_one(
            {"user_id": self.user_id, "bucket_number": bucket_number, "service_type": service_type},
            {"$set": token_data},
            upsert=True
        )