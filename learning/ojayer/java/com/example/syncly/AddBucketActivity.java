package com.example.syncly;

import android.content.Intent;
import android.content.SharedPreferences;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.Toast;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;

import java.util.List;

public class AddBucketActivity extends AppCompatActivity {
    private static final String TAG = "AddBucketActivity";
    private static final int REQUEST_GOOGLE_DRIVE_ACCOUNT = 200;
    private static final int REQUEST_DROPBOX_ACCOUNT = 300;
    private String userId;
    private DriveManager driveManager;
    private Button btnGoogleDrive, btnDropbox;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_add_bucket);

        btnGoogleDrive = findViewById(R.id.btn_google_drive);
        btnDropbox = findViewById(R.id.btn_dropbox);

        userId = getIntent().getStringExtra("userId");

        String tokenDir = getFilesDir().getAbsolutePath();
        driveManager = new DriveManager(userId, tokenDir, this);

        new LoadDrivesTask().execute(userId);

        btnGoogleDrive.setOnClickListener(v -> {
            Intent intent = new Intent(AddBucketActivity.this, GoogleDriveAccountActivity.class);
            startActivityForResult(intent, REQUEST_GOOGLE_DRIVE_ACCOUNT);
        });

        btnDropbox.setOnClickListener(v -> {
            Intent intent = new Intent(AddBucketActivity.this, DropboxAccountActivity.class);
            startActivityForResult(intent, REQUEST_DROPBOX_ACCOUNT);
        });
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        if (requestCode == REQUEST_GOOGLE_DRIVE_ACCOUNT && resultCode == RESULT_OK && data != null) {
            String selectedAccount = data.getStringExtra("selectedAccount");
            if (selectedAccount != null) {
                Toast.makeText(this, "Google Drive Account Added: " + selectedAccount, Toast.LENGTH_LONG).show();
                Log.d(TAG, "Added Account: " + selectedAccount);
                authenticateDrive("GoogleDrive");
            }
        }

        if (requestCode == REQUEST_DROPBOX_ACCOUNT && resultCode == RESULT_OK && data != null) {
            String dropboxAccessToken = data.getStringExtra("dropboxAccessToken");
            if (dropboxAccessToken != null) {
                Toast.makeText(this, "Dropbox Account Linked!", Toast.LENGTH_LONG).show();
                Log.d(TAG, "Added Dropbox Account with token: " + dropboxAccessToken);
                authenticateDrive("Dropbox");
            }
        }
    }

    private void authenticateDrive(String driveType) {
        Log.d(TAG, "Authenticating drive: " + driveType);

        driveManager.getAllAuthenticatedBuckets(authenticatedBuckets -> {
            int bucketNumber = authenticatedBuckets.size() + 1;

            if ("GoogleDrive".equals(driveType)) {
                Log.d(TAG, "Initializing Google Drive authentication");
                GoogleDrive googleDrive = new GoogleDrive(AddBucketActivity.this);
                googleDrive.authenticate(bucketNumber, userId, new Service.AuthCallback() {
                    @Override
                    public void onAuthComplete(Object result) {
                        Log.d(TAG, "Google Drive authenticated successfully");
                        runOnUiThread(() -> Toast.makeText(AddBucketActivity.this, "Google Drive authenticated successfully.", Toast.LENGTH_SHORT).show());
                        driveManager.addDrive(googleDrive, bucketNumber, driveType);
                    }

                    @Override
                    public void onAuthFailed(String error) {
                        Log.e(TAG, "Google Drive authentication failed: " + error);
                        runOnUiThread(() -> Toast.makeText(AddBucketActivity.this, "Google Drive authentication failed: " + error, Toast.LENGTH_SHORT).show());
                    }
                });
            } else if ("Dropbox".equals(driveType)) {
                Log.d(TAG, "Initializing Dropbox authentication");
                DropboxService dropboxService = new DropboxService(AddBucketActivity.this);
                dropboxService.authenticate(bucketNumber, userId, new Service.AuthCallback() {
                    @Override
                    public void onAuthComplete(Object result) {
                        Log.d(TAG, "Dropbox authenticated successfully");
                        runOnUiThread(() -> {
                            Toast.makeText(AddBucketActivity.this, "Dropbox authenticated successfully.", Toast.LENGTH_SHORT).show();
                            if (!Database.getInstance().isInitialized()) {
                                Toast.makeText(AddBucketActivity.this, "Note: MongoDB unavailable, data saved locally.", Toast.LENGTH_LONG).show();
                            }
                        });
                        driveManager.addDrive(dropboxService, bucketNumber, driveType);
                    }

                    @Override
                    public void onAuthFailed(String error) {
                        Log.e(TAG, "Dropbox authentication failed: " + error);
                        runOnUiThread(() -> Toast.makeText(AddBucketActivity.this, "Dropbox authentication failed: " + error, Toast.LENGTH_SHORT).show());
                    }
                });
            }
        });
    }

    private class LoadDrivesTask extends AsyncTask<String, Void, List<DriveManager.Bucket>> {
        @Override
        protected List<DriveManager.Bucket> doInBackground(String... params) {
            String userId = params[0];
            try {
                return driveManager.getSortedBuckets();
            } catch (Exception e) {
                Log.e(TAG, "Error loading drives: " + e.getMessage());
                return null;
            }
        }

        @Override
        protected void onPostExecute(List<DriveManager.Bucket> buckets) {
            if (buckets != null) {
                for (DriveManager.Bucket bucket : buckets) {
                    Log.d(TAG, "Bucket with free space: " + bucket.getFreeSpace());
                }
            } else {
                Toast.makeText(AddBucketActivity.this, "Failed to load drives", Toast.LENGTH_SHORT).show();
            }
        }
    }
}