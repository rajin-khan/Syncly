package com.example.syncly;

import android.content.Intent;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class AddBucketActivity extends AppCompatActivity {
    private static final String TAG = "AddBucketActivity";
    private static final int REQUEST_GOOGLE_DRIVE_ACCOUNT = 1;
    private static final int REQUEST_DROPBOX_ACCOUNT = 2;

    private Button btnGoogleDrive, btnDropbox;
    private String userId;
    private DriveManager driveManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_add_bucket);

        btnGoogleDrive = findViewById(R.id.btn_drive);
        btnDropbox = findViewById(R.id.btn_dropbox);

        userId = getIntent().getStringExtra("userId");
        Log.d(TAG, "User ID: " + userId);

        String tokenDir = getFilesDir().getAbsolutePath();
        driveManager = DriveManager.getInstance(userId, tokenDir, this);

        new LoadDrivesTask().execute(userId);

        btnGoogleDrive.setOnClickListener(v -> {
            Intent intent = new Intent(AddBucketActivity.this, GoogleDriveAccountActivity.class);
            intent.putExtra("userId", userId);
            startActivityForResult(intent, REQUEST_GOOGLE_DRIVE_ACCOUNT);
        });

        btnDropbox.setOnClickListener(v -> {
            Intent intent = new Intent(AddBucketActivity.this, DropboxAccountActivity.class);
            intent.putExtra("userId", userId);
            startActivityForResult(intent, REQUEST_DROPBOX_ACCOUNT);
        });
    }

    private class LoadDrivesTask extends AsyncTask<String, Void, List<Map<String, String>>> {
        @Override
        protected List<Map<String, String>> doInBackground(String... params) {
            try {
                List<DriveManager.Bucket> buckets = driveManager.getSortedBuckets();
                List<Map<String, String>> bucketInfo = new ArrayList<>();
                for (DriveManager.Bucket bucket : buckets) {
                    long freeSpace = bucket.getFreeSpace();
                    Map<String, String> info = new HashMap<>();
                    info.put("index", String.valueOf(bucket.getIndex()));
                    info.put("freeSpace", formatSize(freeSpace));
                    bucketInfo.add(info);
                }
                return bucketInfo;
            } catch (Exception e) {
                Log.e(TAG, "Error loading drives: " + e.getMessage(), e);
                return null;
            }
        }

        @Override
        protected void onPostExecute(List<Map<String, String>> bucketInfo) {
            if (bucketInfo != null) {
                for (Map<String, String> info : bucketInfo) {
                    Log.d(TAG, "Bucket " + info.get("index") + " with free space: " + info.get("freeSpace"));
                }
            } else {
                Toast.makeText(AddBucketActivity.this, "Failed to load drives", Toast.LENGTH_SHORT).show();
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode == RESULT_OK && data != null) {
            int nextBucketNumber = getNextBucketNumber();
            if (requestCode == REQUEST_GOOGLE_DRIVE_ACCOUNT) {
                String accountEmail = data.getStringExtra("googleAccountEmail");
                Log.d(TAG, "Selected Google Drive account: " + accountEmail);
                Toast.makeText(this, "Google Drive selected: " + accountEmail, Toast.LENGTH_SHORT).show();
                if (accountEmail != null) {
                    GoogleDrive googleDrive = new GoogleDrive(this);
                    googleDrive.authenticateWithEmail(nextBucketNumber, userId, accountEmail, new Service.AuthCallback() {
                        @Override
                        public void onAuthComplete(Object result) {
                            Log.d(TAG, "Authentication completed for Google Drive: " + accountEmail);
                            driveManager.addDrive(googleDrive, nextBucketNumber, "GoogleDrive");
                            // Refresh UI or buckets after adding
                            new LoadDrivesTask().execute(userId);
                        }
                        @Override
                        public void onAuthFailed(String error) {
                            Log.e(TAG, "Google Drive authentication failed: " + error);
                            Toast.makeText(AddBucketActivity.this, "Google Drive auth failed: " + error, Toast.LENGTH_SHORT).show();
                        }
                    });
                }
            } else if (requestCode == REQUEST_DROPBOX_ACCOUNT) {
                String accessToken = data.getStringExtra("dropboxAccessToken");
                String refreshToken = data.getStringExtra("dropboxRefreshToken");
                Log.d(TAG, "Added Dropbox account with access token: " + accessToken);
                Toast.makeText(this, "Dropbox added successfully", Toast.LENGTH_SHORT).show();
                if (accessToken != null && refreshToken != null) {
                    DropboxService dropboxService = new DropboxService(this);
                    dropboxService.setAccessToken(accessToken);
                    dropboxService.setRefreshToken(refreshToken);
                    dropboxService.authenticate(nextBucketNumber, userId, new Service.AuthCallback() {
                        @Override
                        public void onAuthComplete(Object result) {
                            Log.d(TAG, "Authentication completed for Dropbox");
                            driveManager.addDrive(dropboxService, nextBucketNumber, "Dropbox");
                            new LoadDrivesTask().execute(userId);
                        }
                        @Override
                        public void onAuthFailed(String error) {
                            Log.e(TAG, "Dropbox authentication failed: " + error);
                            Toast.makeText(AddBucketActivity.this, "Dropbox auth failed: " + error, Toast.LENGTH_SHORT).show();
                        }
                    });
                }
            }
        }
    }

    private int getNextBucketNumber() {
        List<DriveManager.Bucket> buckets = driveManager.getSortedBuckets();
        if (buckets.isEmpty()) return 1;
        int maxBucket = 0;
        for (DriveManager.Bucket bucket : buckets) {
            maxBucket = Math.max(maxBucket, bucket.getIndex());
        }
        return maxBucket + 1;
    }

    private String formatSize(long bytes) {
        if (bytes < 0) return "Unknown";
        if (bytes < 1024) return bytes + " B";
        int exp = (int) (Math.log(bytes) / Math.log(1024));
        String pre = "KMGTPE".charAt(exp - 1) + "";
        return String.format("%.1f %sB", bytes / Math.pow(1024, exp), pre);
    }
}
