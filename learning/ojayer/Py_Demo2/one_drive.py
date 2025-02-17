import msal
import requests
import json

# Azure app registration details
CLIENT_ID = "real client_id"
TENANT_ID = "real tenant_id"
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["https://graph.microsoft.com/.default"]
FILE_PATH = r"F:\CSE327\output.csv"
ONEDRIVE_PATH = "output.csv"
DOWNLOAD_PATH = r"F:\CSE327\downloaded_output.csv"
upload_json = "upload.json"

# Initialize MSAL client
app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)

# Acquire token interactively
result = app.acquire_token_interactive(scopes=SCOPES)

if "access_token" in result:
    access_token = result["access_token"]
    print("Access token acquired successfully!")
else:
    print("Failed to acquire token:", result.get("error_description"))
    exit()

# --- Upload File ---
UPLOAD_URL = f"https://graph.microsoft.com/v1.0/me/drive/root:/{ONEDRIVE_PATH}:/content"

with open(FILE_PATH, "rb") as file:
    file_content = file.read()

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/octet-stream"
}

response = requests.put(UPLOAD_URL, headers=headers, data=file_content)
response_data = response.json()

# Store response in a JSON file
with open(upload_json, "w", encoding="utf-8") as test_json:
    json.dump(response_data, test_json, indent=2)

# Check upload response
if response.status_code in [200, 201]:
    print("File uploaded successfully!")
    download_url = response_data.get("@microsoft.graph.downloadUrl")
    if download_url:
        print("Using provided download URL for direct access.")
    else:
        print("Download URL not found in response. Exiting.")
        exit()
else:
    print("Failed to upload file:", response.status_code, response.text)
    exit()

#Download File
print("Downloading file...")
download_response = requests.get(download_url)

if download_response.status_code == 200:
    with open(DOWNLOAD_PATH, "wb") as file:
        file.write(download_response.content)
    print(f"File downloaded successfully! Saved as {DOWNLOAD_PATH}")
else:
    print("Failed to download file:", download_response.status_code, download_response.text)
