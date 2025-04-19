# --- START OF FILE synclybot.py ---

import logging
import requests
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup # Added Inline buttons
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
# Removed CallbackQueryHandler as buttons are now URL based
import os
import mimetypes
import re
from datetime import datetime, timedelta # Need datetime
from telegram.ext import ApplicationBuilder, ContextTypes
from dotenv import load_dotenv

# Load environment variables at the top
load_dotenv()

# --- Environment Variable Checks ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL")

# Configure logging FIRST
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Critical environment variable checks AFTER logging is configured
if not TOKEN: logger.critical("FATAL ERROR: TELEGRAM_BOT_TOKEN missing"); exit("Telegram Token Missing")
if not API_BASE_URL: logger.critical("FATAL ERROR: API_BASE_URL missing"); exit("API Base URL Missing")

# Ensure downloads directory exists
os.makedirs("downloads", exist_ok=True)

# --- Constants ---
LINK_EXPIRY_MINUTES = 5 # How long the login link is valid (for user message)

# --- Helper Functions ---
def sanitize_filename(filename: str) -> str:
    if not filename: return "downloaded_file"
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename); sanitized = sanitized.strip(" ._")
    sanitized = re.sub(r'_+', '_', sanitized); return sanitized if sanitized else "downloaded_file"


# --- Authentication Check Helper ---
async def check_and_complete_auth(update: Update, context: CallbackContext) -> bool:
    """
    Checks auth status. If JWT exists, returns True. If pending link exists,
    tries to complete it via API. Returns True if auth successful, False otherwise.
    Handles API errors and updates user context.
    """
    # Ensure we have a message context to potentially reply to
    effective_message = update.effective_message
    if not effective_message:
        logger.warning("check_and_complete_auth called without effective_message context.")
        return False # Cannot proceed or reply

    user = update.effective_user
    if not user:
        logger.warning("check_and_complete_auth called without effective_user.")
        return False # Cannot proceed without user info
    telegram_id = str(user.id)

    # 1. Already authenticated?
    if context.user_data.get("jwt"):
        # Optional: Could add a quick /validate-token call here periodically if needed
        return True

    # 2. Pending link exists in context?
    link_id = context.user_data.get('pending_link_id')
    link_expiry_client = context.user_data.get('pending_link_expiry')

    if not link_id:
        # Not logged in, and no pending link found in context
        return False

    # 3. Client-side expiry check (approximate)
    if link_expiry_client and datetime.utcnow() > link_expiry_client:
        logger.info(f"Client-side expiry check failed for link {link_id} (User: {telegram_id}). Clearing state.")
        context.user_data.pop('pending_link_id', None)
        context.user_data.pop('pending_link_expiry', None)
        # Don't reply here, let the calling command prompt for login
        return False

    # 4. Attempt to complete authentication via API
    logger.info(f"Attempting to complete auth via API for link_id: {link_id}, user: {telegram_id}")
    api_url = f"{API_BASE_URL.rstrip('/')}/auth/complete_link"
    payload = {"link_id": link_id, "telegram_id": telegram_id}

    try:
        response = requests.post(api_url, json=payload, timeout=15) # Increased timeout slightly

        # --- Handle API Responses Robustly ---
        if response.status_code == 200:
            auth_data = response.json()
            jwt_token = auth_data.get("access_token")
            username = auth_data.get("username")
            if jwt_token and username:
                context.user_data["jwt"] = jwt_token
                context.user_data["username"] = username
                context.user_data["telegram_id"] = telegram_id # Ensure it's stored/updated
                # Clear pending state on success
                context.user_data.pop('pending_link_id', None)
                context.user_data.pop('pending_link_expiry', None)
                logger.info(f"Auth link completion successful for user {telegram_id} (Username: {username})")
                # Let the original command proceed
                return True # Now authenticated
            else:
                logger.error(f"API status 200 but missing token/username in response for link {link_id}.")
                await effective_message.reply_text("❌ Authentication failed (Invalid server response). Please try /login again.")
                context.user_data.pop('pending_link_id', None); context.user_data.pop('pending_link_expiry', None)
                return False

        elif response.status_code == 400: # Bad Request (Likely means link not validated via web yet)
             logger.warning(f"Auth link {link_id} not validated via web yet for user {telegram_id} (API returned 400).")
             await effective_message.reply_text("⏳ Please complete the login in your web browser first, then try your command again.")
             # Keep pending state for user to complete web step
             return False

        elif response.status_code in [404, 410, 403]: # Not Found, Gone (Expired/Used), Forbidden (ID mismatch)
             error_detail = "Link not found, expired, or invalid."
             try: error_detail = response.json().get("detail", error_detail)
             except ValueError: pass # Ignore if response is not JSON
             logger.warning(f"Auth completion failed ({response.status_code}) for user {telegram_id}, link {link_id}: {error_detail}")
             await effective_message.reply_text(f"❌ Authentication failed: {error_detail}. Please use /login to get a new link.")
             context.user_data.pop('pending_link_id', None); context.user_data.pop('pending_link_expiry', None)
             return False
        else: # Handle other server errors (5xx, etc.)
             error_detail = f"Server error ({response.status_code})"
             try: error_detail = response.json().get("detail", error_detail)
             except ValueError: error_detail = response.text[:150] # Show start of raw response
             logger.error(f"Auth completion failed ({response.status_code}) for user {telegram_id}, link {link_id}: {error_detail}")
             await effective_message.reply_text(f"❌ Authentication failed due to a server issue ({error_detail}). Please try again later.")
             # Clear pending state as link is likely unusable now
             context.user_data.pop('pending_link_id', None); context.user_data.pop('pending_link_expiry', None)
             return False

    except requests.exceptions.Timeout:
        logger.error(f"API timeout during auth completion for link {link_id}, user {telegram_id}")
        await effective_message.reply_text("❌ Authentication check timed out. Please try your command again shortly.")
        # Keep pending state, might be temporary network issue
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"API connection failed during auth completion for link {link_id}, user {telegram_id}: {e}")
        await effective_message.reply_text("❌ Could not connect to authentication server. Please check connection and try again.")
        # Keep pending state, might be temporary network issue
        return False
    except Exception as e:
         logger.error(f"Unexpected error during auth completion for link {link_id}, user {telegram_id}: {e}", exc_info=True)
         await effective_message.reply_text("❌ An unexpected error occurred during authentication. Please try /login again.")
         context.user_data.pop('pending_link_id', None); context.user_data.pop('pending_link_expiry', None)
         return False

# --- API Error Handling Helper ---
async def handle_api_error(e: requests.exceptions.RequestException, update: Update, context: CallbackContext, command_name: str = "operation") -> bool:
     """
     Handles RequestExceptions, specifically checks for 401, clears auth, and informs user.
     Returns True if 401 was handled, False otherwise.
     """
     user_id = update.effective_user.id if update.effective_user else 'unknown'
     effective_message = update.effective_message # Use message context for replies

     if e.response is not None and e.response.status_code == 401:
          logger.warning(f"API call returned 401 (Unauthorized) during '{command_name}' for user {user_id}. Clearing JWT.")
          # Clear authentication state fully
          context.user_data.pop("jwt", None)
          context.user_data.pop("username", None)
          context.user_data.pop('pending_link_id', None)
          context.user_data.pop('pending_link_expiry', None)
          if effective_message:
              await effective_message.reply_text("❌ Your session has expired or is invalid. Please use /login to authenticate again.")
          return True # 401 error was handled
     else:
          # Log other request errors
          status_code = e.response.status_code if e.response is not None else "N/A"
          error_detail = f"Connection Error (Status: {status_code})"
          if e.response is not None:
              try: error_detail = e.response.json().get("detail", f"Error {status_code}")
              except ValueError: error_detail = e.response.text[:200] # Use raw text if not JSON

          logger.error(f"API request failed during '{command_name}' for user {user_id}: {e} | Detail: {error_detail}")
          if effective_message:
               # Provide a user-friendly error message
               await effective_message.reply_text(f"❌ An error occurred while performing the operation: {error_detail}")
          return False # Indicates it was not a 401 error

# --- Command Handlers ---

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/start from {user.username or 'N/A'} (ID: {user.id})")

    # --- Check for successful auth completion *immediately* on /start ---
    # This handles the case where the user clicks the button in login.html
    # which redirects back to the bot with `/start` but no payload.
    # check_and_complete_auth will use the pending_link_id from context if present.
    auth_successful = await check_and_complete_auth(update, context)
    # --- End immediate check ---

    jwt = context.user_data.get("jwt"); username_display = context.user_data.get("username", user.first_name or "there")
    welcome = f"Hi {username_display}! "
    if jwt or auth_successful: # If already logged in OR just completed auth
         welcome += "You are logged in. "
    else:
         welcome += "I'm the Syncly Bot. Use /login to get started. "

    commands = ("Available commands:\n\n🔑 /login - Connect your Syncly account\n\n➕ /addbucket (Type) - Link GoogleDrive or Dropbox\n\n"
               "📊 /storage - Check cloud storage usage\n\n📂 /list (limit) - View files (e.g., /list 20)\n\n"
               "🔍 /search (query) - Find files by name/content\n\n"
               "🤖 /ask (question) - Chat with Syncly AI about your files\n🧠 /reset - Clear AI conversation memory\n\n"
               "⬆️ /upload - Just send a file directly to me to upload\n\n🚪 /logout - Disconnect your account")
    await update.message.reply_text(welcome + commands)

# --- Corrected /login ---
async def login(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; telegram_id = str(user.id); logger.info(f"/login request from user: {telegram_id}")

    # Check if already logged in
    if context.user_data.get("jwt"):
        await update.message.reply_text("ℹ️ You are already logged in. Use /logout first if you wish to switch accounts or re-authenticate.")
        return
    # Check if already waiting for a link validation
    if context.user_data.get("pending_link_id"):
        # Optionally check expiry here too
        await update.message.reply_text("⏳ You already have a pending login link. Please click the link previously sent or wait for it to expire before requesting a new one.")
        return

    api_url = f"{API_BASE_URL.rstrip('/')}/auth/create_link"; payload = {"telegram_id": telegram_id}
    try:
        response = requests.post(api_url, json=payload, timeout=10); response.raise_for_status()
        link_data = response.json(); link_id = link_data.get("link_id"); login_url = link_data.get("login_url")
        if not link_id or not login_url: raise ValueError("Invalid response from link creation API.")

        # Store pending link info in context BEFORE sending message
        context.user_data['pending_link_id'] = link_id
        # Store expiry slightly longer on client to account for delays
        context.user_data['pending_link_expiry'] = datetime.utcnow() + timedelta(minutes=LINK_EXPIRY_MINUTES + 1)

        keyboard = [[InlineKeyboardButton("Log In / Register via Web Portal", url=login_url)]]
        await update.message.reply_text(
            f"🧑🏻‍💻 Click the button below to log in through the secure web portal.\n\n 🎉 If you're registering, click once, come back and click again after registering."
            f"This link will expire in {LINK_EXPIRY_MINUTES} minutes.\n\n"
            f"Once done, return here and use any command (like /storage or /list) to complete the process.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"Sent login button (link_id: {link_id}) to user {telegram_id}")

    except requests.exceptions.RequestException as e:
         logger.error(f"Failed to call /auth/create_link for {telegram_id}: {e}")
         await handle_api_error(e, update, context, "login link generation")
    except Exception as e:
         logger.error(f"Unexpected error during /login for {telegram_id}: {e}", exc_info=True)
         await update.message.reply_text("❌ An error occurred while generating the login link. Please try again later.")

async def logout(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id if update.effective_user else "N/A"; logger.info(f"/logout from user: {user_id}")
    state_cleared = False
    if "jwt" in context.user_data: context.user_data.pop("jwt"); state_cleared = True
    if "username" in context.user_data: context.user_data.pop("username"); state_cleared = True
    if "telegram_id" in context.user_data: context.user_data.pop("telegram_id"); state_cleared = True
    if "pending_link_id" in context.user_data: context.user_data.pop("pending_link_id"); state_cleared = True
    if "pending_link_expiry" in context.user_data: context.user_data.pop("pending_link_expiry"); state_cleared = True
    # Clear listing state too
    if "list_offset" in context.user_data: context.user_data.pop("list_offset"); state_cleared = True
    if "list_limit" in context.user_data: context.user_data.pop("list_limit"); state_cleared = True

    if state_cleared:
        logger.info(f"User {user_id} logged out / session cleared.")
        await update.message.reply_text("✅ You have been logged out and your session data cleared.")
    else: await update.message.reply_text("ℹ️ You were not logged in.")


# --- Commands Requiring Auth (Using the check_and_complete_auth helper) ---

async def add_drive(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/addbucket from user: {user.id if user else '?'}")
    if not user: await update.message.reply_text("Cannot identify user."); return # Should not happen

    # Check auth status, potentially completing link flow
    if not await check_and_complete_auth(update, context):
        await update.message.reply_text("❌ Please use /login first.")
        return
    jwt = context.user_data.get("jwt") # Auth succeeded, get JWT

    # Proceed with command logic...
    if not context.args or len(context.args) < 1: await update.message.reply_text("Usage: /addbucket <GoogleDrive|Dropbox>"); return
    drive_type = context.args[0].strip().lower(); drive_type_norm = ""
    if drive_type == "googledrive": drive_type_norm = "GoogleDrive"
    elif drive_type == "dropbox": drive_type_norm = "Dropbox"
    else: await update.message.reply_text("❌ Invalid drive type."); return
    username = context.user_data.get('username', '?'); logger.info(f"Adding {drive_type_norm} for {username} ({user.id})")
    await update.message.reply_text(f"⏳ Adding {drive_type_norm}... Follow browser prompts if needed.")
    try:
        response = requests.post(f"{API_BASE_URL.rstrip('/')}/drives", json={"drive_type": drive_type_norm}, headers={"Authorization": f"Bearer {jwt}"}, timeout=20) # Increased timeout slightly
        response.raise_for_status()
        drive_data = response.json(); logger.info(f"Add drive response: {drive_data}")
        await update.message.reply_text(drive_data.get("message", "✅ Drive added successfully!"))
    except requests.exceptions.RequestException as e: await handle_api_error(e, update, context, "add drive")
    except Exception as e: logger.error(f"Unexpected error adding drive: {e}", exc_info=True); await update.message.reply_text("❌ An unexpected error occurred while adding the drive.")


async def list_files(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/list from user: {user.id if user else '?'}")
    if not user: await update.message.reply_text("Cannot identify user."); return

    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please use /login first."); return
    # Auth succeeded, proceed...
    limit = 10
    if context.args:
        try: limit = int(context.args[0]); assert 0 < limit <= 100
        except: await update.message.reply_text("❌ Invalid limit (1-100)."); return
    context.user_data["list_offset"] = 0; context.user_data["list_limit"] = limit
    await update.message.reply_text(f"⏳ Fetching first {limit} files..."); await fetch_and_display_files(update, context, False)


async def more_files(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/more from user: {user.id if user else '?'}")
    if not user: await update.message.reply_text("Cannot identify user."); return

    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please use /login first."); return
    # Auth succeeded, proceed...
    offset = context.user_data.get("list_offset"); limit = context.user_data.get("list_limit")
    if offset is None or limit is None: await update.message.reply_text("ℹ️ Use /list first to start viewing files."); return
    context.user_data["list_offset"] = offset + limit
    await update.message.reply_text(f"⏳ Fetching next {limit} files..."); await fetch_and_display_files(update, context, True)


async def fetch_and_display_files(update: Update, context: CallbackContext, is_continuation: bool):
    # This helper assumes auth was checked by the caller
    jwt = context.user_data.get("jwt"); offset = context.user_data.get("list_offset"); limit = context.user_data.get("list_limit")
    user = update.effective_user; username = context.user_data.get('username', f'User_{user.id if user else "?"}')
    effective_message = update.effective_message # Use this for replies

    if not effective_message: logger.error("INTERNAL ERROR: fetch_and_display_files called without message context."); return
    if not jwt: logger.error("INTERNAL ERROR: fetch_and_display_files called without JWT."); await effective_message.reply_text("Error: Authentication missing."); return
    if offset is None or limit is None: logger.error("INTERNAL ERROR: fetch_and_display_files called without pagination state."); await effective_message.reply_text("Error: Listing state lost, please use /list again."); return

    try:
        logger.info(f"Fetching files: user={username} ({user.id}), limit={limit}, offset={offset}")
        response = requests.get(f"{API_BASE_URL.rstrip('/')}/viewfiles", params={"limit": limit, "offset": offset}, headers={"Authorization": f"Bearer {jwt}"}, timeout=25)
        response.raise_for_status()
        files = response.json(); logger.debug(f"API file list response count: {len(files)}")

        if not files:
            msg = "✅ No more files to show." if is_continuation else "📂 No files found in your connected drives."
            await effective_message.reply_text(msg)
            context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None) # Clear state
            return

        lines = []; current_num = offset + 1
        for file in files:
            size_display = "Unknown"; size_bytes = file.get('size');
            if isinstance(size_bytes, int):
                if size_bytes == 0: size_display = "0 B"
                elif size_bytes < 1024: size_display = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024: size_display = f"{size_bytes / 1024:.1f} KB"
                else: size_display = f"{size_bytes / (1024*1024):.2f} MB"
            lines.append(f"{current_num}. 📄 {file.get('name','Unknown File')} ({file.get('provider','?')}, {size_display})"); current_num += 1

        start_num = offset + 1; end_num = offset + len(files)
        message = f"📂 Files {start_num}-{end_num}:\n\n" + "\n".join(lines)

        if len(files) == limit: # Potentially more files exist
            message += "\n\nℹ️ Type /more to see the next set, or /exitlist to stop."
        else: # Reached the end
            message += "\n\n✅ Reached the end of your files."
            context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None) # Clear state

        await effective_message.reply_text(message) # Send plain text

    except requests.exceptions.RequestException as e:
        # Use helper to check for 401, otherwise log and inform user
        if not await handle_api_error(e, update, context, "list files"):
             # If it wasn't 401, clear listing state as we failed
             context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None)
    except Exception as e:
        logger.error(f"Unexpected error fetching/displaying files for user {user.id}: {e}", exc_info=True)
        await effective_message.reply_text("❌ An unexpected error occurred while fetching files.")
        context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None) # Clear state


async def exit_listing(update: Update, context: CallbackContext) -> None: # Keep as is
    user = update.effective_user; logger.info(f"/exitlist from user: {user.id if user else '?'}")
    if "list_offset" in context.user_data or "list_limit" in context.user_data:
        context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None); await update.message.reply_text("✅ Exited file listing mode.")
    else: await update.message.reply_text("ℹ️ You weren't in file listing mode.")


async def search_file(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/search from user: {user.id if user else '?'}")
    if not user: await update.message.reply_text("Cannot identify user."); return

    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please use /login first."); return
    jwt = context.user_data.get("jwt")

    if not context.args: await update.message.reply_text("❌ Usage: /search <filename_query>"); return
    query = " ".join(context.args); username = context.user_data.get('username', '?'); logger.info(f"Searching '{query}' for {username} ({user.id})")
    await update.message.reply_text(f"⏳ Searching for files matching '{query}'...")
    try:
        response = requests.get(f"{API_BASE_URL.rstrip('/')}/search_files", params={"query": query, "limit": 5}, headers={"Authorization": f"Bearer {jwt}"}, timeout=20) # Slightly longer timeout for search
        response.raise_for_status()
        files = response.json(); logger.info(f"Search API found {len(files)} results.")
        if files:
            lines = []
            for i, file in enumerate(files):
                size_display = "Unknown"; size_bytes = file.get('size');
                if isinstance(size_bytes, int):
                    if size_bytes == 0: size_display = "0 B"
                    elif size_bytes < 1024: size_display = f"{size_bytes} B"
                    elif size_bytes < 1024 * 1024: size_display = f"{size_bytes / 1024:.1f} KB"
                    else: size_display = f"{size_bytes / (1024*1024):.2f} MB"
                lines.append(f"{i+1}. 📄 {file.get('name','?')} ({file.get('provider','?')}, {size_display})")
            await update.message.reply_text(f"✅ Found files matching '{query}':\n\n" + "\n".join(lines))
        else: await update.message.reply_text(f"❌ No files found matching '{query}' in your connected drives.")
    except requests.exceptions.RequestException as e: await handle_api_error(e, update, context, "search files")
    except Exception as e: logger.error(f"Unexpected error during search for user {user.id}: {e}", exc_info=True); await update.message.reply_text("❌ An unexpected error occurred during search.")


async def upload_file(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"Document upload from user: {user.id if user else '?'}")
    if not user: await update.message.reply_text("Cannot identify user."); return

    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please use /login first to upload files."); return
    jwt = context.user_data.get("jwt")

    if not update.message or not update.message.document: await update.message.reply_text("❓ Please send the file you want to upload as a document."); return
    doc = update.message.document; original_filename = doc.file_name or "untitled_upload"; sanitized_filename = sanitize_filename(original_filename)
    file_size = doc.file_size; mime_type = doc.mime_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"

    await update.message.reply_text(f"⏳ Receiving '{original_filename}' ({file_size / (1024*1024):.2f} MB)...")
    temp_dir = os.path.join("downloads", str(user.id)); os.makedirs(temp_dir, exist_ok=True); temp_file_path = os.path.join(temp_dir, sanitized_filename)
    username = context.user_data.get('username', '?')

    try:
        tg_file = await context.bot.get_file(doc.file_id); await tg_file.download_to_drive(custom_path=temp_file_path); logger.info(f"File downloaded to temporary path: {temp_file_path}")
        await update.message.reply_text("⬆️ Uploading to Syncly storage...")
        with open(temp_file_path, "rb") as f:
            files_payload = {"file": (original_filename, f, mime_type)} # Send original name to API
            response = requests.post(f"{API_BASE_URL.rstrip('/')}/files/upload", files=files_payload, headers={"Authorization": f"Bearer {jwt}"}, timeout=300) # Longer timeout for large uploads
            response.raise_for_status()
        upload_result = response.json(); logger.info(f"File upload API response for user {user.id}: {upload_result}")
        await update.message.reply_text(upload_result.get("message", "✅ File uploaded successfully!"))
    except requests.exceptions.RequestException as e: await handle_api_error(e, update, context, "file upload")
    except Exception as e: logger.error(f"Error during file upload process for user {user.id}: {e}", exc_info=True); await update.message.reply_text("❌ An error occurred during the file upload process.")
    finally:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path); logger.info(f"Temporary file {temp_file_path} cleaned up.")
                try:
                    if not os.listdir(temp_dir): os.rmdir(temp_dir); logger.info(f"Removed empty temporary directory: {temp_dir}")
                except OSError: logger.debug(f"Temporary directory {temp_dir} not empty or couldn't be removed.")
            except OSError as e: logger.warning(f"Could not clean up temporary file {temp_file_path}: {e}")


# --- START OF UPDATED storage_info FUNCTION ---

async def storage_info(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/storage from user: {user.id if user else '?'}")
    if not user: await update.message.reply_text("Cannot identify user."); return

    # Check authentication status (and complete if necessary)
    if not await check_and_complete_auth(update, context):
        await update.message.reply_text("❌ Please use /login first.")
        return
    jwt = context.user_data.get("jwt") # Get JWT after successful check

    username = context.user_data.get('username', '?'); logger.info(f"Fetching storage info for {username} ({user.id})")
    await update.message.reply_text("⏳ Fetching storage information...")
    try:
        response = requests.get(
            f"{API_BASE_URL.rstrip('/')}/storage",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15 # Reasonable timeout for storage check
        )
        response.raise_for_status() # Check for HTTP errors
        storage_data = response.json(); logger.info(f"Storage API Response for user {user.id}: {storage_data}")

        # --- Formatting the Message (Overall Summary ONLY) ---
        total_gb = storage_data.get("total_storage_gb", 0)
        used_gb = storage_data.get("used_storage_gb", 0)
        free_gb = storage_data.get("free_storage_gb", 0)

        # Only include the overall summary lines
        lines = [
            f"📊 **Overall Storage Summary**", # Updated title slightly
            f"Total: {total_gb:.2f} GB",
            f"Used: {used_gb:.2f} GB",
            f"Free: {free_gb:.2f} GB"
        ]

        # --- REMOVED Individual Drive Details Section ---
        # individual = storage_data.get("storages", [])
        # if individual:
        #      lines.append("\n📋 **Details per Drive**")
        #      for i, s in enumerate(individual):
        #          p = s.get('provider', '?'); n = s.get('drive_number', i+1); l = s.get('storage_limit_gb', 0); u = s.get('used_storage_gb', 0); f = s.get('free_storage_gb', 0)
        #          lines.append(f"- {p} #{n}: Used {u:.2f}/{l:.2f} GB (Free: {f:.2f} GB)")
        # --- END REMOVED Section ---

        # Using Markdown for slight emphasis
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    except requests.exceptions.RequestException as e:
        # Use the helper to handle potential 401 or other request errors
        await handle_api_error(e, update, context, "storage info")
    except Exception as e:
        logger.error(f"Unexpected storage info error for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred fetching storage info.")

# --- END OF UPDATED storage_info FUNCTION ---

# --- LLM Handlers (Using Auth Check) ---
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; logger.info(f"/ask from user: {user.id if user else '?'}")
    if not user: await update.message.reply_text("Cannot identify user."); return

    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please use /login first to use the Ask AI feature."); return
    jwt = context.user_data.get("jwt")

    if not context.args: await update.message.reply_text("Please provide a question after /ask.\nExample: `/ask What is Syncly?`"); return
    query = " ".join(context.args).strip()
    telegram_user_id = context.user_data.get("telegram_id", str(user.id)); username = context.user_data.get('username', '?')
    logger.info(f"User {username} (TG_ID: {telegram_user_id}) asking: '{query}'")
    thinking_message = await update.message.reply_text("🧠 Asking Syncly AI (this may take a moment)...")
    try:
        headers = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}; payload = {"question": query, "user_id": telegram_user_id}
        response = requests.post(f"{API_BASE_URL.rstrip('/')}/llm/ask", headers=headers, json=payload, timeout=90); response.raise_for_status()
        if response.headers.get('content-type') == 'application/json':
             answer_data = response.json(); answer = answer_data.get("response", "Sorry, I couldn't get a proper response from the AI.")
             await thinking_message.edit_text(f"🤖 {answer}") # Edit original message
        else: logger.error(f"LLM Ask API response was not JSON: {response.text[:200]}"); await thinking_message.edit_text("❌ Failed to get a valid response from the AI (Invalid Format).")
    except requests.exceptions.RequestException as e:
        if not await handle_api_error(e, update, context, "ask AI"): # Check for 401
             await thinking_message.edit_text("❌ Failed to reach the AI service. Please try again.") # Generic error if not 401
    except Exception as e: logger.error(f"An unexpected error occurred during /ask for user {user.id}: {e}", exc_info=True); await thinking_message.edit_text(f"⚠️ An unexpected error occurred while asking the AI.")


async def reset_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; logger.info(f"/reset from user: {user.id if user else '?'}")
    if not user: await update.message.reply_text("Cannot identify user."); return
    # No explicit auth check needed here as API uses telegram_id from payload
    telegram_user_id = str(user.id); username = context.user_data.get('username', '?'); logger.info(f"Resetting memory for user: {username} (ID: {telegram_user_id})")
    try:
        payload = {"user_id": telegram_user_id}
        response = requests.post(f"{API_BASE_URL.rstrip('/')}/llm/reset", json=payload, timeout=10); response.raise_for_status()
        if response.headers.get('content-type') == 'application/json':
            reset_data = response.json(); await update.message.reply_text(reset_data.get("message", "🧠 AI conversation memory reset!"))
        else: logger.error(f"LLM Reset API response was not JSON: {response.text[:200]}"); await update.message.reply_text("❌ Could not reset memory (Invalid Response).")
    except requests.exceptions.RequestException as e:
        # Use handle_api_error just in case reset endpoint requires auth later
        await handle_api_error(e, update, context, "reset memory")
    except Exception as e: logger.error(f"An unexpected error occurred during /reset for user {user.id}: {e}", exc_info=True); await update.message.reply_text(f"⚠️ An unexpected error occurred while resetting memory.")

# --- Main Bot Setup ---
def main():
    logger.info("Starting Syncly Bot...")
    builder = Application.builder().token(TOKEN)
    app = builder.build()

    # Register Handlers (Order Matters)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("addbucket", add_drive))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("more", more_files))
    app.add_handler(CommandHandler("exitlist", exit_listing))
    app.add_handler(CommandHandler("search", search_file))
    app.add_handler(CommandHandler("storage", storage_info))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("reset", reset_memory))

    # Message Handlers (Lower Priority)
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, upload_file))
    # No text handler for JWT needed anymore

    logger.info("Handlers added.")
    print("🤖 Syncly Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
# --- END OF FILE synclybot.py ---