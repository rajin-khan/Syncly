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
    private Drive googleDriveService; // Reference to Google Drive API service
    private String userId;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_upload_files);

        btnSelectFile = findViewById(R.id.btn_select_file);
        btnGoogleDrive = findViewById(R.id.btn_google_drive);
        tvSelectedFile = findViewById(R.id.tv_selected_file);

        // Get authenticated Google Drive service
        userId = getIntent().getStringExtra("userId");

        // If userId is still null, try retrieving from SharedPreferences
        if (userId == null || userId.isEmpty()) {
            userId = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                    .getString("google_account_email", null);
        }

        if (userId == null || userId.isEmpty()) {
            Toast.makeText(this, "No Google Account found. Please reauthenticate.", Toast.LENGTH_LONG).show();
            finish(); // Exit activity
            return;
        }

        /*if (googleDriveService == null) {
            googleDriveService = GoogleDriveHelper.getDriveService(this, userId);
        }
        if (googleDriveService == null) {
            Toast.makeText(this, "Failed to initialize Google Drive service!", Toast.LENGTH_SHORT).show();
            return;
        }*/

        googleDriveService = GoogleDriveHelper.getDriveService(this, userId);

        // File selection button click
        btnSelectFile.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("*/*"); // Allow any file type
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            startActivityForResult(Intent.createChooser(intent, "Select a file"), REQUEST_FILE_PICK);
        });

        // Upload to Google Drive button click
        btnGoogleDrive.setOnClickListener(v -> {
            if (selectedFileUri == null) {
                Toast.makeText(this, "Please select a file first!", Toast.LENGTH_SHORT).show();
                return;
            }
            if (googleDriveService == null) {
                Toast.makeText(this, "Google Drive authentication failed!", Toast.LENGTH_SHORT).show();
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
        }
    }

    private class UploadFileTask extends AsyncTask<Uri, Void, String> {
        @Override
        protected String doInBackground(Uri... uris) {
            if (googleDriveService == null) {
                return "Google Drive service is not initialized.";
            }

            Uri fileUri = uris[0];
            java.io.File filePath = FileUtils.getFileFromUri(UploadFilesActivity.this, fileUri);
            if (filePath == null) {
                return "Failed to get file path";
            }

            String mimeType = getContentResolver().getType(fileUri);
            if (mimeType == null) {
                mimeType = "application/octet-stream";
            }

            com.google.api.services.drive.model.File fileMetadata = new com.google.api.services.drive.model.File();
            fileMetadata.setName(filePath.getName());
            fileMetadata.setParents(Collections.singletonList("root"));

            FileContent mediaContent = new FileContent(mimeType, filePath);

            try {
                com.google.api.services.drive.model.File uploadedFile = googleDriveService.files().create(fileMetadata, mediaContent)
                        .setFields("id, name")
                        .execute();
                return "Uploaded: " + uploadedFile.getName();
            } catch (IOException e) {
                Log.e(TAG, "Upload failed", e);
                return "Upload failed: " + e.getMessage();
            }
        }

        @Override
        protected void onPostExecute(String result) {
            Toast.makeText(UploadFilesActivity.this, result, Toast.LENGTH_LONG).show();
        }
    }
}
