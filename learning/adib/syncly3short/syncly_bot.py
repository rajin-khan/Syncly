import logging
import requests
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import os

# Replace with your BotFather Token
TOKEN = "7840092563:AAE5GREtDI5rQj4IxWj9mlPG9lldY5vbJT0"

# Syncly API URL
API_BASE_URL = "http://127.0.0.1:8000"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure downloads directory exists
os.makedirs("downloads", exist_ok=True)

async def start(update: Update, context: CallbackContext) -> None:
    logger.info(f"Received /start command from user: {update.message.from_user.username}")
    await update.message.reply_text("Welcome to Syncly Bot! Use /login <username> <password> to authenticate.")

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
    logger.info(f"Downloading file: {file_name} for user: {user_id}")
    try:
        response = requests.get(f"{API_BASE_URL}/files/download", params={"user_id": user_id, "file_name": file_name})
        response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        logger.error(f"File download failed for user {user_id}, file {file_name}: {e}")
        await update.message.reply_text("❌ File not found or failed to download.")
        return
    
    # Save the file locally
    file_path = f"downloads/{file_name}"
    with open(file_path, "wb") as f:
        f.write(response.content)

    # Send the file to the user
    await update.message.reply_document(document=InputFile(file_path, filename=file_name))

def main():
    """Start the bot."""
    app = Application.builder().token(TOKEN).build()

    # Register commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("download", download_file))
    app.add_handler(MessageHandler(filters.Document.ALL, upload_file))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()