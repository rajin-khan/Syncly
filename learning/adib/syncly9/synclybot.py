# --- START OF FILE synclybot.py ---

import logging
import requests
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup # Added Inline buttons
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
# Removed CallbackQueryHandler for now
import os
import mimetypes
import re
# uuid isn't strictly needed here anymore as API generates link_id
from datetime import datetime, timedelta # Keep datetime
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
if not TOKEN: logger.critical("FATAL ERROR: TELEGRAM_BOT_TOKEN missing"); exit("Token Missing")
if not API_BASE_URL: logger.critical("FATAL ERROR: API_BASE_URL missing"); exit("API URL Missing")

# Ensure downloads directory exists
os.makedirs("downloads", exist_ok=True)

# --- Constants ---
LINK_EXPIRY_MINUTES = 5 # How long the login link is valid (for user message)

# --- Helper Functions ---
def sanitize_filename(filename: str) -> str:
    if not filename: return "downloaded_file"
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename); sanitized = sanitized.strip(" ._")
    sanitized = re.sub(r'_+', '_', sanitized); return sanitized if sanitized else "downloaded_file"


# --- NEW: Auth Check Helper ---
async def check_and_complete_auth(update: Update, context: CallbackContext) -> bool:
    """
    Checks for pending link ID, calls API to complete auth if needed.
    Updates context.user_data with JWT and username on success.
    Returns True if authenticated (JWT exists or link succeeded), False otherwise.
    Handles specific API error responses (404, 410, 403, 400) and generic errors.
    """
    effective_message = update.effective_message # Use effective_message for potential edits/replies
    if not effective_message: return False # Cannot reply without a message context

    user = update.effective_user
    if not user: return False
    telegram_id = str(user.id)

    # 1. Check if already authenticated (JWT exists)
    if context.user_data.get("jwt"):
        return True

    # 2. Check for a pending link initiated by this user
    link_id = context.user_data.get('pending_link_id')
    link_expiry_client = context.user_data.get('pending_link_expiry')

    if not link_id:
        return False # No pending link

    # 3. Client-side expiry check (rough estimate)
    if link_expiry_client and datetime.utcnow() > link_expiry_client:
        logger.info(f"Client-side expiry check failed for link_id {link_id} for user {telegram_id}. Prompting login.")
        context.user_data.pop('pending_link_id', None); context.user_data.pop('pending_link_expiry', None)
        # Let calling function handle the "Please login" message
        return False

    # 4. Attempt to complete authentication via API
    logger.info(f"User {telegram_id} trying to complete auth with pending link_id: {link_id}")
    api_url = f"{API_BASE_URL.rstrip('/')}/auth/complete_link"
    payload = {"link_id": link_id, "telegram_id": telegram_id}

    try:
        response = requests.post(api_url, json=payload, timeout=10)

        # --- Handle API Responses ---
        if response.status_code == 200:
            auth_data = response.json()
            jwt_token = auth_data.get("access_token")
            username = auth_data.get("username")
            if jwt_token and username:
                context.user_data["jwt"] = jwt_token
                context.user_data["username"] = username
                context.user_data["telegram_id"] = telegram_id # Ensure stored
                context.user_data.pop('pending_link_id', None); context.user_data.pop('pending_link_expiry', None)
                logger.info(f"Successfully completed auth link for user {telegram_id} (Username: {username})")
                # Don't send message here, let original command proceed
                return True # Now authenticated
            else:
                logger.error(f"API OK but missing token/user for link {link_id}.")
                await effective_message.reply_text("❌ Authentication failed (Invalid API data). Please try /login again.")
        elif response.status_code == 400: # Link not validated yet
             logger.warning(f"Auth link {link_id} not validated yet for user {telegram_id}.")
             await effective_message.reply_text("⏳ Please complete the login process in your web browser first, then try your command again.")
        elif response.status_code in [404, 410, 403]: # Not found, Expired/Used, Forbidden (ID mismatch)
             error_detail = "Link not found, expired, or invalid."
             try: error_detail = response.json().get("detail", error_detail)
             except: pass
             logger.warning(f"Auth complete failed {response.status_code} for {telegram_id}, link {link_id}: {error_detail}")
             await effective_message.reply_text(f"❌ Authentication failed: {error_detail}. Please use /login to get a new link.")
        else: # Handle other errors (e.g., 500)
             error_detail = f"Server error ({response.status_code})"
             try: error_detail = response.json().get("detail", error_detail)
             except: error_detail = response.text[:150]
             logger.error(f"Auth complete failed {response.status_code} for {telegram_id}, link {link_id}: {error_detail}")
             await effective_message.reply_text(f"❌ Authentication failed ({error_detail}). Please try again later.")

        # If any error occurred that prevented success, clear pending link state
        context.user_data.pop('pending_link_id', None); context.user_data.pop('pending_link_expiry', None)
        return False # Authentication failed

    except requests.exceptions.Timeout:
        logger.error(f"API timeout completing link {link_id}")
        await effective_message.reply_text("❌ Authentication check timed out. Please try your command again.")
        return False # Failed this attempt, keep link_id for retry
    except requests.exceptions.RequestException as e:
        logger.error(f"API connection failed completing link {link_id}: {e}")
        await effective_message.reply_text("❌ Authentication check failed (server connection). Please try again later.")
        return False # Failed this attempt, keep link_id for retry
    except Exception as e:
         logger.error(f"Unexpected error completing link: {e}", exc_info=True)
         await effective_message.reply_text("❌ Unexpected auth error.")
         context.user_data.pop('pending_link_id', None); context.user_data.pop('pending_link_expiry', None)
         return False

# --- NEW: Helper to handle API errors / Expired JWT ---
async def handle_api_error(e: requests.exceptions.RequestException, update: Update, context: CallbackContext, command_name: str = "operation") -> bool:
     """
     Checks for 401 Unauthorized, clears auth, informs user. Logs other errors.
     Returns True if a 401 error was handled, False otherwise.
     """
     user_id = update.effective_user.id if update.effective_user else 'unknown'
     effective_message = update.effective_message

     if e.response is not None and e.response.status_code == 401:
          logger.warning(f"API call returned 401 during {command_name} for user {user_id}. Clearing JWT.")
          context.user_data.pop("jwt", None)
          context.user_data.pop("username", None)
          # Also clear any pending link state if it was somehow involved
          context.user_data.pop('pending_link_id', None)
          context.user_data.pop('pending_link_expiry', None)
          if effective_message:
              await effective_message.reply_text("❌ Your session has expired. Please use /login to authenticate again.")
          return True # Indicates 401 error was handled
     else:
          # Log other request errors
          status_code = e.response.status_code if e.response is not None else "N/A"
          error_detail = f"Connection Error ({status_code})"
          if e.response is not None:
              try: error_detail = e.response.json().get("detail", e.response.text[:200])
              except ValueError: error_detail = e.response.text[:200] # Use raw text if not JSON
          logger.error(f"API request failed during {command_name} for user {user_id}: {e} | Detail: {error_detail}")
          if effective_message:
               await effective_message.reply_text(f"❌ An error occurred: {error_detail}")
          return False # Other error

# --- Command Handlers ---

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/start from {user.username or 'N/A'} (ID: {user.id})")
    jwt = context.user_data.get("jwt"); username_display = context.user_data.get("username", user.first_name or "there")
    welcome = f"Hi {username_display}! {'You are logged in. ' if jwt else 'Im the Syncly Bot. '}"
    commands = ("My commands are:\n/login\n/addbucket <Type>\n/storage\n/list [limit]\n/more\n/exitlist\n"
               "/search <name>\n/ask <question>\n/reset\n/upload (Send file)\n/logout")
    await update.message.reply_text(welcome + commands)

# --- MODIFIED /login ---
async def login(update: Update, context: CallbackContext) -> None:
    """Generates a unique login link via API and sends it to the user."""
    user = update.effective_user; telegram_id = str(user.id); logger.info(f"/login from user: {telegram_id}")
    # Check if already logged in
    if context.user_data.get("jwt"):
        await update.message.reply_text("ℹ️ You are already logged in. Use /logout first if you want to re-authenticate.")
        return

    api_url = f"{API_BASE_URL.rstrip('/')}/auth/create_link"; payload = {"telegram_id": telegram_id}
    try:
        response = requests.post(api_url, json=payload, timeout=10); response.raise_for_status()
        link_data = response.json(); link_id = link_data.get("link_id"); login_url = link_data.get("login_url")
        if not link_id or not login_url: raise ValueError("Invalid response from link creation API.")

        # Store pending link info in context BEFORE sending message
        context.user_data['pending_link_id'] = link_id
        context.user_data['pending_link_expiry'] = datetime.utcnow() + timedelta(minutes=LINK_EXPIRY_MINUTES + 1)

        keyboard = [[InlineKeyboardButton("Log In / Register via Web", url=login_url)]]
        await update.message.reply_text(
            f"Click below to log in/register (link expires in {LINK_EXPIRY_MINUTES} mins).",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"Sent login button link_id {link_id} to user {telegram_id}")

    except requests.exceptions.RequestException as e:
         logger.error(f"Failed call /auth/create_link for {telegram_id}: {e}")
         # Use handle_api_error for consistent reporting, although 401 shouldn't happen here
         await handle_api_error(e, update, context, command_name="login link generation")
    except Exception as e:
         logger.error(f"Error during /login for {telegram_id}: {e}", exc_info=True)
         await update.message.reply_text("❌ An error occurred while generating the login link.")

async def logout(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id; logger.info(f"/logout from user: {user_id}")
    if "jwt" in context.user_data or "pending_link_id" in context.user_data: # Clear pending link too
        username = context.user_data.get("username", "?"); context.user_data.clear()
        logger.info(f"User {username} ({user_id}) logged out / cleared pending auth")
        await update.message.reply_text("✅ Logged out.")
    else: await update.message.reply_text("ℹ️ Not logged in.")

# --- MODIFIED Command Handlers Requiring Auth ---

async def add_drive(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/addbucket from user: {user.id}")
    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please /login first."); return
    jwt = context.user_data.get("jwt") # Get JWT after check
    if not context.args or len(context.args) < 1: await update.message.reply_text("Usage: /addbucket <GoogleDrive|Dropbox>"); return
    drive_type = context.args[0].strip().lower(); drive_type_norm = ""
    if drive_type == "googledrive": drive_type_norm = "GoogleDrive"
    elif drive_type == "dropbox": drive_type_norm = "Dropbox"
    else: await update.message.reply_text("❌ Invalid drive type."); return
    username = context.user_data.get('username', '?'); logger.info(f"Adding {drive_type_norm} for {username} ({user.id})")
    await update.message.reply_text(f"⏳ Adding {drive_type_norm}...")
    try:
        response = requests.post(f"{API_BASE_URL.rstrip('/')}/drives", json={"drive_type": drive_type_norm}, headers={"Authorization": f"Bearer {jwt}"}, timeout=15); response.raise_for_status()
        drive_data = response.json(); logger.info(f"Add drive response: {drive_data}")
        await update.message.reply_text(drive_data.get("message", "✅ Drive added!"))
    except requests.exceptions.RequestException as e: await handle_api_error(e, update, context, "add drive")
    except Exception as e: logger.error(f"Unexpected error adding drive: {e}", exc_info=True); await update.message.reply_text("❌ Unexpected error adding drive.")

async def list_files(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/list from user: {user.id}")
    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please /login first."); return
    limit = 10
    if context.args: 
        try: limit = int(context.args[0]); assert 0 < limit <= 100
        except: await update.message.reply_text("❌ Invalid limit (1-100)."); return
    context.user_data["list_offset"] = 0; context.user_data["list_limit"] = limit
    await update.message.reply_text(f"⏳ Fetching first {limit} files..."); await fetch_and_display_files(update, context, False)

async def more_files(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/more from user: {user.id}")
    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please /login first."); return
    offset = context.user_data.get("list_offset"); limit = context.user_data.get("list_limit")
    if offset is None or limit is None: await update.message.reply_text("ℹ️ Use /list first."); return
    context.user_data["list_offset"] = offset + limit
    await update.message.reply_text(f"⏳ Fetching next {limit} files..."); await fetch_and_display_files(update, context, True)

async def fetch_and_display_files(update: Update, context: CallbackContext, is_continuation: bool):
    # This helper relies on calling function ensuring auth
    jwt = context.user_data.get("jwt"); offset = context.user_data.get("list_offset"); limit = context.user_data.get("list_limit")
    user = update.effective_user; username = context.user_data.get('username', f'User_{user.id}')
    if not jwt: logger.error("AUTH fetch_files: JWT missing!"); await update.effective_message.reply_text("Error: Not authenticated."); return
    if offset is None or limit is None: logger.error("STATE fetch_files: Pagination missing!"); await update.effective_message.reply_text("Error: List state lost."); return
    try:
        logger.info(f"Fetching files: user={username} ({user.id}), l={limit}, o={offset}")
        response = requests.get(f"{API_BASE_URL.rstrip('/')}/viewfiles", params={"limit": limit, "offset": offset}, headers={"Authorization": f"Bearer {jwt}"}, timeout=25)
        response.raise_for_status(); files = response.json(); logger.debug(f"API file list response: {files}")
        if not files: msg = "✅ No more files." if is_continuation else "📂 No files found."; await update.effective_message.reply_text(msg); context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None); return
        lines = []; num = offset + 1
        for file in files:
            size_disp = "Unk"; sz = file.get('size');
            if isinstance(sz, int): size_disp = f"{sz/(1024*1024):.2f}MB" if sz>=1024*1024 else f"{sz/1024:.1f}KB" if sz>=1024 else f"{sz}B"
            lines.append(f"{num}. 📄 {file.get('name','?')} ({file.get('provider','?')}, {size_disp})"); num += 1
        msg = f"📂 Files {offset + 1}-{offset + len(files)}:\n\n" + "\n".join(lines)
        if len(files) == limit: msg += "\n\nℹ️ Type /more or /exitlist."
        else: msg += "\n\n✅ End of files."; context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None)
        await update.effective_message.reply_text(msg)
    except requests.exceptions.RequestException as e:
        if not await handle_api_error(e, update, context, "list files"): context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None) # Clear state on other errors too
    except Exception as e:
        logger.error(f"Unexpected error fetching files: {e}", exc_info=True); await update.effective_message.reply_text("❌ Error fetching files.")
        context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None)

async def exit_listing(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/exitlist from user: {user.id}")
    if "list_offset" in context.user_data or "list_limit" in context.user_data:
        context.user_data.pop("list_offset", None); context.user_data.pop("list_limit", None); await update.message.reply_text("✅ Exited listing.")
    else: await update.message.reply_text("ℹ️ Not in listing mode.")

async def search_file(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/search from user: {user.id}")
    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please /login first."); return
    jwt = context.user_data.get("jwt")
    if not context.args: await update.message.reply_text("❌ Usage: /search <query>"); return
    query = " ".join(context.args); username = context.user_data.get('username', '?'); logger.info(f"Searching '{query}' for {username} ({user.id})")
    await update.message.reply_text(f"⏳ Searching for '{query}'...")
    try:
        response = requests.get(f"{API_BASE_URL.rstrip('/')}/search_files", params={"query": query, "limit": 5}, headers={"Authorization": f"Bearer {jwt}"}, timeout=15); response.raise_for_status()
        files = response.json(); logger.info(f"Search API response: {files}")
        if files:
            lines = []
            for i, file in enumerate(files):
                size_disp = "Unk"; sz = file.get('size');
                if isinstance(sz, int): size_disp = f"{sz/(1024*1024):.2f}MB" if sz>=1024*1024 else f"{sz/1024:.1f}KB" if sz>=1024 else f"{sz}B"
                lines.append(f"{i+1}. 📄 {file.get('name','?')} ({file.get('provider','?')}, {size_disp})")
            await update.message.reply_text(f"✅ Found files for '{query}':\n\n" + "\n".join(lines))
        else: await update.message.reply_text(f"❌ No files found matching '{query}'.")
    except requests.exceptions.RequestException as e: await handle_api_error(e, update, context, "search files")
    except Exception as e: logger.error(f"Unexpected error during search: {e}", exc_info=True); await update.message.reply_text("❌ Unexpected search error.")

async def upload_file(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"Document upload from user: {user.id}")
    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please /login first."); return
    jwt = context.user_data.get("jwt")
    if not update.message or not update.message.document: await update.message.reply_text("❓ Send file."); return
    doc = update.message.document; orig_name = doc.file_name or "untitled"; clean_name = sanitize_filename(orig_name) or "upload"
    size = doc.file_size; mime = doc.mime_type or mimetypes.guess_type(orig_name)[0] or "app/octet-stream"
    await update.message.reply_text(f"⏳ Receiving '{orig_name}'...")
    temp_dir = os.path.join("downloads", str(user.id)); os.makedirs(temp_dir, exist_ok=True); temp_path = os.path.join(temp_dir, clean_name)
    username = context.user_data.get('username', '?')
    try:
        tg_file = await context.bot.get_file(doc.file_id); await tg_file.download_to_drive(custom_path=temp_path); logger.info(f"Temp download: {temp_path}")
        await update.message.reply_text("⬆️ Uploading...")
        with open(temp_path, "rb") as f:
            payload = {"file": (orig_name, f, mime)}
            response = requests.post(f"{API_BASE_URL.rstrip('/')}/files/upload", files=payload, headers={"Authorization": f"Bearer {jwt}"}, timeout=180); response.raise_for_status()
        result = response.json(); logger.info(f"Upload API response: {result}")
        await update.message.reply_text(result.get("message", "✅ Uploaded!"))
    except requests.exceptions.RequestException as e: await handle_api_error(e, update, context, "file upload")
    except Exception as e: logger.error(f"Upload error for {user.id}: {e}", exc_info=True); await update.message.reply_text("❌ Upload error.")
    finally:
        if os.path.exists(temp_path): 
            try: os.remove(temp_path); logger.info("Cleaned temp upload.")
            except: pass; 
            try: os.rmdir(temp_dir)
            except: pass

async def storage_info(update: Update, context: CallbackContext) -> None:
    user = update.effective_user; logger.info(f"/storage from user: {user.id}")
    # --- Auth Check ---
    if not await check_and_complete_auth(update, context):
        await update.message.reply_text("❌ Please /login first.")
        return
    jwt = context.user_data.get("jwt") # Get JWT after check succeeded
    # --- End Auth Check ---

    username = context.user_data.get('username', '?'); logger.info(f"Fetching storage for {username} ({user.id})")
    await update.message.reply_text("⏳ Fetching storage...")
    try:
        response = requests.get(
            f"{API_BASE_URL.rstrip('/')}/storage",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15 # Reasonable timeout for storage check
        )
        response.raise_for_status() # Check for HTTP errors
        data = response.json(); logger.info(f"Storage response: {data}")

        # --- Formatting the Message ---
        total = data.get("total_storage_gb", 0); used = data.get("used_storage_gb", 0); free = data.get("free_storage_gb", 0)
        lines = [f"📊 Overall: {used:.2f}/{total:.2f} GB ({free:.2f} GB Free)"] # Summary line

        individual_storages = data.get("storages", [])
        if individual_storages:
             lines.append("\n📋 Details per Drive")
             for s in individual_storages:
                 # Remove [:10] to show full provider name
                 provider_name = s.get('provider','?')
                 drive_num = s.get('drive_number','?')
                 used_gb = s.get('used_storage_gb',0)
                 limit_gb = s.get('storage_limit_gb',0)
                 # Use f-string for cleaner formatting
                 lines.append(f"- {provider_name} #{drive_num}: {used_gb:.2f}/{limit_gb:.2f} GB")

        await update.message.reply_text("\n".join(lines)) # Send plain text

    except requests.exceptions.RequestException as e:
        # Use the helper to handle potential 401 or other request errors
        await handle_api_error(e, update, context, "storage info")
    except Exception as e:
        logger.error(f"Unexpected storage error: {e}", exc_info=True)
        await update.message.reply_text("❌ Error fetching storage info.")

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; logger.info(f"/ask from user: {user.id}")
    thinking_msg = None
    if not await check_and_complete_auth(update, context): await update.message.reply_text("❌ Please /login first."); return
    jwt = context.user_data.get("jwt")
    if not context.args: await update.message.reply_text("Usage: /ask <question>"); return
    query = " ".join(context.args).strip()
    tg_id = context.user_data.get("telegram_id", str(user.id)); username = context.user_data.get('username', '?')
    logger.info(f"User {username} (TG:{tg_id}) asking: '{query}'")
    thinking_msg = await update.message.reply_text("🧠 Asking Syncly AI...")
    try:
        headers = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}; payload = {"question": query, "user_id": tg_id}
        response = requests.post(f"{API_BASE_URL.rstrip('/')}/llm/ask", headers=headers, json=payload, timeout=90); response.raise_for_status()
        if response.headers.get('content-type') == 'application/json':
             data = response.json(); answer = data.get("response", "Couldn't get response.")
             await thinking_msg.edit_text(f"🤖 {answer}")
        else: logger.error(f"LLM Ask non-JSON: {response.text[:200]}"); await thinking_msg.edit_text("❌ Failed (Invalid AI response).")
    except requests.exceptions.RequestException as e:
        if not await handle_api_error(e, update, context, "ask AI"): # If not 401 handled
             if thinking_msg: await thinking_msg.edit_text("❌ Failed to reach AI service.")
             else: await update.message.reply_text("❌ Failed to reach AI service.")
    except Exception as e: logger.error(f"Unexpected /ask error: {e}", exc_info=True); await thinking_msg.edit_text("⚠️ Unexpected AI error.")

async def reset_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; logger.info(f"/reset from user: {user.id}")
    # Auth check optional - decided API handles based on telegram_id
    tg_id = str(user.id); username = context.user_data.get('username', '?'); logger.info(f"Resetting memory for {username} ({tg_id})")
    try:
        payload = {"user_id": tg_id}
        response = requests.post(f"{API_BASE_URL.rstrip('/')}/llm/reset", json=payload, timeout=10); response.raise_for_status()
        if response.headers.get('content-type') == 'application/json': data = response.json(); await update.message.reply_text(data.get("message", "🧠 Memory reset!"))
        else: logger.error(f"LLM Reset non-JSON: {response.text[:200]}"); await update.message.reply_text("❌ Reset failed (Invalid Response).")
    except requests.exceptions.RequestException as e: await handle_api_error(e, update, context, "reset memory") # Use helper just in case
    except Exception as e: logger.error(f"Unexpected /reset error: {e}", exc_info=True); await update.message.reply_text("⚠️ Unexpected reset error.")

# --- Main Bot Setup ---
def main():
    logger.info("Starting Syncly Bot...")
    builder = Application.builder().token(TOKEN)
    app = builder.build()

    # Register Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login)) # Uses NEW logic
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("addbucket", add_drive)) # Uses auth check
    app.add_handler(CommandHandler("list", list_files))     # Uses auth check
    app.add_handler(CommandHandler("more", more_files))     # Uses auth check
    app.add_handler(CommandHandler("exitlist", exit_listing))
    app.add_handler(CommandHandler("search", search_file))   # Uses auth check
    app.add_handler(CommandHandler("storage", storage_info)) # Uses auth check
    app.add_handler(CommandHandler("ask", ask))             # Uses auth check
    app.add_handler(CommandHandler("reset", reset_memory))   # Auth check optional

    # Message Handlers
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, upload_file)) # Uses auth check
    # --- REMOVED handle_jwt text handler ---

    logger.info("Handlers added.")
    print("🤖 Syncly Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
# --- END OF FILE synclybot.py ---