package com.example.syncly;

import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.ListView;
import android.widget.SimpleAdapter;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import com.dropbox.core.DbxException;
import com.dropbox.core.v2.DbxClientV2;
import com.dropbox.core.v2.files.FileMetadata;
import com.dropbox.core.v2.files.ListFolderResult;
import com.google.api.services.drive.Drive;
import com.google.api.services.drive.model.File;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ViewFilesActivity extends AppCompatActivity {
    private static final String TAG = "ViewFilesActivity";
    private ListView listViewFiles;
    private Button btnRefresh;
    private Drive googleDriveService;
    private DbxClientV2 dropboxClient;
    private String userId;
    private String googleAccountEmail;
    private String dropboxAccessToken;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_view_files);

        listViewFiles = findViewById(R.id.list_view_files);
        btnRefresh = findViewById(R.id.btn_refresh);

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
        }

        if (dropboxAccessToken != null) {
            dropboxClient = DropboxHelper.getDropboxClient(this);
            if (dropboxClient == null) {
                Log.e(TAG, "Failed to initialize Dropbox client!");
                Toast.makeText(this, "Dropbox authentication failed.", Toast.LENGTH_LONG).show();
            } else {
                Log.d(TAG, "Dropbox client initialized");
            }
        }

        if (googleAccountEmail == null && dropboxAccessToken == null) {
            Toast.makeText(this, "No cloud accounts linked. Please add a bucket.", Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        btnRefresh.setOnClickListener(v -> {
            Toast.makeText(this, "Refreshing file list...", Toast.LENGTH_SHORT).show();
            new ListFilesTask().execute();
        });

        // Load files on start
        new ListFilesTask().execute();
    }

    private class ListFilesTask extends AsyncTask<Void, Void, List<Map<String, String>>> {
        @Override
        protected List<Map<String, String>> doInBackground(Void... voids) {
            List<Map<String, String>> fileList = new ArrayList<>();

            // List Google Drive files
            if (googleDriveService != null) {
                try {
                    Drive.Files.List request = googleDriveService.files().list()
                            .setFields("files(id, name, size)")
                            .setSpaces("drive");
                    List<File> files = request.execute().getFiles();
                    for (File file : files) {
                        Map<String, String> fileInfo = new HashMap<>();
                        fileInfo.put("name", file.getName());
                        fileInfo.put("size", file.getSize() != null ? formatSize(file.getSize()) : "Unknown");
                        fileInfo.put("provider", "Google Drive");
                        fileList.add(fileInfo);
                    }
                    Log.d(TAG, "Listed " + files.size() + " files from Google Drive");
                } catch (IOException e) {
                    Log.e(TAG, "Failed to list Google Drive files: " + e.getMessage());
                }
            }

            // List Dropbox files
            if (dropboxClient != null) {
                try {
                    ListFolderResult result = dropboxClient.files().listFolder("");
                    while (true) {
                        for (com.dropbox.core.v2.files.Metadata metadata : result.getEntries()) {
                            if (metadata instanceof FileMetadata) {
                                FileMetadata file = (FileMetadata) metadata;
                                Map<String, String> fileInfo = new HashMap<>();
                                fileInfo.put("name", file.getName());
                                fileInfo.put("size", formatSize(file.getSize()));
                                fileInfo.put("provider", "Dropbox");
                                fileList.add(fileInfo);
                            }
                        }
                        if (!result.getHasMore()) break;
                        result = dropboxClient.files().listFolderContinue(result.getCursor());
                    }
                    Log.d(TAG, "Listed files from Dropbox");
                } catch (DbxException e) {
                    Log.e(TAG, "Failed to list Dropbox files: " + e.getMessage());
                }
            }

            return fileList;
        }

        @Override
        protected void onPostExecute(List<Map<String, String>> fileList) {
            if (fileList.isEmpty()) {
                Toast.makeText(ViewFilesActivity.this, "No files found or error occurred.", Toast.LENGTH_LONG).show();
                return;
            }

            SimpleAdapter adapter = new SimpleAdapter(
                    ViewFilesActivity.this,
                    fileList,
                    android.R.layout.simple_list_item_2,
                    new String[]{"name", "size"},
                    new int[]{android.R.id.text1, android.R.id.text2}
            );
            listViewFiles.setAdapter(adapter);
            Toast.makeText(ViewFilesActivity.this, "Listed " + fileList.size() + " files.", Toast.LENGTH_SHORT).show();
            Log.d(TAG, "Displayed " + fileList.size() + " files in ListView");
        }
    }

    private String formatSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        int exp = (int) (Math.log(bytes) / Math.log(1024));
        String pre = "KMGTPE".charAt(exp - 1) + "";
        return String.format("%.1f %sB", bytes / Math.pow(1024, exp), pre);
    }
}