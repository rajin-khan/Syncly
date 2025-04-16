# --- START OF FILE synclybot.py ---

import logging
import requests
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import os
import mimetypes
import re
from telegram.ext import ApplicationBuilder, ContextTypes

# Replace with your BotFather Token
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7728489108:AAEARmLHOsCUTBpGEZ03-Ol53SNLKTPcROI") # Use environment variable

# Syncly API URL
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000") # Use environment variable

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
    # Improved regex to handle more cases and replace with underscore
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename)
    # Remove leading/trailing whitespace/dots
    sanitized = sanitized.strip(" .")
    # Replace multiple underscores with a single one
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized if sanitized else "downloaded_file" # Ensure not empty

async def start(update: Update, context: CallbackContext) -> None:
    logger.info(f"Received /start command from user: {update.message.from_user.username} (ID: {update.message.from_user.id})")
    # Check if user is already logged in
    jwt = context.user_data.get("jwt")
    if jwt:
        username = context.user_data.get("username", "there")
        welcome_message = f"Hi {username}! You are logged in. "
    else:
         welcome_message = "Hi! I'm the Syncly Bot. "

    await update.message.reply_text(
        welcome_message + "My commands are:\n"
        "/login - Log in to your account\n"
        "/addbucket <bucketType> - Add a new storage bucket (GoogleDrive or Dropbox)\n"
        "/ask <your question> - Ask Syncly AI any question (aware of your files)\n"
        "/reset - Manually reset Syncly AI's memory\n"
        "/storage - View Total Storage Information\n"
        "/search <fileName> - Find a specific file by name\n"
        "/list [limit] - List your files (default 10)\n"
        "/upload - Send a file to upload\n"
        #"/download <file_name> - Download a file\n" # Download via API might be complex for bot
        "/logout - Log out and end your session\n"
    )

async def login(update: Update, context: CallbackContext) -> None:
    """Guides the user to log in via the web portal."""
    logger.info(f"Received /login command from user: {update.message.from_user.id}")
    login_url = f"{API_BASE_URL}/static/login.html"
    await update.message.reply_text(
        f"Please log in or register via the web portal:\n{login_url}\n\n"
        "After logging in on the web, copy the JWT shown and paste it back here in the chat."
    )

async def logout(update: Update, context: CallbackContext) -> None:
    """Logs out the user by clearing their session data."""
    user_id = update.message.from_user.id
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
    jwt_input = update.message.text.strip()
    user_id = update.message.from_user.id
    username = update.message.from_user.username or f"User_{user_id}" # Handle missing username

    logger.info(f"Received potential JWT from user: {username} (ID: {user_id})")

    # Basic JWT format check (3 parts separated by dots)
    if not re.match(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$", jwt_input):
        # Check if it's a command or regular text the user intended to send
        # If user was previously prompted to log in, maybe assume it's JWT attempt.
        # Otherwise, might ignore or reply with generic help.
        # For now, we assume any non-command text after /login is a JWT attempt.
        # We could add state tracking in context.user_data if needed.
        logger.info("Input doesn't look like a JWT format. Ignoring.")
        # Avoid replying here unless we are sure it was a JWT attempt
        # await update.message.reply_text("That doesn't look like a valid JWT format.")
        return

    # Attempt to delete the user's message containing the JWT for security
    try:
        await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        logger.info(f"Deleted JWT message from chat for user {user_id}")
    except Exception as e:
        logger.warning(f"Could not delete JWT message for user {user_id}: {e}")
        await update.message.reply_text("⚠️ For security, please delete the message containing your token manually.")


    logger.info(f"Attempting to validate JWT for user {username} (ID: {user_id})")
    # Log only first/last few chars of JWT
    logger.debug(f"JWT Snippet: {jwt_input[:10]}...{jwt_input[-10:]}")

    try:
        # Validate the JWT with the backend
        api_url = f"{API_BASE_URL}/validate-token"
        response = requests.post(api_url, params={"token": jwt_input}) # Send token as query param

        response.raise_for_status()  # Raise an exception for HTTP errors (4xx, 5xx)

        # Extract the username from the API response
        api_username = response.json().get("username")
        if not api_username:
             raise ValueError("API did not return a username from token.")

        # Store JWT and username in user_data
        context.user_data["jwt"] = jwt_input
        context.user_data["username"] = api_username
        # Store telegram user id mapping? (Might be useful elsewhere)
        context.user_data["telegram_id"] = user_id

        logger.info(f"JWT validation successful for user {api_username} (ID: {user_id})")
        await update.message.reply_text(f"✅ Login successful! Welcome, {api_username}. You can now use other commands like /ask or /list.")

    except requests.exceptions.RequestException as e:
        logger.error(f"JWT validation API request failed for user {user_id}: {e}")
        error_detail = "Connection Error"
        if e.response is not None:
            try:
                error_detail = e.response.json().get("detail", e.response.text)
            except ValueError: # If response is not JSON
                error_detail = e.response.text
        logger.error(f"API Response: {error_detail}")
        await update.message.reply_text(f"❌ Login failed. The token seems invalid or the API is unreachable. ({error_detail}). Please /login again.")
    except ValueError as e:
         logger.error(f"JWT validation error (likely API response issue) for user {user_id}: {e}")
         await update.message.reply_text("❌ Login failed. Could not process the response from the server.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during JWT handling for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred during login. Please try again later.")


async def add_drive(update: Update, context: CallbackContext) -> None:
    """Adds a new drive (GoogleDrive or Dropbox)."""
    user_id = update.message.from_user.id
    logger.info(f"Received /addbucket command from user: {user_id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first before adding a bucket.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /addbucket <DriveType>\nExample: `/addbucket GoogleDrive` or `/addbucket Dropbox`")
        return

    drive_type = context.args[0].strip()
    # Case-insensitive check and normalize
    if drive_type.lower() == "googledrive":
        drive_type = "GoogleDrive"
    elif drive_type.lower() == "dropbox":
        drive_type = "Dropbox"
    else:
        await update.message.reply_text("❌ Invalid drive type. Choose 'GoogleDrive' or 'Dropbox'.")
        return

    username = context.user_data.get('username', f'User_{user_id}')
    logger.info(f"Attempting to add drive: {drive_type} for user: {username} (ID: {user_id})")
    await update.message.reply_text(f"⏳ Adding {drive_type}. This may require you to authorize Syncly in your browser. Please follow the instructions provided by the API...")

    try:
        # Send a request to the API to add the drive
        response = requests.post(
            f"{API_BASE_URL}/drives",
            json={"drive_type": drive_type},
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()  # Raise an exception for HTTP errors

        drive_data = response.json()
        logger.info(f"Add drive API response for user {user_id}: {drive_data}")

        reply_message = drive_data.get("message", f"✅ {drive_type} added successfully!")
        # Include potential auth URLs if provided by the API
        if "auth_url" in drive_data:
            reply_message += f"\nPlease visit this URL to authorize: {drive_data['auth_url']}"

        await update.message.reply_text(reply_message)

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to add drive for user {user_id}: {e}")
        error_detail = "Connection Error"
        if e.response is not None:
             try:
                 error_detail = e.response.json().get("detail", e.response.text)
             except ValueError:
                 error_detail = e.response.text
             # Handle specific errors like timeout for Dropbox auth
             if e.response.status_code == 408: # Timeout
                  error_detail = "Authorization timed out. Please try `/addbucket Dropbox` again and complete the steps in your browser promptly."

        logger.error(f"API Response: {error_detail}")
        await update.message.reply_text(f"❌ Failed to add drive. {error_detail}")
    except Exception as e:
        logger.error(f"An unexpected error occurred adding drive for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred while adding the drive.")


# --- List Files Handlers ---
async def list_files(update: Update, context: CallbackContext) -> None:
    """Lists stored files with names, providers, and links."""
    user_id = update.message.from_user.id
    logger.info(f"Received /list command from user: {user_id}")
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
                await update.message.reply_text("❌ Please provide a positive number for the limit (max 100).")
                return
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Invalid limit. Usage: /list [number_of_files]")
            return

    # Initialize or reset offset for a new /list command
    context.user_data["list_offset"] = 0
    context.user_data["list_limit"] = limit
    username = context.user_data.get('username', f'User_{user_id}')

    await update.message.reply_text(f"⏳ Fetching first {limit} files...")
    await fetch_and_display_files(update, context, is_continuation=False)

async def more_files(update: Update, context: CallbackContext) -> None:
    """Fetches the next set of files."""
    user_id = update.message.from_user.id
    logger.info(f"Received /more command from user: {user_id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first.")
        return

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
    jwt = context.user_data["jwt"]
    offset = context.user_data["list_offset"]
    limit = context.user_data["list_limit"]
    user_id = update.message.from_user.id
    username = context.user_data.get('username', f'User_{user_id}')

    try:
        logger.info(f"Fetching files for user: {username} (ID: {user_id}) with limit: {limit}, offset: {offset}")
        response = requests.get(
            f"{API_BASE_URL}/viewfiles",
            params={"limit": limit, "offset": offset},
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()

        files = response.json()
        logger.debug(f"API Response for files: {files}") # Log file list for debug

        if not files:
            if not is_continuation: # First /list call resulted in no files
                 await update.message.reply_text("📂 No files found in your connected drives.")
            else: # /more call resulted in no more files
                await update.message.reply_text("✅ No more files to show.")
            # Clear pagination state as we reached the end
            context.user_data.pop("list_offset", None)
            context.user_data.pop("list_limit", None)
            return

        # Format file list
        file_list_text = []
        current_file_number = offset + 1
        for file in files:
            size_mb = "Unknown"
            try:
                # Safely convert size string to float for calculation
                size_bytes_str = file.get('size', 'Unknown')
                if size_bytes_str != 'Unknown' and size_bytes_str.isdigit():
                     size_bytes = int(size_bytes_str)
                     if size_bytes < 1024 * 1024: # Show KB for small files
                         size_mb = f"{size_bytes / 1024:.1f} KB"
                     else:
                         size_mb = f"{size_bytes / (1024*1024):.2f} MB"
            except (ValueError, TypeError):
                pass # Keep size_mb as "Unknown"

            provider = file.get('provider', 'Unknown')
            name = file.get('name', 'Unknown File')
            # Basic link, download might not work directly for users easily
            # path = file.get('path', '#') # Use # if no path
            # file_list_text.append(f"{current_file_number}. 📄 {name} ({provider}, {size_mb})\n   Link: {path}")
            # Simplified view without link for now
            file_list_text.append(f"{current_file_number}. 📄 {name} ({provider}, {size_mb})")
            current_file_number += 1

        start_num = offset + 1
        end_num = offset + len(files)
        message = f"📂 Files {start_num}-{end_num}:\n\n" + "\n".join(file_list_text)

        # Check if there might be more files to fetch
        if len(files) == limit:
            message += "\n\nℹ️ Type /more to see the next set, or /exitlist to stop."
        else:
            message += "\n\n✅ Reached the end of your files."
            # Clear pagination state as we reached the end
            context.user_data.pop("list_offset", None)
            context.user_data.pop("list_limit", None)

        await update.message.reply_text(message)

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve files for user {user_id}: {e}")
        error_detail = "Connection Error"
        if e.response is not None:
             try:
                 error_detail = e.response.json().get("detail", e.response.text)
             except ValueError:
                 error_detail = e.response.text
        logger.error(f"API Response: {error_detail}")
        await update.message.reply_text(f"❌ Failed to retrieve files: {error_detail}")
        # Clear pagination state on error
        context.user_data.pop("list_offset", None)
        context.user_data.pop("list_limit", None)
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching files for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred while fetching files.")
        # Clear pagination state on error
        context.user_data.pop("list_offset", None)
        context.user_data.pop("list_limit", None)

async def exit_listing(update: Update, context: CallbackContext) -> None:
    """Exits the file listing mode by clearing pagination state."""
    user_id = update.message.from_user.id
    logger.info(f"Received /exitlist command from user: {user_id}")
    if "list_offset" in context.user_data or "list_limit" in context.user_data:
        context.user_data.pop("list_offset", None)
        context.user_data.pop("list_limit", None)
        await update.message.reply_text("✅ Exited file listing mode.")
    else:
        await update.message.reply_text("ℹ️ You weren't in file listing mode.")
# --- End List Files Handlers ---

async def search_file(update: Update, context: CallbackContext) -> None:
    """Searches for a file by name across all buckets."""
    user_id = update.message.from_user.id
    logger.info(f"Received /search command from user: {user_id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /search <filename>")
        return

    filename_query = " ".join(context.args)
    username = context.user_data.get('username', f'User_{user_id}')
    logger.info(f"Searching for file '{filename_query}' for user: {username} (ID: {user_id})")
    await update.message.reply_text(f"⏳ Searching for '{filename_query}'...")

    try:
        # Use the API's search endpoint (fetch max 5 results for display)
        response = requests.get(
            f"{API_BASE_URL}/search_files",
            params={"query": filename_query, "limit": 5, "exact_match": False}, # Find files containing the query
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()

        files = response.json()
        logger.info(f"Search API Response for user {user_id}: {files}")

        if files:
            results_list = []
            for i, file in enumerate(files):
                size_mb = "Unknown"
                try:
                    size_bytes_str = file.get('size', 'Unknown')
                    if size_bytes_str != 'Unknown' and size_bytes_str.isdigit():
                        size_bytes = int(size_bytes_str)
                        size_mb = f"{size_bytes / (1024*1024):.2f} MB"
                except (ValueError, TypeError):
                    pass

                provider = file.get('provider', 'Unknown')
                name = file.get('name', 'Unknown File')
                # path = file.get('path', '#')
                # results_list.append(f"{i+1}. 📄 {name} ({provider}, {size_mb})\n   Link: {path}")
                results_list.append(f"{i+1}. 📄 {name} ({provider}, {size_mb})")

            message = f"✅ Found matching files for '{filename_query}':\n\n" + "\n".join(results_list)
            await update.message.reply_text(message)
        else:
            await update.message.reply_text(f"❌ No files found matching '{filename_query}' in your Syncly drives.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to search for file '{filename_query}' for user {user_id}: {e}")
        error_detail = "Connection Error"
        if e.response is not None:
             try:
                 error_detail = e.response.json().get("detail", e.response.text)
             except ValueError:
                 error_detail = e.response.text
        logger.error(f"API Response: {error_detail}")
        await update.message.reply_text(f"❌ Failed to search for file: {error_detail}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during search for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred during search.")


async def upload_file(update: Update, context: CallbackContext) -> None:
    """Handles file uploads sent directly as documents."""
    user_id = update.message.from_user.id
    logger.info(f"Received a document upload from user: {user_id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first before uploading files.")
        return

    if not update.message.document:
        # This should ideally not happen if triggered by filters.Document.ALL
        await update.message.reply_text("❓ Please send the file you want to upload.")
        return

    doc = update.message.document
    original_filename = doc.file_name or "untitled_upload"
    sanitized_filename = sanitize_filename(original_filename)
    file_size = doc.file_size # Size in bytes

    await update.message.reply_text(f"⏳ Receiving '{original_filename}' ({file_size / (1024*1024):.2f} MB)...")

    # Define the path to save the file locally temporarily
    # Include user_id in path to prevent conflicts if multiple users upload same filename
    temp_dir = os.path.join("downloads", str(user_id))
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, sanitized_filename)

    file_id = doc.file_id
    username = context.user_data.get('username', f'User_{user_id}')

    try:
        # Get the file object from Telegram
        tg_file = await context.bot.get_file(file_id)

        # Download the file to the temporary path
        await tg_file.download_to_drive(temp_file_path)
        logger.info(f"File '{original_filename}' downloaded to temporary path: {temp_file_path}")

        await update.message.reply_text("⬆️ Uploading to Syncly storage...")

        # Upload the downloaded file to the backend API
        with open(temp_file_path, "rb") as f:
            files_payload = {"file": (original_filename, f, doc.mime_type)} # Send original name
            response = requests.post(
                f"{API_BASE_URL}/files/upload",
                files=files_payload,
                headers={"Authorization": f"Bearer {jwt}"}
            )
            response.raise_for_status()  # Raise an exception for HTTP errors

        upload_result = response.json()
        logger.info(f"File upload API response for user {user_id}: {upload_result}")
        await update.message.reply_text(upload_result.get("message", "✅ File uploaded successfully!"))

    except requests.exceptions.RequestException as e:
        logger.error(f"File upload API request failed for user {user_id}: {e}")
        error_detail = "Connection Error"
        if e.response is not None:
             try:
                 error_detail = e.response.json().get("detail", e.response.text)
             except ValueError:
                 error_detail = e.response.text
        logger.error(f"API Response: {error_detail}")
        await update.message.reply_text(f"❌ File upload failed: {error_detail}")
    except Exception as e:
        logger.error(f"Error during file upload process for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred during the file upload.")
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Temporary file {temp_file_path} cleaned up.")
                # Attempt to remove the user-specific directory if empty
                # Be cautious with rmdir, ensure it's the correct directory
                if not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
                    logger.info(f"Removed empty temporary directory: {temp_dir}")
            except OSError as e:
                logger.warning(f"Could not clean up temporary file/directory {temp_file_path} or {temp_dir}: {e}")

async def download_file(update: Update, context: CallbackContext) -> None:
    """Downloads a file from Syncly (Placeholder/Complex)."""
    # Note: Direct download via bot might be complex due to file size limits, auth, etc.
    # It might be better to provide a link from /list or /search for user to download via browser.
    await update.message.reply_text("ℹ️ File download via bot is not fully implemented. Please use /search or /list to find file links.")
    # --- Implementation kept for reference ---
    # jwt = context.user_data.get("jwt")
    # if not jwt:
    #     await update.message.reply_text("❌ Please log in first using /login.")
    #     return

    # if len(context.args) < 1:
    #     await update.message.reply_text("Usage: /download <file_name>")
    #     return

    # file_name = " ".join(context.args) # Handle names with spaces
    # sanitized_file_name = sanitize_filename(file_name) # Sanitize if needed by API

    # user_id = update.message.from_user.id
    # username = context.user_data.get('username', f'User_{user_id}')
    # logger.info(f"Attempting download for file: {file_name} for user: {username} (ID: {user_id})")
    # await update.message.reply_text(f"⏳ Requesting download for '{file_name}'...")

    # try:
    #     response = requests.get(
    #         f"{API_BASE_URL}/files/download",
    #         params={"file_name": file_name}, # Send original name? API needs to handle search/lookup
    #         headers={"Authorization": f"Bearer {jwt}"},
    #         stream=True # Use stream for potentially large files
    #     )
    #     response.raise_for_status()

    #     # Extract filename from Content-Disposition header if available
    #     content_disposition = response.headers.get('content-disposition')
    #     final_filename = sanitized_file_name # Default
    #     if content_disposition:
    #         disp_filename = re.findall("filename=\"?(.+?)\"?$", content_disposition)
    #         if disp_filename:
    #             final_filename = sanitize_filename(disp_filename[0])

    #     # Save the file locally
    #     temp_dir = os.path.join("downloads", str(user_id))
    #     os.makedirs(temp_dir, exist_ok=True)
    #     local_file_path = os.path.join(temp_dir, final_filename)

    #     with open(local_file_path, "wb") as f:
    #         for chunk in response.iter_content(chunk_size=8192):
    #             f.write(chunk)
    #     logger.info(f"File '{final_filename}' downloaded to: {local_file_path}")

    #     # Send the file to the user
    #     await update.message.reply_document(
    #         document=InputFile(local_file_path, filename=final_filename),
    #         caption=f"✅ Here is your file: {final_filename}"
    #     )

    # except requests.exceptions.RequestException as e:
    #     logger.error(f"File download API failed for file '{file_name}' user {user_id}: {e}")
    #     error_detail = "Connection Error or File Not Found"
    #     if e.response is not None:
    #          try:
    #              error_detail = e.response.json().get("detail", e.response.text)
    #          except ValueError:
    #              error_detail = e.response.text
    #     logger.error(f"API Response: {error_detail}")
    #     await update.message.reply_text(f"❌ Download failed: {error_detail}")
    # except Exception as e:
    #     logger.error(f"An unexpected error occurred during download for user {user_id}: {e}", exc_info=True)
    #     await update.message.reply_text("❌ An unexpected error occurred during download.")
    # finally:
    #     # Clean up the temporary downloaded file
    #     if 'local_file_path' in locals() and os.path.exists(local_file_path):
    #          try:
    #              os.remove(local_file_path)
    #              logger.info(f"Cleaned up downloaded temp file: {local_file_path}")
    #              # Attempt to remove dir if empty
    #              if not os.listdir(temp_dir):
    #                 os.rmdir(temp_dir)
    #                 logger.info(f"Removed empty download directory: {temp_dir}")
    #          except OSError as e:
    #              logger.warning(f"Could not clean up temp download {local_file_path} or {temp_dir}: {e}")


async def storage_info(update: Update, context: CallbackContext) -> None:
    """Retrieves and displays storage information for the user."""
    user_id = update.message.from_user.id
    logger.info(f"Received /storage command from user: {user_id}")
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first.")
        return

    username = context.user_data.get('username', f'User_{user_id}')
    logger.info(f"Fetching storage info for user: {username} (ID: {user_id})")
    await update.message.reply_text("⏳ Fetching storage information...")

    try:
        # Call the API to get storage information
        response = requests.get(
            f"{API_BASE_URL}/storage",
            headers={"Authorization": f"Bearer {jwt}"}
        )
        response.raise_for_status()

        storage_data = response.json()
        logger.info(f"Storage API Response for user {user_id}: {storage_data}")

        # Extract storage details
        total_storage_gb = storage_data.get("total_storage_gb", 0)
        used_storage_gb = storage_data.get("used_storage_gb", 0)
        free_storage_gb = storage_data.get("free_storage_gb", 0)
        individual_storages = storage_data.get("storages", [])

        # Format the message
        message_lines = [f"📊 **Overall Storage**"]
        message_lines.append(f"Total: {total_storage_gb:.2f} GB")
        message_lines.append(f"Used: {used_storage_gb:.2f} GB")
        message_lines.append(f"Free: {free_storage_gb:.2f} GB")

        if individual_storages:
             message_lines.append("\n📋 **Details per Drive**")
             for i, storage in enumerate(individual_storages):
                 provider = storage.get('provider', 'Unknown')
                 drive_num = storage.get('drive_number', i+1)
                 limit_gb = storage.get('storage_limit_gb', 0)
                 used_gb = storage.get('used_storage_gb', 0)
                 free_gb = storage.get('free_storage_gb', 0)
                 message_lines.append(f"- {provider} #{drive_num}: Used {used_gb:.2f}/{limit_gb:.2f} GB (Free: {free_gb:.2f} GB)")

        message = "\n".join(message_lines)
        # Use MarkdownV2 for bold, requires escaping special chars like '.'
        # Or stick to simple Markdown
        await update.message.reply_text(message, parse_mode="Markdown")

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to retrieve storage info for user {user_id}: {e}")
        error_detail = "Connection Error"
        if e.response is not None:
             try:
                 error_detail = e.response.json().get("detail", e.response.text)
             except ValueError:
                 error_detail = e.response.text
        logger.error(f"API Response: {error_detail}")
        await update.message.reply_text(f"❌ Failed to retrieve storage information: {error_detail}")
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching storage info for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred while fetching storage info.")


# --- LLM Handlers ---
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /ask command, sending the query and user context to the backend."""
    user_id = update.message.from_user.id
    logger.info(f"Received /ask command from user: {user_id}")

    # --- Authentication Check ---
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first to use the Ask AI feature.")
        return
    # --- End Authentication Check ---

    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Please provide a question after /ask.\nExample: `/ask What is Syncly?`")
        return

    telegram_user_id = str(user_id) # Use Telegram ID for memory tracking
    username = context.user_data.get('username', f'User_{user_id}')
    logger.info(f"User {username} (ID: {user_id}) asking: '{query}'")
    await update.message.reply_text("🧠 Asking Syncly AI (this may take a moment)...")

    try:
        # --- Send JWT in Headers ---
        headers = {"Authorization": f"Bearer {jwt}"}
        # --- End Send JWT ---

        response = requests.post(
            f"{API_BASE_URL}/llm/ask",
            headers=headers, # Add headers here
            json={
                "question": query,
                "user_id": telegram_user_id # Still send telegram ID for memory mapping
            }
        )
        response.raise_for_status() # Check for HTTP errors

        if response.ok:
            answer = response.json().get("response", "Sorry, I couldn't get a proper response.")
            # Send the raw response text
            await update.message.reply_text(f"🤖 {answer}")
        else:
            # This part might not be reached if raise_for_status() catches the error
            error_detail = response.json().get("detail", "Unknown error from LLM service")
            logger.error(f"LLM Ask API failed for user {user_id} with status {response.status_code}: {error_detail}")
            await update.message.reply_text(f"❌ Failed to get a response from the AI: {error_detail}")

    except requests.exceptions.RequestException as e:
        logger.error(f"LLM Ask API request failed for user {user_id}: {e}")
        error_detail = "Connection Error"
        if e.response is not None:
             try:
                 error_detail = e.response.json().get("detail", e.response.text)
             except ValueError:
                 error_detail = e.response.text
        logger.error(f"API Response: {error_detail}")
        await update.message.reply_text(f"❌ Failed to reach the AI service: {error_detail}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during /ask for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ An unexpected error occurred: {e}")

async def reset_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resets the LLM conversation memory for the user."""
    user_id = update.message.from_user.id
    logger.info(f"Received /reset command from user: {user_id}")

    # --- Authentication Check (Optional but good practice) ---
    jwt = context.user_data.get("jwt")
    if not jwt:
        await update.message.reply_text("❌ Please /login first.")
        return
    # --- End Authentication Check ---

    telegram_user_id = str(user_id)
    username = context.user_data.get('username', f'User_{user_id}')
    logger.info(f"Resetting memory for user: {username} (ID: {user_id})")

    try:
         # --- Send JWT if required by the reset endpoint (currently not, but could be added) ---
        headers = {"Authorization": f"Bearer {jwt}"}

        response = requests.post(
            f"{API_BASE_URL}/llm/reset",
            # headers=headers # Add if reset endpoint requires auth
            json={"user_id": telegram_user_id} # API uses telegram_user_id to find memory slot
        )
        response.raise_for_status() # Check for HTTP errors

        if response.ok:
            await update.message.reply_text("🧠 AI conversation memory reset!")
        else:
            # This part might not be reached if raise_for_status() catches the error
            error_detail = response.json().get("detail", "Could not reset memory")
            logger.error(f"LLM Reset API failed for user {user_id} with status {response.status_code}: {error_detail}")
            await update.message.reply_text(f"❌ Could not reset memory: {error_detail}")

    except requests.exceptions.RequestException as e:
        logger.error(f"LLM Reset API request failed for user {user_id}: {e}")
        error_detail = "Connection Error"
        if e.response is not None:
             try:
                 error_detail = e.response.json().get("detail", e.response.text)
             except ValueError:
                 error_detail = e.response.text
        logger.error(f"API Response: {error_detail}")
        await update.message.reply_text(f"❌ Failed to reach the AI service for reset: {error_detail}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during /reset for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ An unexpected error occurred: {e}")

# --- End LLM Handlers ---


def main():
    """Start the bot."""
    logger.info("Starting Syncly Bot...")

    # Use ApplicationBuilder for modern python-telegram-bot setup
    builder = Application.builder().token(TOKEN)
    # Potentially add persistence here if needed later
    # from telegram.ext import PicklePersistence
    # persistence = PicklePersistence(filepath="syncly_bot_persistence")
    # builder.persistence(persistence)

    app = builder.build()

    # --- Add Handlers ---
    # Core Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("logout", logout))

    # File Management Commands
    app.add_handler(CommandHandler("addbucket", add_drive))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("more", more_files))
    app.add_handler(CommandHandler("exitlist", exit_listing)) # Changed from /exit
    app.add_handler(CommandHandler("search", search_file))
    # app.add_handler(CommandHandler("download", download_file)) # Disabled for now
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
    app.run_polling(allowed_updates=Update.ALL_TYPES) # Process all update types

if __name__ == "__main__":
    # Load .env file if it exists
    from dotenv import load_dotenv
    load_dotenv()
    # Check required environment variables
    if not TOKEN or TOKEN == "YOUR_BOTFATHER_TOKEN_HERE":
        logger.critical("TELEGRAM_BOT_TOKEN environment variable not set or is default.")
        exit("Error: Telegram Bot Token not configured.")
    if not API_BASE_URL:
        logger.critical("API_BASE_URL environment variable not set.")
        exit("Error: API Base URL not configured.")

    main()
# --- END OF FILE synclybot.py ---