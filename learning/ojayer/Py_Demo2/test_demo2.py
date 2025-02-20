from google_drive import googleDrive # Import the GoogleDriveService class

# Step 1: Create an instance of GoogleDriveService
gdrive = googleDrive()

# Step 2: Authenticate the service
gdrive.authenticate(bucket_number=1)

# Step 3: Check storage
limit,storage = gdrive.check_storage()

# Step 4: Print the results
print(f"Storage Limit: {limit}")
print(f"Storage Used: {storage}")