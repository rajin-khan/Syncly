import msal
import requests
import json

# Azure app registration details
CLIENT_ID = "2dfae117-e01c-40e4-a465-31dc1481e25f"
TENANT_ID = "6c42c5f0-38a9-4ff6-950c-e3f506601d0b"  # Replace with your actual tenant ID
AUTHORITY = f"https://login.microsoftonline.com/consumers"
SCOPES = ["https://graph.microsoft.com/.default"]
FILE_PATH = f"F:\CSE327\output.csv"  # Use raw string (r"") to avoid escape issues
ONEDRIVE_PATH = "output.csv"  # Destination filename in OneDrive
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

# OneDrive upload URL
UPLOAD_URL = f"https://graph.microsoft.com/v1.0/me/drive/root:/{ONEDRIVE_PATH}:/content"

# Read the file content
with open(FILE_PATH, "rb") as file:
    file_content = file.read()

# Upload the file
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/octet-stream"
}

response = requests.put(UPLOAD_URL, headers=headers, data=file_content)

response_data = response.json()

#store response in a json file
with open(upload_json,"w",encoding="utf-8") as test_json:
    json.dump(response_data, test_json, indent=2)

# Check the response
if response.status_code in [200, 201]:
    print("File uploaded successfully!")
    print(json.dumps(response.json(), indent=2))
else:
    print("Failed to upload file:", response.status_code, response.text)
