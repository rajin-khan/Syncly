# --- START OF FILE synclybot.py ---

import logging
import requests
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import os
import mimetypes
import re
from telegram.ext import ApplicationBuilder, ContextTypes
from dotenv import load_dotenv # Ensure dotenv is loaded

# Load environment variables at the top
load_dotenv()

# --- Environment Variable Checks ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL")

# Configure logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Critical environment variable checks AFTER logging is configured
if not TOKEN:
    logger.critical("FATAL ERROR: TELEGRAM_BOT_TOKEN environment variable not set.")
    exit("Error: Telegram Bot Token not configured.")
if not API_BASE_URL:
    logger.critical("FATAL ERROR: API_BASE_URL environment variable not set.")
    exit("Error: API Base URL not configured.")


# Ensure downloads directory exists
os.makedirs("downloads", exist_ok=True)

# --- Helper Functions ---

def sanitize_filename(filename: str) -> str:
    """Sanitize the filename to remove invalid characters."""
    if not filename: # Handle empty input
        return "downloaded_file"
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename)
    # Remove leading/trailing whitespace/dots/underscores that might cause issues
    sanitized = sanitized.strip(" ._")
    # Replace multiple underscores with a single one
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized if sanitized else "downloaded_file" # Ensure not empty after sanitizing

# --- Command Handlers ---

async def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message and lists available commands."""
    user = update.effective_user
    # Log using user ID and username if available for better tracking
    logger.info(f"Received /start command from user: {user.username or 'N/A'} (ID: {user.id})")

    jwt = context.user_data.get("jwt")
    # Get username from context if logged in, otherwise use first name
    username_display = context.user_data.get("username", user.first_name or "there")

    if jwt:
        welcome_message = f"Hi {username_display}! You are logged in. "
    else:
        welcome_message = "Hi! I'm the Syncly Bot. "

    # Commands list (ensure consistency with added handlers)
    commands_text = (
        "My commands are:\n"
        "/login - Log in to your account\n"
        "/addbucket <Type> - Add GoogleDrive or Dropbox\n"
        "/storage - View your total storage info\n"
        "/list [limit] - List your files (e.g., /list 20)\n"
        "/more - Show next page of files (after /list)\n"
        "/exitlist - Exit file listing mode\n"
        "/search <name> - Find files by name\n"
        "/ask <question> - Ask Syncly AI about your files\n"
        "/reset - Reset Syncly AI conversation memory\n"
        "/upload - Send a file directly to this chat to upload\n"
        # "/download <name> - Download a file (currently disabled)\n"
        "/logout - Log out and clear session"
    )
    await update.message.reply_text(welcome_message + commands_text)

async def login(update: Update, context: CallbackContext) -> None:
    """Guides the user to log in via the web portal."""
    user = update.effective_user
    logger.info(f"Received /login command from user: {user.id}")
    # Ensure API_BASE_URL is correctly formed
    login_url = f"{API_BASE_URL.rstrip('/')}/static/login.html"
    await update.message.reply_text(
        f"Please log in or register via the web portal:\n{login_url}\n\n"
        "After logging in on the web, copy the JWT shown (it's a long string) "
        "and paste it back here in the chat."
    )

async def logout(update: Update, context: CallbackContext) -> None:
    """Logs out the user by clearing their session data."""
    user_id = update.effective_user.id
    logger.info(f"Received /logout command from user: {user_id}")

    if "jwt" in context.user_data:
        username = context.user_data.get("username", "unknown")
        # Optionally: Call an API endpoint to invalidate the JWT server-side if needed
        context.user_data.clear()  # Clear all user data (jwt, username, list_offset, etc.)
        logger.info(f"User {username} (ID: {user_id}) logged out")
        await update.message.reply_text("✅ You have been logged out. Use /login to start a new session.")
    else:
        await update.message.reply_text("ℹ️ You're not logged in.")

async def handle_jwt(update: Update, context: CallbackContext) -> None:
    """Handles the JWT pasted by the user."""
    # Ignore if message is empty or None, or if it's a command edit
    if not update.message or not update.message.text:
        return

    jwt_input = update.message.text.strip()
    user = update.effective_user
    username_display = user.username or f"User_{user.id}" # Handle missing username

    # Basic JWT format check + reasonable length check
    # Slightly improved regex to be less strict on the exact characters in the payload
    if not re.match(r"^[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]*$", jwt_input) or len(jwt_input) < 50:
        logger.debug(f"Ignoring non-command text message from {user.id} that doesn't look like a JWT: '{jwt_input[:50]}...'")
        return

    logger.info(f"Received potential JWT from user: {username_display} (ID: {user.id})")

    # Attempt to delete the user's message containing the JWT for security
    try:
        await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        logger.info(f"Deleted JWT message from chat for user {user.id}")
    except Exception as e:
        logger.warning(f"Could not delete JWT message for user {user.id}: {e}")
        await update.message.reply_text("⚠️ For security, please delete the message containing your token manually.")

    logger.info(f"Attempting to validate JWT for user {username_display} (ID: {user.id})")
    logger.debug(f"JWT Snippet: {jwt_input[:10]}...{jwt_input[-10:]}")

    try:
        # Validate the JWT with the backend
        api_url = f"{API_BASE_URL.rstrip('/')}/validate-token"
        # Send token as query parameter for this specific endpoint
        response = requests.post(api_url, params={"token": jwt_input}, timeout=10) # Added timeout

        response.raise_for_status()  # Raise an exception for HTTP errors (4xx, 5xx)

        # Extract the username from the API response
        validation_data = response.json()
        api_username = validation_data.get("username")
        if not api_username:
             raise ValueError("API did not return a username from token.")

        # Store JWT and username in user_data
        context.user_data["jwt"] = jwt_input
        context.user_data["username"] = api_username
        # Store telegram user id mapping (useful for /ask)
        context.user_data["telegram_id"] = str(user.id)

        logger.info(f"JWT validation successful for user {api_username} (ID: {user.id})")
        await update.message.reply_text(f"✅ Login successful! Welcome, {api_username}. You can now use other commands like /ask or /list.")

    except requests.exceptions.Timeout:
        logger.error(f"JWT validation API request timed out for user {user.id}")
        await update.message.reply_text("❌ Login failed. The validation request timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        logger.error(f"JWT validation API request failed for user {user.id}: {e}")
        error_detail = "Connection Error"
        status_code = None
        if e.response is not None:
            status_code = e.response.status_code
            try: error_detail = e.response.json().get("detail", e.response.text)
            except ValueError: error_detail = e.response.text[:200] # Limit length
        logger.error(f"API Response (Status {status_code}): {error_detail}")
        await update.message.reply_text(f"❌ Login failed. The token seems invalid or the API is unreachable. (Error: {error_detail}). Please /login again.")
    except ValueError as e: # Handles JSON decoding errors or missing username
         logger.error(f"JWT validation error (likely API response issue) for user {user.id}: {e}")
         await update.message.reply_text("❌ Login failed. Could not process the response from the server.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during JWT handling for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred during login. Please try again later.")


async def add_drive(update: Update, context: CallbackContext) -> None:
    """Adds a new drive (GoogleDrive or Dropbox)."""
    user = update.effective_user
    logger.info(f"Received /addbucket command from user: {user.id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first before adding a bucket.")
        return

    if not context.args or len(context.args) < 1: # Check context.args exists first
        await update.message.reply_text("Usage: /addbucket <DriveType>\nExample: `/addbucket GoogleDrive` or `/addbucket Dropbox`")
        return

    drive_type = context.args[0].strip()
    # Case-insensitive check and normalize
    if drive_type.lower() == "googledrive":
        drive_type_normalized = "GoogleDrive"
    elif drive_type.lower() == "dropbox":
        drive_type_normalized = "Dropbox"
    else:
        await update.message.reply_text("❌ Invalid drive type. Choose 'GoogleDrive' or 'Dropbox'.")
        return

    username = context.user_data.get('username', f'User_{user.id}')
    logger.info(f"Attempting to add drive: {drive_type_normalized} for user: {username} (ID: {user.id})")
    await update.message.reply_text(f"⏳ Adding {drive_type_normalized}. This may require you to authorize Syncly in your browser...")

    try:
        # Send a request to the API to add the drive
        response = requests.post(
            f"{API_BASE_URL.rstrip('/')}/drives",
            json={"drive_type": drive_type_normalized},
            headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}, # Add content type
            timeout=15 # Slightly longer timeout for potential OAuth redirects
        )
        response.raise_for_status()  # Raise an exception for HTTP errors

        drive_data = response.json()
        logger.info(f"Add drive API response for user {user.id}: {drive_data}")

        reply_message = drive_data.get("message", f"✅ {drive_type_normalized} added successfully!")
        # Include potential auth URLs if provided by the API (though usually handled by browser flow)
        if "auth_url" in drive_data:
            reply_message += f"\nPlease visit this URL if prompted: {drive_data['auth_url']}"

        await update.message.reply_text(reply_message)

    except requests.exceptions.Timeout:
        logger.error(f"Add drive API request timed out for user {user.id}")
        await update.message.reply_text(f"❌ Failed to add {drive_type_normalized}. The request timed out.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to add drive for user {user.id}: {e}")
        error_detail = "Connection Error"
        status_code = None
        if e.response is not None:
            status_code = e.response.status_code
            try: error_detail = e.response.json().get("detail", e.response.text)
            except ValueError: error_detail = e.response.text[:200]
             # Handle specific errors like timeout for Dropbox auth initiated server-side (less common now)
            if status_code == 408:
                 error_detail = "Authorization process timed out. Please try again and complete the steps in your browser promptly."
            elif status_code == 500 and "key not configured" in str(error_detail).lower():
                 error_detail = "Server configuration error. Dropbox App Key/Secret may be missing."

        logger.error(f"API Response (Status {status_code}): {error_detail}")
        await update.message.reply_text(f"❌ Failed to add drive. {error_detail}")
    except Exception as e:
        logger.error(f"An unexpected error occurred adding drive for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred while adding the drive.")

# --- List Files Handlers ---
async def list_files(update: Update, context: CallbackContext) -> None:
    """Lists stored files with names, providers, and sizes."""
    user = update.effective_user
    logger.info(f"Received /list command from user: {user.id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first.")
        return

    # Default limit
    limit = 10
    if context.args:
        try:
            limit = int(context.args[0])
            if limit <= 0 or limit > 100: # Add upper bound
                await update.message.reply_text("❌ Please provide a positive number for the limit (1-100).")
                return
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Invalid limit. Usage: /list [number_of_files]")
            return

    # Initialize or reset offset for a new /list command
    context.user_data["list_offset"] = 0
    context.user_data["list_limit"] = limit

    await update.message.reply_text(f"⏳ Fetching first {limit} files...")
    # Call the helper function to do the actual fetching and displaying
    await fetch_and_display_files(update, context, is_continuation=False)

async def more_files(update: Update, context: CallbackContext) -> None:
    """Fetches the next set of files."""
    user = update.effective_user
    logger.info(f"Received /more command from user: {user.id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first.")
        return

    # Use .get() for safer access
    offset = context.user_data.get("list_offset")
    limit = context.user_data.get("list_limit")

    # Check if user was actually in listing mode
    if offset is None or limit is None:
        await update.message.reply_text("ℹ️ Please use /list first to start viewing files before using /more.")
        return

    # Increment offset for the next page
    context.user_data["list_offset"] = offset + limit

    await update.message.reply_text(f"⏳ Fetching next {limit} files...")
    await fetch_and_display_files(update, context, is_continuation=True)

async def fetch_and_display_files(update: Update, context: CallbackContext, is_continuation: bool):
    """Helper function to fetch files from API and display them."""
    jwt = context.user_data.get("jwt")
    offset = context.user_data.get("list_offset")
    limit = context.user_data.get("list_limit")
    user = update.effective_user
    username = context.user_data.get('username', f'User_{user.id}')

    # Check required context data
    if not jwt: logger.error("JWT missing in fetch_and_display_files"); await update.message.reply_text("❌ Error: Session expired. Please /login again."); return
    if offset is None or limit is None: logger.error("Pagination state missing in fetch_and_display_files"); await update.message.reply_text("❌ Error fetching files state. Please try /list again."); return

    try:
        logger.info(f"Fetching files for user: {username} (ID: {user.id}) with limit: {limit}, offset: {offset}")
        response = requests.get(
            f"{API_BASE_URL.rstrip('/')}/viewfiles",
            params={"limit": limit, "offset": offset}, # Add query param if needed: "query": query_term
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=25 # Increased timeout
        )
        response.raise_for_status()

        files = response.json()
        logger.debug(f"API Response for files: {files}")

        if not files:
            if not is_continuation: await update.message.reply_text("📂 No files found in your connected drives.")
            else: await update.message.reply_text("✅ No more files to show.")
            context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None)
            return

        # Format file list
        file_list_text = []
        current_file_number = offset + 1
        for file in files:
            # --- CORRECTED SIZE HANDLING ---
            size_display = "Unknown"
            size_bytes = file.get('size') # API now returns int or None
            if isinstance(size_bytes, int): # Check if it's an integer
                if size_bytes == 0: size_display = "0 B"
                elif size_bytes < 1024: size_display = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024: size_display = f"{size_bytes / 1024:.1f} KB"
                else: size_display = f"{size_bytes / (1024*1024):.2f} MB"
            # --- END CORRECTED SIZE HANDLING ---

            provider = file.get('provider', 'Unknown')
            name = file.get('name', 'Unknown File')
            # Escape potential markdown characters in filename for safety if using Markdown parse mode
            # name_escaped = name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
            file_list_text.append(f"{current_file_number}. 📄 {name} ({provider}, {size_display})") # Using plain text
            current_file_number += 1

        start_num = offset + 1
        end_num = offset + len(files)
        message = f"📂 Files {start_num}-{end_num}:\n\n" + "\n".join(file_list_text)

        # Check if there might be more files to fetch
        if len(files) == limit:
            message += "\n\nℹ️ Type /more to see the next set, or /exitlist to stop."
        else:
            message += "\n\n✅ Reached the end of your files."
            context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None)

        # Send plain text to avoid markdown issues
        await update.message.reply_text(message)

    except requests.exceptions.Timeout:
        logger.error(f"API request timed out while fetching files for user {user.id}")
        await update.message.reply_text("❌ Failed to retrieve files: The request timed out.")
        context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None)
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve files for user {user.id}: {e}")
        error_detail = "Connection Error"; status_code = None
        if e.response is not None:
             status_code = e.response.status_code
             try: error_detail = e.response.json().get("detail", e.response.text)
             except ValueError: error_detail = e.response.text[:200]
        logger.error(f"API Response (Status {status_code}): {error_detail}")
        await update.message.reply_text(f"❌ Failed to retrieve files: {error_detail}")
        context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None)
    except Exception as e:
        # Log the specific error encountered by the bot
        logger.error(f"An unexpected error occurred fetching files for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred while fetching files.")
        context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None)

async def exit_listing(update: Update, context: CallbackContext) -> None:
    """Exits the file listing mode by clearing pagination state."""
    user = update.effective_user
    logger.info(f"Received /exitlist command from user: {user.id}")
    if "list_offset" in context.user_data or "list_limit" in context.user_data:
        context.user_data.pop("list_offset", None)
        context.user_data.pop("list_limit", None)
        await update.message.reply_text("✅ Exited file listing mode.")
    else:
        await update.message.reply_text("ℹ️ You weren't in file listing mode.")
# --- End List Files Handlers ---

async def search_file(update: Update, context: CallbackContext) -> None:
    """Searches for a file by name across all buckets."""
    user = update.effective_user
    logger.info(f"Received /search command from user: {user.id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /search <filename_query>")
        return

    filename_query = " ".join(context.args)
    username = context.user_data.get('username', f'User_{user.id}')
    logger.info(f"Searching for file '{filename_query}' for user: {username} (ID: {user.id})")
    await update.message.reply_text(f"⏳ Searching for '{filename_query}'...")

    try:
        # Use the API's search endpoint (fetch max 5 results for display)
        response = requests.get(
            f"{API_BASE_URL.rstrip('/')}/search_files",
            params={"query": filename_query, "limit": 5}, # Use query and limit params
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15
        )
        response.raise_for_status()

        files = response.json()
        logger.info(f"Search API Response for user {user.id}: {files}")

        if files:
            results_list = []
            for i, file in enumerate(files):
                # --- CORRECTED SIZE HANDLING ---
                size_display = "Unknown"
                size_bytes = file.get('size') # API now returns int or None
                if isinstance(size_bytes, int): # Check if it's an integer
                     if size_bytes == 0: size_display = "0 B"
                     elif size_bytes < 1024: size_display = f"{size_bytes} B"
                     elif size_bytes < 1024 * 1024: size_display = f"{size_bytes / 1024:.1f} KB"
                     else: size_display = f"{size_bytes / (1024*1024):.2f} MB"
                # --- END CORRECTED SIZE HANDLING ---

                provider = file.get('provider', 'Unknown')
                name = file.get('name', 'Unknown File')
                results_list.append(f"{i+1}. 📄 {name} ({provider}, {size_display})") # Plain text display

            message = f"✅ Found matching files for '{filename_query}':\n\n" + "\n".join(results_list)
            await update.message.reply_text(message)
        else:
            await update.message.reply_text(f"❌ No files found matching '{filename_query}' in your Syncly drives.")

    except requests.exceptions.Timeout:
        logger.error(f"API request timed out during search for '{filename_query}' for user {user.id}")
        await update.message.reply_text("❌ Search failed: The request timed out.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to search for file '{filename_query}' for user {user.id}: {e}")
        error_detail = "Connection Error"; status_code = None
        if e.response is not None:
            status_code = e.response.status_code
            try: error_detail = e.response.json().get("detail", e.response.text)
            except ValueError: error_detail = e.response.text[:200]
        logger.error(f"API Response (Status {status_code}): {error_detail}")
        await update.message.reply_text(f"❌ Failed to search for file: {error_detail}")
    except Exception as e:
        # Log the specific error encountered by the bot
        logger.error(f"An unexpected error occurred during search for user {user.id}: {e}", exc_info=True) # Log traceback
        await update.message.reply_text("❌ An unexpected error occurred during search.") # Generic message to user


async def upload_file(update: Update, context: CallbackContext) -> None:
    """Handles file uploads sent directly as documents."""
    user = update.effective_user
    logger.info(f"Received a document upload from user: {user.id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first before uploading files.")
        return

    if not update.message or not update.message.document:
        await update.message.reply_text("❓ Please send the file you want to upload.")
        return

    doc = update.message.document
    original_filename = doc.file_name or "untitled_upload"
    # Sanitize filename *before* using it in paths
    sanitized_filename = sanitize_filename(original_filename)
    if not sanitized_filename: # Handle case where sanitization results in empty name
        sanitized_filename = "uploaded_file"
        logger.warning(f"Original filename '{original_filename}' sanitized to empty, using default.")

    file_size = doc.file_size # Size in bytes
    mime_type = doc.mime_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"

    await update.message.reply_text(f"⏳ Receiving '{original_filename}' ({file_size / (1024*1024):.2f} MB)...")

    temp_dir = os.path.join("downloads", str(user.id))
    os.makedirs(temp_dir, exist_ok=True)
    # Use the sanitized name for the local temporary file path
    temp_file_path = os.path.join(temp_dir, sanitized_filename)

    file_id = doc.file_id
    username = context.user_data.get('username', f'User_{user.id}')

    try:
        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(custom_path=temp_file_path)
        logger.info(f"File '{original_filename}' downloaded to temporary path: {temp_file_path}")

        await update.message.reply_text("⬆️ Uploading to Syncly storage...")

        with open(temp_file_path, "rb") as f:
            # Send the *original* filename to the API, as the API expects it
            files_payload = {"file": (original_filename, f, mime_type)}
            response = requests.post(
                f"{API_BASE_URL.rstrip('/')}/files/upload",
                files=files_payload,
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=180 # Longer timeout for uploads
            )
            response.raise_for_status()

        upload_result = response.json()
        logger.info(f"File upload API response for user {user.id}: {upload_result}")
        await update.message.reply_text(upload_result.get("message", "✅ File uploaded successfully!"))

    except requests.exceptions.Timeout:
         logger.error(f"API request timed out during file upload for user {user.id}")
         await update.message.reply_text("❌ File upload failed: The request timed out.")
    except requests.exceptions.RequestException as e:
        logger.error(f"File upload API request failed for user {user.id}: {e}")
        error_detail = "Connection Error"; status_code = None
        if e.response is not None:
            status_code = e.response.status_code
            try: error_detail = e.response.json().get("detail", e.response.text)
            except ValueError: error_detail = e.response.text[:200]
        logger.error(f"API Response (Status {status_code}): {error_detail}")
        await update.message.reply_text(f"❌ File upload failed: {error_detail}")
    except Exception as e:
        logger.error(f"Error during file upload process for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred during the file upload.")
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Temporary file {temp_file_path} cleaned up.")
                # Attempt to remove the user-specific directory if empty
                # Use try-except in case dir is not empty or other issues
                try:
                    if not os.listdir(temp_dir):
                        os.rmdir(temp_dir)
                        logger.info(f"Removed empty temporary directory: {temp_dir}")
                except OSError:
                     logger.debug(f"Temporary directory {temp_dir} not empty or couldn't be removed.")
            except OSError as e:
                logger.warning(f"Could not clean up temporary file {temp_file_path}: {e}")


async def download_file(update: Update, context: CallbackContext) -> None:
    """Downloads a file from Syncly (Placeholder)."""
    await update.message.reply_text("ℹ️ File download via bot is not fully implemented. Use search/list and web links for now.")


async def storage_info(update: Update, context: CallbackContext) -> None:
    """Retrieves and displays storage information for the user."""
    user = update.effective_user
    logger.info(f"Received /storage command from user: {user.id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first.")
        return

    username = context.user_data.get('username', f'User_{user.id}')
    logger.info(f"Fetching storage info for user: {username} (ID: {user.id})")
    await update.message.reply_text("⏳ Fetching storage information...")

    try:
        response = requests.get(
            f"{API_BASE_URL.rstrip('/')}/storage",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15
        )
        response.raise_for_status()

        storage_data = response.json()
        logger.info(f"Storage API Response for user {user.id}: {storage_data}")

        # Extract storage details
        total_storage_gb = storage_data.get("total_storage_gb", 0)
        used_storage_gb = storage_data.get("used_storage_gb", 0)
        free_storage_gb = storage_data.get("free_storage_gb", 0)
        individual_storages = storage_data.get("storages", [])

        # Format the message (using plain text for simplicity)
        message_lines = ["📊 Overall Storage"]
        message_lines.append(f"Total: {total_storage_gb:.2f} GB")
        message_lines.append(f"Used: {used_storage_gb:.2f} GB")
        message_lines.append(f"Free: {free_storage_gb:.2f} GB")

        if individual_storages:
             message_lines.append("\n📋 Details per Drive")
             for i, storage in enumerate(individual_storages):
                 provider = storage.get('provider', 'Unknown')
                 drive_num = storage.get('drive_number', i+1)
                 limit_gb = storage.get('storage_limit_gb', 0)
                 used_gb = storage.get('used_storage_gb', 0)
                 free_gb = storage.get('free_storage_gb', 0)
                 message_lines.append(f"- {provider} #{drive_num}: Used {used_gb:.2f}/{limit_gb:.2f} GB (Free: {free_gb:.2f} GB)")

        message = "\n".join(message_lines)
        await update.message.reply_text(message) # Send as plain text

    except requests.exceptions.Timeout:
        logger.error(f"API request timed out fetching storage info for user {user.id}")
        await update.message.reply_text("❌ Failed to retrieve storage info: The request timed out.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve storage info for user {user.id}: {e}")
        error_detail = "Connection Error"; status_code = None
        if e.response is not None:
            status_code = e.response.status_code
            try: error_detail = e.response.json().get("detail", e.response.text)
            except ValueError: error_detail = e.response.text[:200]
        logger.error(f"API Response (Status {status_code}): {error_detail}")
        await update.message.reply_text(f"❌ Failed to retrieve storage information: {error_detail}")
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching storage info for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred while fetching storage info.")


# --- LLM Handlers ---
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /ask command, sending the query and user context to the backend."""
    user = update.effective_user
    logger.info(f"Received /ask command from user: {user.id}")

    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first to use the Ask AI feature.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a question after /ask.\nExample: `/ask What is Syncly?`")
        return
    query = " ".join(context.args).strip()

    # Use Telegram ID from user_data if available, otherwise use current user ID
    telegram_user_id = context.user_data.get("telegram_id", str(user.id))
    username = context.user_data.get('username', f'User_{user.id}')
    logger.info(f"User {username} (TG_ID: {telegram_user_id}) asking: '{query}'")

    thinking_message = await update.message.reply_text("🧠 Asking Syncly AI (this may take a moment)...")

    try:
        headers = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}
        payload = {"question": query, "user_id": telegram_user_id}

        response = requests.post(
            f"{API_BASE_URL.rstrip('/')}/llm/ask",
            headers=headers,
            json=payload,
            timeout=90 # Long timeout for potentially complex LLM calls
        )
        response.raise_for_status()

        if response.headers.get('content-type') == 'application/json':
             answer_data = response.json()
             answer = answer_data.get("response", "Sorry, I couldn't get a proper response from the AI.")
             await thinking_message.edit_text(f"🤖 {answer}")
        else:
             logger.error(f"LLM Ask API response was not JSON: {response.text[:200]}")
             await thinking_message.edit_text("❌ Failed to get a valid response from the AI (Invalid Format).")

    except requests.exceptions.Timeout:
        logger.error(f"LLM Ask API request timed out for user {user.id}")
        await thinking_message.edit_text("❌ The request to the AI timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        logger.error(f"LLM Ask API request failed for user {user.id}: {e}")
        error_detail = "Connection Error"; status_code = None
        if e.response is not None:
            status_code = e.response.status_code
            try: error_detail = e.response.json().get("detail", e.response.text)
            except ValueError: error_detail = e.response.text[:200]
        logger.error(f"API Response (Status {status_code}): {error_detail}")
        await thinking_message.edit_text(f"❌ Failed to reach the AI service: {error_detail}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during /ask for user {user.id}: {e}", exc_info=True)
        await thinking_message.edit_text(f"⚠️ An unexpected error occurred while asking the AI.")


async def reset_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resets the LLM conversation memory for the user."""
    user = update.effective_user
    logger.info(f"Received /reset command from user: {user.id}")

    # Optional: Check auth
    # jwt = context.user_data.get("jwt")
    # if not jwt: await update.message.reply_text("❌ Please /login first."); return

    telegram_user_id = str(user.id) # Use current user's ID for reset request
    username = context.user_data.get('username', f'User_{user.id}')
    logger.info(f"Resetting memory for user: {username} (ID: {user.id})")

    try:
        # headers = {"Authorization": f"Bearer {jwt}"} # Add if reset endpoint requires auth
        payload = {"user_id": telegram_user_id}
        response = requests.post(
            f"{API_BASE_URL.rstrip('/')}/llm/reset",
            # headers=headers,
            json=payload,
            timeout=10
        )
        response.raise_for_status()

        if response.headers.get('content-type') == 'application/json':
            reset_data = response.json()
            await update.message.reply_text(reset_data.get("message", "🧠 AI conversation memory reset!"))
        else:
            logger.error(f"LLM Reset API response was not JSON: {response.text[:200]}")
            await update.message.reply_text("❌ Could not reset memory (Invalid Response).")

    except requests.exceptions.Timeout:
        logger.error(f"LLM Reset API request timed out for user {user.id}")
        await update.message.reply_text("❌ Failed to reset memory: The request timed out.")
    except requests.exceptions.RequestException as e:
        logger.error(f"LLM Reset API request failed for user {user.id}: {e}")
        error_detail = "Connection Error"; status_code = None
        if e.response is not None:
            status_code = e.response.status_code
            try: error_detail = e.response.json().get("detail", e.response.text)
            except ValueError: error_detail = e.response.text[:200]
        logger.error(f"API Response (Status {status_code}): {error_detail}")
        await update.message.reply_text(f"❌ Failed to reach the AI service for reset: {error_detail}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during /reset for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ An unexpected error occurred while resetting memory.")

# --- End LLM Handlers ---

# --- Main Bot Setup ---

def main():
    """Start the bot."""
    logger.info("Starting Syncly Bot...")

    # Create the Application instance
    builder = Application.builder().token(TOKEN)

    # Optional: Add persistence if needed later
    # from telegram.ext import PicklePersistence
    # persistence = PicklePersistence(filepath="syncly_bot_persistence")
    # builder.persistence(persistence)

    app = builder.build()

    # --- Register Handlers ---
    # Core Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("logout", logout))

    # File Management Commands
    app.add_handler(CommandHandler("addbucket", add_drive))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("more", more_files))
    app.add_handler(CommandHandler("exitlist", exit_listing))
    app.add_handler(CommandHandler("search", search_file))
    # app.add_handler(CommandHandler("download", download_file)) # Keep disabled
    app.add_handler(CommandHandler("storage", storage_info))

    # LLM Commands
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("reset", reset_memory))

    # Message Handlers
    # Handle document uploads (must be after commands)
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, upload_file))
    # Handle text messages that are likely JWT tokens (must be last text handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_jwt))

    logger.info("Handlers added.")
    print("🤖 Syncly Bot is running...")

    # Run the bot
    app.run_polling(allowed_updates=Update.ALL_TYPES) # Process all update types

if __name__ == "__main__":
    main()
# --- END OF FILE synclybot.py ---