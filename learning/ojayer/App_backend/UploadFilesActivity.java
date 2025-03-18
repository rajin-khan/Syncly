package com.example.syncly;

import android.content.Intent;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import com.dropbox.core.DbxException;
import com.dropbox.core.v2.DbxClientV2;
import com.dropbox.core.v2.files.FileMetadata;
import com.google.api.client.http.FileContent;
import com.google.api.services.drive.Drive;
import com.google.api.services.drive.model.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.util.Collections;

public class UploadFilesActivity extends AppCompatActivity {
    private static final String TAG = "UploadFilesActivity";
    private static final int REQUEST_FILE_PICK = 101;
    private Uri selectedFileUri = null;
    private Button btnSelectFile, btnGoogleDrive, btnDropbox;
    private TextView tvSelectedFile;
    private Drive googleDriveService;
    private DbxClientV2 dropboxClient;
    private String userId;
    private String googleAccountEmail;
    private String dropboxAccessToken;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_upload_files);

        btnSelectFile = findViewById(R.id.btn_select_file);
        btnGoogleDrive = findViewById(R.id.btn_google_drive);
        btnDropbox = findViewById(R.id.btn_dropbox);
        tvSelectedFile = findViewById(R.id.tv_selected_file);

        userId = getIntent().getStringExtra("userId");
        Log.d(TAG, "Retrieved userId from intent: " + userId);

        // Get credentials from SharedPreferences
        googleAccountEmail = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                .getString("google_account_email", null);
        dropboxAccessToken = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                .getString("dropbox_access_token", null);
        Log.d(TAG, "Retrieved googleAccountEmail: " + googleAccountEmail);
        Log.d(TAG, "Retrieved dropboxAccessToken: " + (dropboxAccessToken != null ? "exists" : "null"));

        // Initialize services if credentials exist
        if (googleAccountEmail != null) {
            googleDriveService = GoogleDriveHelper.getDriveService(this, googleAccountEmail);
            if (googleDriveService == null) {
                Log.e(TAG, "Failed to initialize Google Drive service!");
                Toast.makeText(this, "Google Drive authentication failed.", Toast.LENGTH_LONG).show();
            } else {
                Log.d(TAG, "Google Drive service initialized");
            }
        } else {
            btnGoogleDrive.setEnabled(false);
            Log.w(TAG, "No Google Drive account linked");
        }

        if (dropboxAccessToken != null) {
            dropboxClient = DropboxHelper.getDropboxClient(this);
            if (dropboxClient == null) {
                Log.e(TAG, "Failed to initialize Dropbox client!");
                Toast.makeText(this, "Dropbox authentication failed.", Toast.LENGTH_LONG).show();
            } else {
                Log.d(TAG, "Dropbox client initialized");
            }
        } else {
            btnDropbox.setEnabled(false);
            Log.w(TAG, "No Dropbox account linked");
        }

        if (googleAccountEmail == null && dropboxAccessToken == null) {
            Toast.makeText(this, "No cloud accounts linked. Please add a bucket.", Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        btnSelectFile.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("*/*");
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            startActivityForResult(Intent.createChooser(intent, "Select a file"), REQUEST_FILE_PICK);
        });

        btnGoogleDrive.setOnClickListener(v -> {
            if (selectedFileUri == null) {
                Toast.makeText(this, "Please select a file first!", Toast.LENGTH_SHORT).show();
                return;
            }
            Toast.makeText(this, "Uploading to Google Drive...", Toast.LENGTH_SHORT).show();
            new UploadFileTask("GoogleDrive").execute(selectedFileUri);
        });

        btnDropbox.setOnClickListener(v -> {
            if (selectedFileUri == null) {
                Toast.makeText(this, "Please select a file first!", Toast.LENGTH_SHORT).show();
                return;
            }
            Toast.makeText(this, "Uploading to Dropbox...", Toast.LENGTH_SHORT).show();
            new UploadFileTask("Dropbox").execute(selectedFileUri);
        });
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_FILE_PICK && resultCode == RESULT_OK && data != null) {
            selectedFileUri = data.getData();
            tvSelectedFile.setText(selectedFileUri.getLastPathSegment());
            Log.d(TAG, "Selected file URI: " + selectedFileUri);
        }
    }

    private class UploadFileTask extends AsyncTask<Uri, Void, String> {
        private final String provider;

        UploadFileTask(String provider) {
            this.provider = provider;
        }

        @Override
        protected String doInBackground(Uri... uris) {
            Uri fileUri = uris[0];
            java.io.File filePath = FileUtils.getFileFromUri(UploadFilesActivity.this, fileUri);
            if (filePath == null) {
                Log.e(TAG, "Failed to get file path from URI: " + fileUri);
                return "Failed to get file path";
            }
            Log.d(TAG, "File path: " + filePath.getAbsolutePath());

            String mimeType = getContentResolver().getType(fileUri);
            if (mimeType == null) {
                mimeType = "application/octet-stream";
                Log.w(TAG, "MIME type not detected, using default: " + mimeType);
            }

            if ("GoogleDrive".equals(provider)) {
                if (googleDriveService == null) {
                    Log.e(TAG, "Google Drive service is not initialized.");
                    return "Google Drive service is not initialized.";
                }

                File fileMetadata = new File();
                fileMetadata.setName(filePath.getName());
                fileMetadata.setParents(Collections.singletonList("root"));

                FileContent mediaContent = new FileContent(mimeType, filePath);

                try {
                    File uploadedFile = googleDriveService.files().create(fileMetadata, mediaContent)
                            .setFields("id, name")
                            .execute();
                    Log.d(TAG, "File uploaded to Google Drive: " + uploadedFile.getName());
                    return "Uploaded to Google Drive: " + uploadedFile.getName();
                } catch (IOException e) {
                    Log.e(TAG, "Google Drive upload failed", e);
                    return "Google Drive upload failed: " + e.getMessage();
                }
            } else if ("Dropbox".equals(provider)) {
                if (dropboxClient == null) {
                    Log.e(TAG, "Dropbox client is not initialized.");
                    return "Dropbox client is not initialized.";
                }

                try {
                    FileInputStream inputStream = new FileInputStream(filePath);
                    FileMetadata uploadedFile = dropboxClient.files().uploadBuilder("/" + filePath.getName())
                            .uploadAndFinish(inputStream);
                    inputStream.close();
                    Log.d(TAG, "File uploaded to Dropbox: " + uploadedFile.getName());
                    return "Uploaded to Dropbox: " + uploadedFile.getName();
                } catch (DbxException | IOException e) {
                    Log.e(TAG, "Dropbox upload failed", e);
                    return "Dropbox upload failed: " + e.getMessage();
                }
            }
            return "Unknown provider: " + provider;
        }

        @Override
        protected void onPostExecute(String result) {
            Log.d(TAG, "Upload result: " + result);
            Toast.makeText(UploadFilesActivity.this, result, Toast.LENGTH_LONG).show();
        }
    }
}