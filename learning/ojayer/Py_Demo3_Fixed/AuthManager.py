import os
import logging
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from bson.objectid import ObjectId
import base64
import hashlib
import dropbox
from dropbox.oauth import DropboxOAuth2Flow
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from jose import JWTError, jwt
from Database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class OAuthHandler(BaseHTTPRequestHandler):
    """Handle OAuth redirects for Google Drive and Dropbox"""
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        self.server.auth_code = query_params.get('code', [None])[0]
        self.server.auth_state = query_params.get('state', [None])[0]
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Authentication successful! You can close this window.")
        logger.info(f"Captured OAuth code: {self.server.auth_code}")

class AuthManager:
    """Manages authentication for users and cloud services"""
    
    def __init__(self, user_id=None, token_dir="tokens"):
        self.user_id = ObjectId(user_id) if user_id else None
        self.token_dir = token_dir
        self.db = Database.get_instance()
        os.makedirs(self.token_dir, exist_ok=True)
        
        # Enforce SECRET_KEY from environment
        self.SECRET_KEY = os.getenv("SECRET_KEY")
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY environment variable is not set")
        self.ALGORITHM = "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        self.REDIRECT_URI = "http://localhost:8080"
        self.GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive']
        
        logger.info(f"AuthManager initialized for user_id: {self.user_id}")

    # User Authentication Methods
    def register_user(self, username: str, password: str) -> str | None:
        """Register a new user with hashed password"""
        try:
            if self.db.users_collection.find_one({"username": username}):
                logger.warning(f"Registration failed: Username '{username}' already exists")
                return None
            
            hashed_password = base64.b64encode(hashlib.sha256(password.encode()).digest()).decode('utf-8')
            user_id = self.db.users_collection.insert_one({
                "username": username,
                "password": hashed_password,
                "drives": []
            }).inserted_id
            
            self.user_id = user_id
            logger.info(f"User '{username}' registered with ID: {user_id}")
            return str(user_id)
        except Exception as e:
            logger.error(f"Error registering user '{username}': {e}")
            return None

    def login_user(self, username: str, password: str) -> str | None:
        """Authenticate a user and return their ID"""
        try:
            user = self.db.users_collection.find_one({"username": username})
            if not user:
                logger.warning(f"Login failed: User '{username}' not found")
                return None
            
            hashed_password = base64.b64encode(hashlib.sha256(password.encode()).digest()).decode('utf-8')
            if user["password"] != hashed_password:
                logger.warning(f"Login failed: Incorrect password for '{username}'")
                return None
            
            self.user_id = user["_id"]
            logger.info(f"User '{username}' logged in with ID: {self.user_id}")
            return str(self.user_id)
        except Exception as e:
            logger.error(f"Error logging in user '{username}': {e}")
            return None
    
    def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:
        """Create a JWT token for user authentication"""
        try:
            to_encode = data.copy()
            expire = datetime.utcnow() + (expires_delta or timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES))
            to_encode.update({"exp": expire})
            encoded_jwt = jwt.encode(to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM)
            logger.debug(f"Created JWT for user_id: {data.get('sub')}")
            return encoded_jwt
        except Exception as e:
            logger.error(f"Error creating JWT: {e}")
            raise

    # Cloud Service Authentication Methods
    def authenticate_google_drive(self, bucket_number: int, credentials_file: str = "credentials.json"):
        """Authenticate Google Drive using OAuth2"""
        try:
            if not self.user_id:
                logger.error("No user_id set for Google Drive authentication")
                return None

            # Check for existing token
            token_data = self.db.tokens_collection.find_one({
                "user_id": self.user_id,
                "bucket_number": bucket_number,
                "service_type": "GoogleDrive"
            })
            
            creds = None
            if token_data:
                try:
                    creds = Credentials.from_authorized_user_info({
                        "token": token_data.get("access_token"),
                        "refresh_token": token_data.get("refresh_token"),
                        "client_id": token_data.get("client_id"),
                        "client_secret": token_data.get("client_secret"),
                        "token_uri": token_data.get("token_uri"),
                        "scopes": token_data.get("scopes")
                    })
                    if creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                        self._save_token(bucket_number, "GoogleDrive", {
                            "access_token": creds.token,
                            "refresh_token": creds.refresh_token,
                            "client_id": creds.client_id,
                            "client_secret": creds.client_secret,
                            "token_uri": creds.token_uri,
                            "scopes": creds.scopes
                        })
                        logger.info(f"Refreshed Google Drive token for bucket {bucket_number}")
                except Exception as e:
                    logger.warning(f"Invalid Google Drive token for bucket {bucket_number}: {e}")
                    creds = None

            if not creds or not creds.valid:
                logger.info(f"Starting Google Drive OAuth for bucket {bucket_number}")
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, self.GOOGLE_SCOPES, redirect_uri=self.REDIRECT_URI
                )
                creds = flow.run_local_server(port=8080, open_browser=True)
                
                self._save_token(bucket_number, "GoogleDrive", {
                    "user_id": self.user_id,
                    "bucket_number": bucket_number,
                    "service_type": "GoogleDrive",
                    "access_token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "token_uri": creds.token_uri,
                    "scopes": creds.scopes
                })
                logger.info(f"Google Drive authentication successful for bucket {bucket_number}")

            service = build("drive", "v3", credentials=creds)
            return service
        except Exception as e:
            logger.error(f"Error authenticating Google Drive bucket {bucket_number}: {e}")
            return None

    def authenticate_dropbox(self, bucket_number: int, app_key: str, app_secret: str):
        """Authenticate Dropbox using OAuth2"""
        try:
            if not self.user_id:
                logger.error("No user_id set for Dropbox authentication")
                return None

            # Check for existing token
            token_data = self.db.tokens_collection.find_one({
                "user_id": self.user_id,
                "bucket_number": bucket_number,
                "service_type": "Dropbox"
            })
            
            if token_data and token_data.get("access_token"):
                dbx = dropbox.Dropbox(token_data["access_token"])
                try:
                    dbx.users_get_current_account()
                    logger.info(f"Dropbox client initialized from saved token for bucket {bucket_number}")
                    return dbx
                except dropbox.exceptions.AuthError as e:
                    logger.warning(f"Invalid Dropbox token for bucket {bucket_number}: {e}")
                    # Clear invalid token
                    self.db.tokens_collection.delete_one({
                        "user_id": self.user_id,
                        "bucket_number": bucket_number,
                        "service_type": "Dropbox"
                    })

            # Start OAuth flow
            if not app_key or not app_secret:
                logger.error(f"Missing Dropbox app_key or app_secret for bucket {bucket_number}")
                return None

            logger.info(f"Starting Dropbox OAuth for bucket {bucket_number}")
            flow = DropboxOAuth2Flow(
                app_key, app_secret, redirect_uri=self.REDIRECT_URI,
                session={}, token_access_type='offline'
            )
            authorize_url = flow.start()
            logger.info(f"Opening browser for Dropbox auth: {authorize_url}")
            webbrowser.open(authorize_url)

            # Start local server to capture OAuth code
            server_address = ('localhost', 8080)
            httpd = HTTPServer(server_address, OAuthHandler)
            httpd.auth_code = None
            httpd.auth_state = None
            logger.info("Waiting for Dropbox OAuth callback...")
            httpd.handle_request()
            httpd.server_close()

            if not httpd.auth_code:
                logger.error("No auth code received from Dropbox")
                return None

            access_token, _ = flow.finish(httpd.auth_code)
            dbx = dropbox.Dropbox(access_token)
            dbx.users_get_current_account()  # Verify token
            
            # Save token to MongoDB
            self._save_token(bucket_number, "Dropbox", {
                "user_id": self.user_id,
                "bucket_number": bucket_number,
                "service_type": "Dropbox",
                "access_token": access_token
            })
            logger.info(f"Dropbox authentication successful for bucket {bucket_number}")
            return dbx
        except Exception as e:
            logger.error(f"Error authenticating Dropbox bucket {bucket_number}: {e}")
            return None

    def _save_token(self, bucket_number: int, service_type: str, token_data: dict):
        """Save tokens to MongoDB"""
        try:
            token_data["user_id"] = self.user_id
            token_data["bucket_number"] = bucket_number
            token_data["service_type"] = service_type
            self.db.tokens_collection.update_one(
                {
                    "user_id": self.user_id,
                    "bucket_number": bucket_number,
                    "service_type": service_type
                },
                {"$set": token_data},
                upsert=True
            )
            logger.debug(f"Saved {service_type} token for bucket {bucket_number}")
        except Exception as e:
            logger.error(f"Error saving {service_type} token for bucket {bucket_number}: {e}")