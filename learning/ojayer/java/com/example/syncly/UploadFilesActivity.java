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
import com.google.api.client.http.FileContent;
import com.google.api.services.drive.Drive;
import com.google.api.services.drive.model.File;
import java.io.IOException;
import java.util.Collections;

public class UploadFilesActivity extends AppCompatActivity {
    private static final String TAG = "UploadFilesActivity";
    private static final int REQUEST_FILE_PICK = 101;
    private Uri selectedFileUri = null;
    private Button btnSelectFile, btnGoogleDrive;
    private TextView tvSelectedFile;
    private Drive googleDriveService;
    private String userId; // For app logic (e.g., MongoDB username)
    private String googleAccountEmail; // For Google Drive authentication

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_upload_files);

        btnSelectFile = findViewById(R.id.btn_select_file);
        btnGoogleDrive = findViewById(R.id.btn_google_drive);
        tvSelectedFile = findViewById(R.id.tv_selected_file);

        // Get userId from intent (e.g., "user1" from LoginActivity)
        userId = getIntent().getStringExtra("userId");
        Log.d(TAG, "Retrieved userId from intent: " + userId);

        // Get Google account email from SharedPreferences
        googleAccountEmail = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                .getString("google_account_email", null);
        Log.d(TAG, "Retrieved googleAccountEmail from SharedPreferences: " + googleAccountEmail);

        if (googleAccountEmail == null || googleAccountEmail.isEmpty()) {
            Log.e(TAG, "No Google Account email found in SharedPreferences.");
            Toast.makeText(this, "No Google Account found. Please add a Google Drive bucket.", Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        googleDriveService = GoogleDriveHelper.getDriveService(this, googleAccountEmail);
        if (googleDriveService == null) {
            Log.e(TAG, "Failed to initialize Google Drive service!");
            Toast.makeText(this, "Google Drive authentication failed.", Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        Log.d(TAG, "Google Drive service initialized for email: " + googleAccountEmail);

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
            Toast.makeText(this, "Uploading file...", Toast.LENGTH_SHORT).show();
            new UploadFileTask().execute(selectedFileUri);
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
        @Override
        protected String doInBackground(Uri... uris) {
            if (googleDriveService == null) {
                Log.e(TAG, "Google Drive service is not initialized.");
                return "Google Drive service is not initialized.";
            }

            Uri fileUri = uris[0];
            Log.d(TAG, "Uploading file from URI: " + fileUri);
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

            File fileMetadata = new File();
            fileMetadata.setName(filePath.getName());
            fileMetadata.setParents(Collections.singletonList("root"));

            FileContent mediaContent = new FileContent(mimeType, filePath);

            try {
                File uploadedFile = googleDriveService.files().create(fileMetadata, mediaContent)
                        .setFields("id, name")
                        .execute();
                Log.d(TAG, "File uploaded successfully: " + uploadedFile.getName());
                return "Uploaded: " + uploadedFile.getName();
            } catch (IOException e) {
                Log.e(TAG, "Upload failed", e);
                return "Upload failed: " + e.getMessage();
            }
        }

        @Override
        protected void onPostExecute(String result) {
            Log.d(TAG, "Upload result: " + result);
            Toast.makeText(UploadFilesActivity.this, result, Toast.LENGTH_LONG).show();
        }
    }
}