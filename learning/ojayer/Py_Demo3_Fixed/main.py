import os
import webbrowser
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from DriveManager import DriveManager
from Database import Database
from jose import jwt
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Syncly-CLI")

WEB_PORTAL_URL = "http://127.0.0.1:8000"

def authenticate_via_web_portal():
    cli_code = secrets.token_hex(4)
    auth_url = f"{WEB_PORTAL_URL}/static/login.html?cli_code={cli_code}"
    print(f"\nPlease authenticate via the web portal:\n{auth_url}")
    logger.info(f"Opening auth URL with cli_code: {cli_code}")
    webbrowser.open(auth_url)

    class AuthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            token = query.get("token", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Authentication successful! You can close this window.")
            if token:
                self.server.token = token
                logger.info("Token received by CLI server")
            else:
                logger.warning("No token in callback")

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("localhost", 8081), AuthHandler)
    server.token = None
    print("Waiting for authentication to complete...")
    timeout_seconds = 180  # 3 minutes

    try:
        start_time = time.time()
        while not server.token and time.time() - start_time < timeout_seconds:
            server.handle_request()
    except KeyboardInterrupt:
        logger.info("Authentication interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        server.server_close()
        logger.info("CLI server closed")

    token = server.token
    if not token:
        logger.error("Authentication failed: No token received")
        print("Authentication failed: No token received.")
        return None
    return token

def get_user_id(token):
    try:
        payload = jwt.decode(token, "your-secret-key", algorithms=["HS256"])
        username = payload.get("sub")
        db = Database().get_instance()
        user = db.users_collection.find_one({"username": username})
        if user:
            logger.info(f"User ID retrieved for username: {username}")
            return str(user["_id"])
        logger.error("User not found for token")
        return None
    except Exception as e:
        logger.error(f"Error decoding token: {e}")
        print("Error decoding token:", e)
        return None

def display_menu(storages, limit, usage):
    for storage in storages:
        print(f"{storage['Provider']} - Drive {storage['Drive Number']}:")
        print(f"  - Storage Limit: {storage['Storage Limit (bytes)']:.2f} GB")
        print(f"  - Used Storage: {storage['Used Storage (bytes)']:.2f} GB")
        print(f"  - Free Storage: {storage['Free Storage']:.2f} GB")
        print("-" * 30)
    print("Storage Details")
    print("-" * 30)
    print(f"Total Storage: {round(limit / 1024**3, 2)} GB")
    print(f"Used Space: {round(usage / 1024**3, 2)} GB")
    print(f"Free Space: {round((limit - usage) / 1024**3, 2)} GB")
    print("\n1: View Files\n2: Upload File\n3: Download File\n4: Add New Bucket\n5: Exit")

def main():
    print("WELCOME TO SYNCLY! <3")
    logger.info("Starting Syncly CLI")

    token = None
    while not token:
        token = authenticate_via_web_portal()
        if not token:
            retry = input("Retry authentication? (y/n): ").strip().lower()
            if retry != 'y':
                print("Exiting Syncly.")
                logger.info("User exited CLI")
                return

    user_id = get_user_id(token)
    if not user_id:
        print("Error: Unable to retrieve user ID from token.")
        logger.error("Failed to retrieve user ID")
        return

    drive_manager = DriveManager(user_id=user_id, token_dir="tokens")
    drive_manager.load_user_drives()

    while True:
        storages, limit, usage = drive_manager.check_all_storages()
        display_menu(storages, limit, usage)
        choice = input("Choose option: ").strip()

        if choice == "1":
            drive_manager.list_files_from_all_buckets()
        elif choice == "2":
            file_path = input("Enter file path to upload: ").strip()
            if os.path.exists(file_path):
                print("Upload not implemented in this example.")
            else:
                print("File not found.")
        elif choice == "3":
            file_name = input("Enter file name to download: ").strip()
            print("Download not implemented in this example.")
        elif choice == "4":
            drive_type = input("Enter drive type (GoogleDrive/Dropbox): ").strip()
            if drive_type in ["GoogleDrive", "Dropbox"]:
                print("Add drive not implemented in this example.")
            else:
                print("Invalid drive type.")
        elif choice == "5":
            print("Thank you for using Syncly!")
            logger.info("Exiting Syncly CLI")
            break
        else:
            print("Invalid option. Please try again.")

if __name__ == "__main__":
    main()