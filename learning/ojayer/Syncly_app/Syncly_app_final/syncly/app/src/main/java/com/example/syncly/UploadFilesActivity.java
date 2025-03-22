package com.example.syncly;

import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.util.Log;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import com.dropbox.core.v2.DbxClientV2;
import com.google.api.client.http.InputStreamContent;
import com.google.api.services.drive.Drive;

import org.bson.Document;

import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.io.File;

public class UploadFilesActivity extends AppCompatActivity {
    private static final String TAG = "UploadFilesActivity";
    private static final int REQUEST_FILE_PICK = 1;

    private Button btnSelectFile, btnUpload;
    private TextView tvSelectedFile;
    private String userId;
    private DriveManager driveManager;
    private Uri selectedFileUri;
    private Map<String, List<Service>> availableDrives = new HashMap<>();
    private Map<String, Long> totalFreeSpace = new HashMap<>(); // Total space per drive type

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_upload_files);

        btnSelectFile = findViewById(R.id.btn_select_file);
        btnUpload = findViewById(R.id.btn_upload);
        tvSelectedFile = findViewById(R.id.tv_selected_file);

        userId = getIntent().getStringExtra("userId");
        Log.d(TAG, "Retrieved userId from intent: " + userId);

        String tokenDir = getFilesDir().getAbsolutePath();
        driveManager = DriveManager.getInstance(userId, tokenDir, this);

        new InitializeDrivesTask().execute();

        btnSelectFile.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("*/*");
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            startActivityForResult(Intent.createChooser(intent, "Select a file"), REQUEST_FILE_PICK);
        });

        btnUpload.setOnClickListener(v -> {
            if (selectedFileUri == null) {
                Toast.makeText(this, "Please select a file first!", Toast.LENGTH_SHORT).show();
                return;
            }
            String targetDrive = determineTargetDrive();
            Toast.makeText(this, "Uploading to " + targetDrive + "...", Toast.LENGTH_SHORT).show();
            new UploadFileTask(targetDrive).execute(selectedFileUri);
        });
    }

    private String determineTargetDrive() {
        long googleDriveSpace = totalFreeSpace.getOrDefault("GoogleDrive", 0L);
        long dropboxSpace = totalFreeSpace.getOrDefault("Dropbox", 0L);
        Log.d(TAG, "Google Drive total free space: " + googleDriveSpace + " bytes, Dropbox total free space: " + dropboxSpace + " bytes");
        return googleDriveSpace >= dropboxSpace ? "GoogleDrive" : "Dropbox";
    }

    private class InitializeDrivesTask extends AsyncTask<Void, Void, Boolean> {
        private Map<String, Map<Integer, Long>> bucketSpaceInfo = new HashMap<>();

        @Override
        protected Boolean doInBackground(Void... voids) {
            try {
                List<DriveManager.Bucket> buckets = driveManager.getSortedBuckets();
                availableDrives.put("GoogleDrive", new ArrayList<>());
                availableDrives.put("Dropbox", new ArrayList<>());
                bucketSpaceInfo.put("GoogleDrive", new HashMap<>());
                bucketSpaceInfo.put("Dropbox", new HashMap<>());
                totalFreeSpace.put("GoogleDrive", 0L);
                totalFreeSpace.put("Dropbox", 0L);

                for (DriveManager.Bucket bucket : buckets) {
                    Service service = bucket.getDrive();
                    long freeSpace = bucket.getFreeSpace();
                    if (freeSpace > 0) {
                        if (service instanceof GoogleDrive) {
                            availableDrives.get("GoogleDrive").add(service);
                            bucketSpaceInfo.get("GoogleDrive").put(bucket.getIndex(), freeSpace);
                            totalFreeSpace.put("GoogleDrive", totalFreeSpace.get("GoogleDrive") + freeSpace);
                        } else if (service instanceof DropboxService) {
                            availableDrives.get("Dropbox").add(service);
                            bucketSpaceInfo.get("Dropbox").put(bucket.getIndex(), freeSpace);
                            totalFreeSpace.put("Dropbox", totalFreeSpace.get("Dropbox") + freeSpace);
                        }
                    }
                }
                return !availableDrives.get("GoogleDrive").isEmpty() || !availableDrives.get("Dropbox").isEmpty();
            } catch (Exception e) {
                Log.e(TAG, "Failed to initialize drives: " + e.getMessage(), e);
                return false;
            }
        }

        @Override
        protected void onPostExecute(Boolean success) {
            if (!success) {
                Toast.makeText(UploadFilesActivity.this, "No drives available. Add a bucket first.", Toast.LENGTH_LONG).show();
            } else {
                Log.d(TAG, "Initialized drives: " + availableDrives);
                StringBuilder spaceInfo = new StringBuilder("Available Bucket Space:\n");
                for (String driveType : bucketSpaceInfo.keySet()) {
                    Map<Integer, Long> buckets = bucketSpaceInfo.get(driveType);
                    for (Map.Entry<Integer, Long> entry : buckets.entrySet()) {
                        long freeSpaceMB = entry.getValue() / (1024 * 1024);
                        spaceInfo.append(String.format("%s bucket %d: %d MB free\n", driveType, entry.getKey(), freeSpaceMB));
                        Log.d(TAG, String.format("%s bucket %d has %d MB free space", driveType, entry.getKey(), freeSpaceMB));
                    }
                }
                tvSelectedFile.setText(spaceInfo.toString());
            }
        }
    }

    private class UploadFileTask extends AsyncTask<Uri, Void, Boolean> {
        private final String driveType;

        UploadFileTask(String driveType) {
            this.driveType = driveType;
        }

        @Override
        protected Boolean doInBackground(Uri... uris) {
            Uri uri = uris[0];
            try {
                List<Service> services = availableDrives.get(driveType);
                if (services == null || services.isEmpty()) {
                    Log.e(TAG, driveType + " services not available");
                    return false;
                }

                File file = convertUriToFile(uri);
                long fileSize = file.length();
                String fileName = getFileName(uri);
                String mimeType = getContentResolver().getType(uri);
                if (mimeType == null) mimeType = "application/octet-stream";

                List<DriveManager.Bucket> buckets = driveManager.getSortedBuckets();
                List<DriveManager.Bucket> typeBuckets = new ArrayList<>();
                for (DriveManager.Bucket bucket : buckets) {
                    if ((driveType.equals("GoogleDrive") && bucket.getDrive() instanceof GoogleDrive) ||
                            (driveType.equals("Dropbox") && bucket.getDrive() instanceof DropboxService)) {
                        typeBuckets.add(bucket);
                    }
                }

                long totalFreeSpaceForType = 0;
                Map<DriveManager.Bucket, Long> freeSpaceMap = new HashMap<>();
                for (DriveManager.Bucket bucket : typeBuckets) {
                    long freeSpace = bucket.getFreeSpace();
                    if (freeSpace > 0) {
                        totalFreeSpaceForType += freeSpace;
                        freeSpaceMap.put(bucket, freeSpace);
                    }
                }

                if (totalFreeSpaceForType < fileSize) {
                    Log.e(TAG, "Not enough space in " + driveType + " buckets");
                    return false;
                }

                Document metadata = new Document("user_id", userId)
                        .append("file_name", fileName)
                        .append("chunks", new ArrayList<Document>());

                DriveManager.Bucket bestBucket = null;
                for (DriveManager.Bucket bucket : freeSpaceMap.keySet()) {
                    if (freeSpaceMap.get(bucket) >= fileSize) {
                        bestBucket = bucket;
                        break;
                    }
                }

                if (bestBucket != null) {
                    uploadEntireFile(bestBucket, file, fileName, mimeType, metadata);
                } else {
                    splitAndUploadFile(file, fileName, mimeType, fileSize, freeSpaceMap, metadata);
                }

                Database.getInstance().getMetadataCollection().updateOne(
                        new Document("user_id", userId).append("file_name", fileName),
                        new Document("$set", metadata),
                        new com.mongodb.client.model.UpdateOptions().upsert(true)
                );
                Log.d(TAG, "Metadata updated in MongoDB: " + metadata.toJson());

                return true;
            } catch (Exception e) {
                Log.e(TAG, "Upload failed to " + driveType + ": " + e.getMessage(), e);
                return false;
            }
        }

        private void uploadEntireFile(DriveManager.Bucket bucket, File file, String fileName, String mimeType, Document metadata) throws Exception {
            Service service = bucket.getDrive();
            authenticateService(service, bucket.getIndex());

            if (service instanceof GoogleDrive) {
                Drive driveService = GoogleDriveHelper.getDriveService(UploadFilesActivity.this, ((GoogleDrive) service).getAccountEmail());
                if (driveService != null) {
                    com.google.api.services.drive.model.File fileMetadata = new com.google.api.services.drive.model.File();
                    fileMetadata.setName(fileName);
                    try (InputStream inputStream = getContentResolver().openInputStream(selectedFileUri)) {
                        InputStreamContent mediaContent = new InputStreamContent(mimeType, inputStream);
                        com.google.api.services.drive.model.File uploadedFile = driveService.files().create(fileMetadata, mediaContent).execute();
                        metadata.append("chunks", new ArrayList<Document>() {{
                            add(new Document("chunk_name", fileName)
                                    .append("file_id", uploadedFile.getId())
                                    .append("bucket", bucket.getIndex()));
                        }});
                        Log.d(TAG, "Uploaded entire file to Google Drive bucket " + bucket.getIndex() + ": " + fileName);
                    }
                }
            } else if (service instanceof DropboxService) {
                DbxClientV2 dropboxClient = DropboxHelper.getDropboxClient(UploadFilesActivity.this,
                        ((DropboxService) service).getAccessToken(), ((DropboxService) service).getRefreshToken());
                if (dropboxClient != null) {
                    try (InputStream in = getContentResolver().openInputStream(selectedFileUri)) {
                        dropboxClient.files().uploadBuilder("/" + fileName).uploadAndFinish(in);
                        metadata.append("chunks", new ArrayList<Document>() {{
                            add(new Document("chunk_name", fileName)
                                    .append("bucket", bucket.getIndex()));
                        }});
                        Log.d(TAG, "Uploaded entire file to Dropbox bucket " + bucket.getIndex() + ": " + fileName);
                    }
                }
            }
        }

        private void splitAndUploadFile(File file, String fileName, String mimeType, long fileSize, Map<DriveManager.Bucket, Long> freeSpaceMap, Document metadata) throws Exception {
            long offset = 0;
            int chunkIndex = 0;
            List<Document> chunks = new ArrayList<>();

            try (InputStream inputStream = getContentResolver().openInputStream(selectedFileUri)) {
                while (offset < fileSize) {
                    DriveManager.Bucket selectedBucket = null;
                    long maxFreeSpace = 0;
                    for (DriveManager.Bucket bucket : freeSpaceMap.keySet()) {
                        long freeSpace = freeSpaceMap.get(bucket);
                        if (freeSpace > maxFreeSpace && freeSpace > 0) {
                            selectedBucket = bucket;
                            maxFreeSpace = freeSpace;
                        }
                    }

                    if (selectedBucket == null) {
                        throw new RuntimeException("No available buckets with free space");
                    }

                    long chunkSize = Math.min(maxFreeSpace, fileSize - offset);
                    String chunkFileName = fileName + "_part" + chunkIndex;
                    File chunkFile = createChunkFile(inputStream, chunkSize, chunkFileName);

                    Service service = selectedBucket.getDrive();
                    authenticateService(service, selectedBucket.getIndex());

                    if (service instanceof GoogleDrive) {
                        Drive driveService = GoogleDriveHelper.getDriveService(UploadFilesActivity.this, ((GoogleDrive) service).getAccountEmail());
                        if (driveService != null) {
                            com.google.api.services.drive.model.File fileMetadata = new com.google.api.services.drive.model.File();
                            fileMetadata.setName(chunkFileName);
                            try (InputStream chunkStream = new FileInputStream(chunkFile)) {
                                InputStreamContent mediaContent = new InputStreamContent(mimeType, chunkStream);
                                com.google.api.services.drive.model.File uploadedFile = driveService.files().create(fileMetadata, mediaContent).execute();
                                chunks.add(new Document("chunk_name", chunkFileName)
                                        .append("file_id", uploadedFile.getId())
                                        .append("bucket", selectedBucket.getIndex()));
                                Log.d(TAG, "Uploaded chunk " + chunkFileName + " to Google Drive bucket " + selectedBucket.getIndex());
                            }
                        }
                    } else if (service instanceof DropboxService) {
                        DbxClientV2 dropboxClient = DropboxHelper.getDropboxClient(UploadFilesActivity.this,
                                ((DropboxService) service).getAccessToken(), ((DropboxService) service).getRefreshToken());
                        if (dropboxClient != null) {
                            try (InputStream chunkStream = new FileInputStream(chunkFile)) {
                                dropboxClient.files().uploadBuilder("/" + chunkFileName).uploadAndFinish(chunkStream);
                                chunks.add(new Document("chunk_name", chunkFileName)
                                        .append("bucket", selectedBucket.getIndex()));
                                Log.d(TAG, "Uploaded chunk " + chunkFileName + " to Dropbox bucket " + selectedBucket.getIndex());
                            }
                        }
                    }

                    freeSpaceMap.put(selectedBucket, freeSpaceMap.get(selectedBucket) - chunkSize);
                    offset += chunkSize;
                    chunkIndex++;
                    chunkFile.delete();
                }
            }
            metadata.append("chunks", chunks);
        }

        private void authenticateService(Service service, int bucketNumber) throws InterruptedException {
            if (service instanceof GoogleDrive && ((GoogleDrive) service).getDriveService() == null) {
                ((GoogleDrive) service).authenticateWithEmail(bucketNumber, userId, ((GoogleDrive) service).getAccountEmail(), new Service.AuthCallback() {
                    @Override
                    public void onAuthComplete(Object result) {
                        Log.d(TAG, "Google Drive authenticated for upload: " + ((GoogleDrive) service).getAccountEmail());
                    }
                    @Override
                    public void onAuthFailed(String error) {
                        Log.e(TAG, "Google Drive authentication failed: " + error);
                    }
                });
                Thread.sleep(1000);
            } else if (service instanceof DropboxService && !((DropboxService) service).isAuthenticated()) {
                ((DropboxService) service).authenticate(bucketNumber, userId, new Service.AuthCallback() {
                    @Override
                    public void onAuthComplete(Object result) {
                        Log.d(TAG, "Dropbox authenticated for upload");
                    }
                    @Override
                    public void onAuthFailed(String error) {
                        Log.e(TAG, "Dropbox authentication failed: " + error);
                    }
                });
                Thread.sleep(1000);
            }
        }

        private File convertUriToFile(Uri uri) throws Exception {
            File file = new File(getCacheDir(), getFileName(uri));
            try (InputStream inputStream = getContentResolver().openInputStream(uri);
                 FileOutputStream outputStream = new FileOutputStream(file)) {
                byte[] buffer = new byte[1024];
                int bytesRead;
                while ((bytesRead = inputStream.read(buffer)) != -1) {
                    outputStream.write(buffer, 0, bytesRead);
                }
            }
            return file;
        }

        private File createChunkFile(InputStream inputStream, long chunkSize, String chunkFileName) throws Exception {
            File chunkFile = new File(getCacheDir(), chunkFileName);
            try (FileOutputStream outputStream = new FileOutputStream(chunkFile)) {
                byte[] buffer = new byte[1024];
                long bytesWritten = 0;
                int bytesRead;
                while (bytesWritten < chunkSize && (bytesRead = inputStream.read(buffer, 0, (int) Math.min(buffer.length, chunkSize - bytesWritten))) != -1) {
                    outputStream.write(buffer, 0, bytesRead);
                    bytesWritten += bytesRead;
                }
            }
            return chunkFile;
        }

        private String getFileName(Uri uri) {
            String fileName = "uploaded_file";
            try (Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    int nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                    if (nameIndex != -1) {
                        fileName = cursor.getString(nameIndex);
                    }
                }
            } catch (Exception e) {
                Log.e(TAG, "Failed to get file name: " + e.getMessage());
            }
            return fileName;
        }

        @Override
        protected void onPostExecute(Boolean success) {
            if (success) {
                Toast.makeText(UploadFilesActivity.this, "Upload to " + driveType + " successful!", Toast.LENGTH_SHORT).show();
            } else {
                Toast.makeText(UploadFilesActivity.this, "Upload to " + driveType + " failed.", Toast.LENGTH_SHORT).show();
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_FILE_PICK && resultCode == RESULT_OK && data != null) {
            selectedFileUri = data.getData();
            String currentText = tvSelectedFile.getText().toString();
            tvSelectedFile.setText(currentText + "\nSelected: " + selectedFileUri.getLastPathSegment());
            Log.d(TAG, "File selected: " + selectedFileUri);
        }
    }
}