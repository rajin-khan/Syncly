package com.example.syncly;

import android.content.Intent;
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
    private String userId;
    private DriveManager driveManager;
    private Button btnGoogleDrive, btnDropbox;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_add_bucket);

        // Initialize buttons
        btnGoogleDrive = findViewById(R.id.btn_google_drive);
        btnDropbox = findViewById(R.id.btn_dropbox);

        // Retrieve userId from HomeActivity
        userId = getIntent().getStringExtra("userId");

        // Initialize DriveManager with the current context
        String tokenDir = getFilesDir().getAbsolutePath(); // Example token directory
        driveManager = new DriveManager(userId, tokenDir, this); // Pass 'this' as the context

        // Load drives in the background
        new LoadDrivesTask().execute(userId);

        // Google Drive button click listener
        btnGoogleDrive.setOnClickListener(v -> {
            Intent intent = new Intent(AddBucketActivity.this, GoogleDriveAccountActivity.class);
            startActivityForResult(intent, REQUEST_GOOGLE_DRIVE_ACCOUNT);
        });

        // Dropbox button click listener (Remains unchanged for now)
        btnDropbox.setOnClickListener(v -> {
            authenticateDrive("Dropbox");
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
                // You can now proceed to authenticate and store this account in your system.
                authenticateDrive("Google Drive");
            }
        }
    }

    private void authenticateDrive(String driveType) {
        Log.d(TAG, "Authenticating drive: " + driveType);

        // Fetch authenticated buckets in the background
        driveManager.getAllAuthenticatedBuckets(authenticatedBuckets -> {
            // Calculate the next bucket number
            int bucketNumber = authenticatedBuckets.size() + 1;

            if ("GoogleDrive".equals(driveType)) {
                Log.d(TAG, "Initializing Google Drive authentication");
                GoogleDrive googleDrive = new GoogleDrive(AddBucketActivity.this); // Pass context
                googleDrive.authenticate(bucketNumber, userId, new Service.AuthCallback() {
                    @Override
                    public void onAuthComplete(Object result) {
                        Log.d(TAG, "Google Drive authenticated successfully");
                        runOnUiThread(() -> {
                            Toast.makeText(AddBucketActivity.this, "Google Drive authenticated successfully.", Toast.LENGTH_SHORT).show();
                        });
                        driveManager.addDrive(googleDrive, bucketNumber, driveType);
                    }

                    @Override
                    public void onAuthFailed(String error) {
                        Log.e(TAG, "Google Drive authentication failed: " + error);
                        runOnUiThread(() -> {
                            Toast.makeText(AddBucketActivity.this, "Google Drive authentication failed: " + error, Toast.LENGTH_SHORT).show();
                        });
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
                        });
                        driveManager.addDrive(dropboxService, bucketNumber, driveType);
                    }

                    @Override
                    public void onAuthFailed(String error) {
                        Log.e(TAG, "Dropbox authentication failed: " + error);
                        runOnUiThread(() -> {
                            Toast.makeText(AddBucketActivity.this, "Dropbox authentication failed: " + error, Toast.LENGTH_SHORT).show();
                        });
                    }
                });
            }
        });
    }


    private class LoadDrivesTask extends AsyncTask<String, Void, List<DriveManager.Bucket>> {
        @Override
        protected List<DriveManager.Bucket> doInBackground(String... params) {
            String userId = params[0]; // Retrieve userId from params
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
                // Update UI with the loaded drives
                for (DriveManager.Bucket bucket : buckets) {
                    Log.d(TAG, "Bucket with free space: " + bucket.getFreeSpace());
                }
            } else {
                Toast.makeText(AddBucketActivity.this, "Failed to load drives", Toast.LENGTH_SHORT).show();
            }
        }
    }
}
