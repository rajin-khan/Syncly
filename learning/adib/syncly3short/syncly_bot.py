import logging
import requests
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import os
import mimetypes
import re
import dropbox  # Import Dropbox SDK

# Replace with your BotFather Token
TOKEN = "7840092563:AAE5GREtDI5rQj4IxWj9mlPG9lldY5vbJT0"

# Syncly API URL
API_BASE_URL = "http://127.0.0.1:8000"

# Dropbox App Credentials
DROPBOX_APP_KEY = "w84emdpux17qpnj"
DROPBOX_APP_SECRET = "x6ce7dtmj51xqc7"
DROPBOX_REDIRECT_URI = "https://your-redirect-uri.com"  # Replace with your redirect URI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Ensure downloads directory exists
os.makedirs("downloads", exist_ok=True)

def sanitize_filename(filename: str) -> str:
    """Sanitize the filename to remove invalid characters."""
    return re.sub(r'[<>:"/\\|?*]', "_", filename)

async def start(update: Update, context: CallbackContext) -> None:
    logger.info(f"Received /start command from user: {update.message.from_user.username}")
    await update.message.reply_text(
        "Welcome to Syncly Bot! Use the following commands:\n"
        "/login <username> <password> - Log in to your account\n"
        "/register <username> <password> - Register a new account\n"
        "/add_drive <drive_type> - Add a new drive (GoogleDrive or Dropbox)\n"
        "/list - List your files\n"
        #"/download <file_name> - Download a file"
    )

async def register(update: Update, context: CallbackContext) -> None:
    """Registers a new user."""
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /register <username> <password>")
        return
    
    username = context.args[0]
    password = context.args[1]

    logger.info(f"Attempting to register user: {username}")
    try:
        response = requests.post(f"{API_BASE_URL}/auth/register", json={"username": username, "password": password})
        response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        logger.error(f"Registration failed for user {username}: {e}")
        await update.message.reply_text("❌ Registration failed. Please try again.")
        return
    
    user_data = response.json()
    user_id = user_data["user_id"]
    logger.info(f"Registration successful for user: {username}, user_id: {user_id}")
    await update.message.reply_text(f"✅ Registration successful!\nUser ID: `{user_id}`", parse_mode="Markdown")

async def login(update: Update, context: CallbackContext) -> None:
    """Logs in a user."""
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /login <username> <password>")
        return
    
    username = context.args[0]
    password = context.args[1]

    logger.info(f"Attempting to log in user: {username}")
    try:
        response = requests.post(f"{API_BASE_URL}/auth/login", json={"username": username, "password": password})
        response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        logger.error(f"Login failed for user {username}: {e}")
        await update.message.reply_text("❌ Login failed. Please check your credentials.")
        return
    
    user_data = response.json()
    user_id = user_data["user_id"]
    context.user_data["user_id"] = user_id
    logger.info(f"Login successful for user: {username}, user_id: {user_id}")
    await update.message.reply_text(f"✅ Login successful!\nUser ID: `{user_id}`", parse_mode="Markdown")

async def add_drive(update: Update, context: CallbackContext) -> None:
    """Adds a new drive and forwards the OAuth authorization link for Dropbox to the user."""
    user_id = context.user_data.get("user_id")
    if not user_id:
        await update.message.reply_text("❌ Please login first using /login.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /add_drive <drive_type> (GoogleDrive or Dropbox)")
        return
    
    drive_type = context.args[0]
    if drive_type not in ["GoogleDrive", "Dropbox"]:
        await update.message.reply_text("❌ Invalid drive type. Choose 'GoogleDrive' or 'Dropbox'.")
        return

    logger.info(f"Attempting to add drive: {drive_type} for user: {user_id}")
    
    if drive_type == "Dropbox":
        # Generate OAuth URL for Dropbox
        auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(DROPBOX_APP_KEY, DROPBOX_APP_SECRET)
        authorize_url = auth_flow.start()
        
        # Store the CSRF token in user_data for later verification
        context.user_data["dropbox_csrf_token"] = auth_flow._csrf_token
        
        # Send the OAuth URL to the user
        await update.message.reply_text(
            f"✅ Please authorize the app by visiting this link:\n{authorize_url}\n"
            f"After authorization, use /auth_dropbox <code> to complete the process."
        )
    else:
        # Handle Google Drive
        try:
            response = requests.post(
                f"{API_BASE_URL}/drives",
                json={"drive_type": drive_type},
                params={"user_id": user_id}
            )
            response.raise_for_status()  # Raise an exception for HTTP errors
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to add drive for user {user_id}: {e}")
            await update.message.reply_text("❌ Failed to add drive. Please try again.")
            return
        
        drive_data = response.json()
        logger.info(f"Drive added successfully: {drive_data}")
        await update.message.reply_text(f"✅ Google Drive added successfully!\n{drive_data['message']}")

async def auth_dropbox(update: Update, context: CallbackContext) -> None:
    """Handles the OAuth callback for Dropbox."""
    user_id = context.user_data.get("user_id")
    if not user_id:
        await update.message.reply_text("❌ Please login first using /login.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /auth_dropbox <code>")
        return
    
    auth_code = context.args[0]
    csrf_token = context.user_data.get("dropbox_csrf_token")
    
    if not csrf_token:
        await update.message.reply_text("❌ OAuth session expired. Please start over.")
        return
    
    # Complete the OAuth flow
    auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(DROPBOX_APP_KEY, DROPBOX_APP_SECRET)
    try:
        access_token, _ = auth_flow.finish(auth_code)
    except Exception as e:
        logger.error(f"Failed to retrieve Dropbox access token: {e}")
        await update.message.reply_text("❌ Failed to authorize Dropbox. Please try again.")
        return
    
    # Store the access token in the API
    try:
        response = requests.post(
            f"{API_BASE_URL}/drives",
            json={"drive_type": "Dropbox", "access_token": access_token},
            params={"user_id": user_id}
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to add Dropbox drive for user {user_id}: {e}")
        await update.message.reply_text("❌ Failed to add Dropbox drive. Please try again.")
        return
    
    await update.message.reply_text("✅ Dropbox drive added successfully!")

async def list_files(update: Update, context: CallbackContext) -> None:
    """Lists stored files with an optional limit."""
    user_id = context.user_data.get("user_id")
    if not user_id:
        await update.message.reply_text("❌ Please login first using /login.")
        return

    # Default limit is 10 files
    limit = 10
    if context.args:
        try:
            limit = int(context.args[0])  # Get the limit from the command argument
            if limit <= 0:
                await update.message.reply_text("❌ Please provide a positive number for the limit.")
                return
        except ValueError:
            await update.message.reply_text("❌ Invalid limit. Please provide a number.")
            return

    try:
        logger.info(f"Fetching files for user: {user_id} with limit: {limit}")
        response = requests.get(f"{API_BASE_URL}/files", params={"user_id": user_id, "limit": limit}, timeout=5)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Log the API response
        files = response.json()
        logger.info(f"API Response: {files}")
        
        if files:
            file_list = "\n".join([f"📄 {file['name']} ({file['provider']})" for file in files])
            await update.message.reply_text(f"📂 Your Files (First {limit}):\n{file_list}")
        else:
            await update.message.reply_text("📂 No files found.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve files for user {user_id}: {e}")
        await update.message.reply_text("❌ Failed to retrieve files.")

async def upload_file(update: Update, context: CallbackContext) -> None:
    """Uploads a file to Syncly."""
    user_id = context.user_data.get("user_id")
    if not user_id:
        await update.message.reply_text("❌ Please login first using /login.")
        return
    
    if not update.message.document:
        await update.message.reply_text("❌ Please send a file to upload.")
        return

    # Get the file object
    file = await update.message.document.get_file()
    
    # Define the path to save the file locally
    file_path = f"downloads/{update.message.document.file_name}"
    
    # Download the file to the specified path
    await file.download_to_drive(file_path)

    logger.info(f"Uploading file: {file_path} for user: {user_id}")
    try:
        with open(file_path, "rb") as f:
            files = {"file": f}
            response = requests.post(f"{API_BASE_URL}/files/upload", files=files, data={"user_id": user_id})
            response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        logger.error(f"File upload failed for user {user_id}: {e}")
        await update.message.reply_text("❌ File upload failed.")
        return
    finally:
        # Clean up the temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Temporary file {file_path} cleaned up.")
    
    await update.message.reply_text("✅ File uploaded successfully!")

async def download_file(update: Update, context: CallbackContext) -> None:
    """Downloads a file from Syncly."""
    user_id = context.user_data.get("user_id")
    if not user_id:
        await update.message.reply_text("❌ Please login first using /login.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /download <file_name>")
        return
    
    file_name = context.args[0]
    sanitized_file_name = sanitize_filename(file_name)  # Sanitize the filename
    logger.info(f"Downloading file: {sanitized_file_name} for user: {user_id}")
    try:
        response = requests.get(f"{API_BASE_URL}/files/download", params={"user_id": user_id, "file_name": sanitized_file_name})
        response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        logger.error(f"File download failed for user {user_id}, file {sanitized_file_name}: {e}")
        await update.message.reply_text("❌ File not found or failed to download.")
        return
    
    # Save the file locally
    file_path = f"downloads/{sanitized_file_name}"
    with open(file_path, "wb") as f:
        f.write(response.content)

    # Send the file to the user
    await update.message.reply_document(
        document=InputFile(file_path, filename=sanitized_file_name),
        caption=f"Here is your file: {sanitized_file_name}"
    )

    # Log the file path for debugging
    logger.info(f"File saved at: {file_path}")

def main():
    """Start the bot."""
    app = Application.builder().token(TOKEN).build()

    # Register commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("add_drive", add_drive))
    app.add_handler(CommandHandler("auth_dropbox", auth_dropbox))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("download", download_file))
    app.add_handler(MessageHandler(filters.Document.ALL, upload_file))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()