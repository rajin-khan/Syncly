package com.example.syncly;

import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.ListView;
import android.widget.Toast;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import com.google.api.services.drive.Drive;
import com.google.api.services.drive.model.File;
import com.google.api.services.drive.model.FileList;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class ViewFilesActivity extends AppCompatActivity {
    private static final String TAG = "ViewFilesActivity";
    private ListView listViewFiles;
    private Button btnRefresh;
    private Drive googleDriveService;
    private String userId; // For app logic (e.g., MongoDB username)
    private String googleAccountEmail; // For Google Drive authentication
    private List<String> fileNames = new ArrayList<>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_view_files);

        listViewFiles = findViewById(R.id.list_view_files);
        btnRefresh = findViewById(R.id.btn_refresh);

        // Retrieve userId from Intent
        userId = getIntent().getStringExtra("userId");
        Log.d(TAG, "Retrieved userId from intent: " + userId);

        // Retrieve Google account email from SharedPreferences
        googleAccountEmail = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                .getString("google_account_email", null);
        Log.d(TAG, "Retrieved googleAccountEmail from SharedPreferences: " + googleAccountEmail);

        if (googleAccountEmail == null || googleAccountEmail.isEmpty()) {
            Log.e(TAG, "No Google Account email found in SharedPreferences.");
            Toast.makeText(this, "No Google Account found. Please add a Google Drive bucket.", Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        // Initialize Google Drive service with googleAccountEmail
        googleDriveService = GoogleDriveHelper.getDriveService(this, googleAccountEmail);
        if (googleDriveService == null) {
            Log.e(TAG, "Failed to initialize Google Drive service!");
            Toast.makeText(this, "Failed to initialize Google Drive service!", Toast.LENGTH_SHORT).show();
            finish();
            return;
        }
        Log.d(TAG, "Google Drive service initialized for email: " + googleAccountEmail);

        // Refresh button click listener
        btnRefresh.setOnClickListener(v -> {
            if (!isNetworkAvailable()) {
                Toast.makeText(this, "No internet connection. Please check your network.", Toast.LENGTH_LONG).show();
                return;
            }

            btnRefresh.setEnabled(false);
            Toast.makeText(this, "Refreshing file list...", Toast.LENGTH_SHORT).show();
            new ListFilesTask().execute();
        });

        // Initial load of files
        if (isNetworkAvailable()) {
            new ListFilesTask().execute();
        } else {
            Toast.makeText(this, "No internet connection. Please check your network.", Toast.LENGTH_LONG).show();
        }
    }

    private boolean isNetworkAvailable() {
        ConnectivityManager connectivityManager = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        NetworkInfo activeNetworkInfo = connectivityManager.getActiveNetworkInfo();
        return activeNetworkInfo != null && activeNetworkInfo.isConnected();
    }

    private class ListFilesTask extends AsyncTask<Void, Void, List<String>> {
        @Override
        protected List<String> doInBackground(Void... voids) {
            if (googleDriveService == null) {
                Log.e(TAG, "Google Drive service is not initialized.");
                return null;
            }

            List<String> fileNames = new ArrayList<>();
            try {
                FileList result = googleDriveService.files().list()
                        .setFields("nextPageToken, files(id, name)")
                        .execute();

                for (File file : result.getFiles()) {
                    fileNames.add(file.getName());
                    Log.d(TAG, "Found file: " + file.getName());
                }
            } catch (IOException e) {
                Log.e(TAG, "Error listing files", e);
                return null;
            }
            return fileNames;
        }

        @Override
        protected void onPostExecute(List<String> fileNames) {
            btnRefresh.setEnabled(true);

            if (fileNames == null) {
                Toast.makeText(ViewFilesActivity.this, "Failed to load files. Please check your connection.", Toast.LENGTH_LONG).show();
                return;
            }

            if (fileNames.isEmpty()) {
                Toast.makeText(ViewFilesActivity.this, "No files found.", Toast.LENGTH_SHORT).show();
            } else {
                Toast.makeText(ViewFilesActivity.this, "Loaded " + fileNames.size() + " files.", Toast.LENGTH_SHORT).show();
            }

            FileListAdapter adapter = new FileListAdapter(ViewFilesActivity.this, fileNames);
            listViewFiles.setAdapter(adapter);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (googleDriveService != null) {
            // No explicit shutdown needed for Drive service
        }
    }
}