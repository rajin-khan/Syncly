import json
import logging
import re
import requests
from telegram import InputFile, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import os
import secrets
import asyncio

TOKEN = "7728489108:AAEARmLHOsCUTBpGEZ03-Ol53SNLKTPcROI"
API_BASE_URL = "http://127.0.0.1:8000"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

os.makedirs("downloads", exist_ok=True)



# Ensure downloads directory exists
os.makedirs("downloads", exist_ok=True)

def sanitize_filename(filename: str) -> str:
    """Sanitize the filename to remove invalid characters."""
    return re.sub(r'[<>:"/\\|?*]', "_", filename)

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        "Hi! I'm the Syncly Bot. My commands are:\n"
        "/login - Log in to your account\n"
        "/addbucket <bucketType> - Add a new storage bucket\n"
        "/storage - View Total Storage Information\n"
        "/search <fileName> - Find a specific file\n"
        "/list - List your files\n"
        "/upload - Send a file to upload\n"
        "/logout - Log out\n"
    )

async def login(update: Update, context: CallbackContext) -> None:
    telegram_id = update.message.from_user.id
    if "jwt" in context.user_data:
        await update.message.reply_text("ℹ️ You’re already logged in.")
        return

    login_code = secrets.token_hex(4)
    context.user_data["login_code"] = login_code
    context.user_data["telegram_id"] = telegram_id

    login_url = f"{API_BASE_URL}/static/login.html?code={login_code}&telegram_id={telegram_id}"
    await update.message.reply_text(
        f"Please log in here:\n{login_url}\nComplete the login within 5 minutes."
    )

    async def poll_login():
        for _ in range(300):
            try:
                response = requests.get(
                    f"{API_BASE_URL}/check-login?code={login_code}&telegram_id={telegram_id}"
                )
                if response.status_code == 200:
                    data = response.json()
                    context.user_data["jwt"] = data["jwt"]
                    context.user_data["username"] = data["username"]
                    await update.message.reply_text(f"✅ Login successful! Welcome, {data['username']}.")
                    return
            except requests.exceptions.RequestException as e:
                logger.error(f"Polling error: {e}")
            await asyncio.sleep(1)
        await update.message.reply_text("❌ Login timed out. Please try /login again.")
        context.user_data.pop("login_code", None)

    asyncio.create_task(poll_login())

async def logout(update: Update, context: CallbackContext) -> None:
    if "jwt" in context.user_data:
        username = context.user_data.get("username", "unknown")
        context.user_data.clear()
        logger.info(f"User {username} logged out")
        await update.message.reply_text("✅ You have been logged out.")
    else:
        await update.message.reply_text("ℹ️ You're not logged in.")

async def add_drive(update: Update, context: CallbackContext) -> None:
    """Adds a new drive (GoogleDrive or Dropbox)."""
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please log in first using /login.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /addbucket <drive_type> (GoogleDrive or Dropbox)")
        return
    
    drive_type = context.args[0]
    if drive_type not in ["GoogleDrive", "Dropbox"]:
        await update.message.reply_text("❌ Invalid drive type. Choose 'GoogleDrive' or 'Dropbox'.")
        return

    logger.info(f"Attempting to add drive: {drive_type} for user: {context.user_data['username']}")
    
    try:
        # Send a request to the API to add the drive
        response = requests.post(
            f"{API_BASE_URL}/drives",
            json={"drive_type": drive_type},
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        drive_data = response.json()
        logger.info(f"Drive added successfully: {drive_data}")
        await update.message.reply_text(f"✅ {drive_type} added successfully!\n{drive_data['message']}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to add drive: {e}")
        await update.message.reply_text("❌ Failed to add drive. Please try again.")

async def list_files(update: Update, context: CallbackContext) -> None:
    """Lists stored files with names, providers, and links."""
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please log in first using /login.")
        return

    limit = 10
    if context.args:
        try:
            limit = int(context.args[0])
            if limit <= 0:
                await update.message.reply_text("❌ Please provide a positive number for the limit.")
                return
        except ValueError:
            await update.message.reply_text("❌ Invalid limit. Please provide a number.")
            return

    context.user_data["list_offset"] = 0
    context.user_data["list_limit"] = limit

    try:
        logger.info(f"Fetching files for user: {context.user_data['username']} with limit: {limit}, offset: 0")
        response = requests.get(
            f"{API_BASE_URL}/viewfiles",
            params={"limit": limit, "offset": 0},
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()
        
        files = response.json()
        logger.info(f"API Response: {json.dumps(files, indent=2)}")
        
        if files:
            file_list = [f"📄 {file['name']} ({file['provider']})\nLink: {file['path']}" for file in files]
            message = f"📂 Your Files ({len(files)} shown, starting at 1):\n\n" + "\n".join(file_list)
            if len(files) == limit:
                message += "\n\nℹ️ Type /more to see the next set or /exit to stop."
            else:
                message += "\n\nℹ️ No more files to show."
                context.user_data.pop("list_offset", None)
                context.user_data.pop("list_limit", None)
            await update.message.reply_text(message)
        else:
            await update.message.reply_text("📂 No files found. Try uploading files or check your buckets.")
            context.user_data.pop("list_offset", None)
            context.user_data.pop("list_limit", None)
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve files: {e}")
        await update.message.reply_text("❌ Failed to retrieve files.")
        context.user_data.pop("list_offset", None)
        context.user_data.pop("list_limit", None)

async def more_files(update: Update, context: CallbackContext) -> None:
    """Fetches the next set of files."""
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please log in first using /login.")
        return

    offset = context.user_data.get("list_offset")
    limit = context.user_data.get("list_limit")
    if offset is None or limit is None:
        await update.message.reply_text("❌ Please use /list first to start viewing files.")
        return

    # Increment offset
    offset += limit
    context.user_data["list_offset"] = offset

    try:
        logger.info(f"Fetching more files for user: {context.user_data['username']} with limit: {limit}, offset: {offset}")
        response = requests.get(
            f"{API_BASE_URL}/viewfiles",
            params={"limit": limit, "offset": offset},
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()
        
        files = response.json()
        logger.info(f"API Response: {files}")
        
        if files:
            file_list = [f"📄 {file['name']} ({file['provider']})\nLink: {file['path']}" for file in files]
            start_num = offset + 1
            end_num = offset + len(files)
            message = f"📂 Your Files ({len(files)} shown, {start_num}-{end_num}):\n\n" + "\n".join(file_list)
            if len(files) == limit:
                message += "\n\nℹ️ Type /more to see the next set or /exit to stop."
            else:
                message += "\n\nℹ️ No more files to show."
                context.user_data.pop("list_offset", None)
                context.user_data.pop("list_limit", None)
            await update.message.reply_text(message)
        else:
            await update.message.reply_text("📂 No more files to show.")
            context.user_data.pop("list_offset", None)
            context.user_data.pop("list_limit", None)
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve more files: {e}")
        await update.message.reply_text("❌ Failed to retrieve more files.")
        context.user_data.pop("list_offset", None)
        context.user_data.pop("list_limit", None)

async def exit_listing(update: Update, context: CallbackContext) -> None:
    """Exits the file listing mode."""
    if "list_offset" in context.user_data or "list_limit" in context.user_data:
        context.user_data.pop("list_offset", None)
        context.user_data.pop("list_limit", None)
        await update.message.reply_text("✅ Exited file listing mode.")
    else:
        await update.message.reply_text("ℹ️ You’re not in file listing mode.")

async def search_file(update: Update, context: CallbackContext) -> None:
    """Searches for a file by name across all buckets."""
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please log in first using /login.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("❌ Usage: /search <filename>")
        return

    filename = " ".join(context.args)
    logger.info(f"Searching for file '{filename}' for user: {context.user_data.get('username', 'unknown')}")

    try:
        response = requests.get(
            f"{API_BASE_URL}/search_files",
            params={"query": filename, "limit": 1},  # exact_match=False by default
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()
        
        files = response.json()
        logger.info(f"Search API Response: {files}")
        
        if files:
            file = files[0]
            size_str = file['size'] if file['size'] == "Unknown" else f"{int(file['size']) / 1024 / 1024:.2f} MB"
            message = (
                f"✅ File found:\n"
                f"📄 {file['name']} ({file['provider']})\n"
                f"Size: {size_str}\n"
                f"Link: {file['path']}"
            )
            await update.message.reply_text(message)
        else:
            await update.message.reply_text(f"❌ No file named '{filename}' found in your buckets.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to search for file '{filename}': {e}")
        await update.message.reply_text(f"❌ Failed to search for file: {str(e)}")

async def upload_file(update: Update, context: CallbackContext) -> None:
    """Uploads a file to Syncly."""
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please log in first using /login.")
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

    logger.info(f"Uploading file: {file_path} for user: {context.user_data['username']}")
    try:
        with open(file_path, "rb") as f:
            files = {"file": f}
            response = requests.post(
                f"{API_BASE_URL}/files/upload",
                files=files,
                headers={"Authorization": f"Bearer {jwt}"}
            )
            response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        logger.error(f"File upload failed: {e}")
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
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please log in first using /login.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /download <file_name>")
        return
    
    file_name = context.args[0]
    sanitized_file_name = sanitize_filename(file_name)  # Sanitize the filename
    logger.info(f"Downloading file: {sanitized_file_name} for user: {context.user_data['username']}")
    try:
        response = requests.get(
            f"{API_BASE_URL}/files/download",
            params={"file_name": sanitized_file_name},
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.exceptions.RequestException as e:
        logger.error(f"File download failed for file {sanitized_file_name}: {e}")
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
    
async def storage_info(update: Update, context: CallbackContext) -> None:
    """Retrieves and displays storage information for the user."""
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please log in first using /login.")
        return

    logger.info(f"Fetching storage info for user: {context.user_data['username']}")
    try:
        # Call the API to get storage information
        response = requests.get(
            f"{API_BASE_URL}/storage",
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the API response
        storage_data = response.json()
        logger.info(f"API Response: {storage_data}")
        
        # Extract storage details
        total_storage = storage_data["total_storage_gb"]
        used_storage = storage_data["used_storage_gb"]
        free_storage = storage_data["free_storage_gb"]
        
        # Format the message
        message = (
            f"🗂️ **Storage Information**\n"
            f"Total Storage: {total_storage:.2f} GB\n"
            f"Used Storage: {used_storage:.2f} GB\n"
            f"Free Storage: {free_storage:.2f} GB"
        )
        
        await update.message.reply_text(message, parse_mode="Markdown")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve storage info: {e}")
        await update.message.reply_text("❌ Failed to retrieve storage information.")

def main():
    """Start the bot."""
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))         #start command
    app.add_handler(CommandHandler("login", login))         #login command
    app.add_handler(CommandHandler("addbucket", add_drive)) #add new bucket command
    app.add_handler(CommandHandler("list", list_files))     #list files commandd
    app.add_handler(CommandHandler("more", more_files))     #more files command
    app.add_handler(CommandHandler("exit", exit_listing))   #exit file listing comamnd
    app.add_handler(CommandHandler("search", search_file))  #search files command
    #app.add_handler(CommandHandler("download", download_file))#download file command
    app.add_handler(CommandHandler("storage", storage_info))    #storage info command
    app.add_handler(CommandHandler("logout",logout))    #logout command
    app.add_handler(MessageHandler(filters.Document.ALL, upload_file))  #upload file command

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
