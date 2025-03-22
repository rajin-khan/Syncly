package com.example.syncly;

import android.content.Intent;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import androidx.recyclerview.widget.RecyclerView;
import androidx.recyclerview.widget.LinearLayoutManager;
import android.widget.SimpleAdapter;
import androidx.appcompat.widget.SearchView;
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
import java.util.concurrent.CountDownLatch;

public class ViewFilesActivity extends AppCompatActivity {
    private static final String TAG = "ViewFilesActivity";
    private RecyclerView recyclerViewFiles;

    private Button btnRefresh;
    private String userId;
    private DriveManager driveManager;
    private SearchView searchView;
    private FileListAdapter adapter;
    private List<Map<String, String>> fileList = new ArrayList<>();

    private void filterFiles(String query) {
        List<Map<String, String>> filteredList = new ArrayList<>();
        for (Map<String, String> file : fileList) {
            if (file.get("name").toLowerCase().contains(query.toLowerCase())) {
                filteredList.add(file);
            }
        }
        // Update the adapter with the filtered list
        adapter = new FileListAdapter(ViewFilesActivity.this, filteredList, (url, name) -> {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            startActivity(intent);
        });
        recyclerViewFiles.setAdapter(adapter);
    }


    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_view_files);

        recyclerViewFiles = findViewById(R.id.recycler_view_files);
        recyclerViewFiles.setLayoutManager(new LinearLayoutManager(this));

        //Searchbar
        searchView = findViewById(R.id.search_view);
        //Initialize the FileListAdapter with the empty list
        adapter = new FileListAdapter(ViewFilesActivity.this, new ArrayList<>(), (url, name) -> {
            //Your onClick functionality
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            startActivity(intent);
        });
        recyclerViewFiles.setAdapter(adapter);

        btnRefresh = findViewById(R.id.btn_refresh);

        userId = getIntent().getStringExtra("userId");
        Log.d(TAG, "Retrieved userId from intent: " + userId);

        String tokenDir = getFilesDir().getAbsolutePath();
        driveManager = DriveManager.getInstance(userId, tokenDir, this);

        btnRefresh.setOnClickListener(v -> {
            Toast.makeText(this, "Refreshing file list...", Toast.LENGTH_SHORT).show();
            new ListFilesTask().execute();
        });

        new CheckDrivesTask().execute();
        // Implement search functionality
        searchView.setOnQueryTextListener(new SearchView.OnQueryTextListener() {
            @Override
            public boolean onQueryTextSubmit(String query) {
                // You can handle the query submission here (e.g., filter)
                return false;
            }

            @Override
            public boolean onQueryTextChange(String newText) {
                // Filter the displayed files based on the search text
                filterFiles(newText);
                return true;
            }
        });
    }

    private class CheckDrivesTask extends AsyncTask<Void, Void, Boolean> {
        @Override
        protected Boolean doInBackground(Void... voids) {
            long startTime = System.currentTimeMillis();
            List<DriveManager.Bucket> buckets = driveManager.getSortedBuckets();
            while (buckets.isEmpty() && (System.currentTimeMillis() - startTime < 15000)) {
                try {
                    Thread.sleep(500);
                    buckets = driveManager.getSortedBuckets();
                    Log.d(TAG, "Waiting for buckets to load... Current size: " + buckets.size());
                } catch (InterruptedException e) {
                    Log.e(TAG, "Interrupted while waiting for drives: " + e.getMessage());
                    return false;
                }
            }
            Log.d(TAG, "CheckDrivesTask completed with " + buckets.size() + " buckets.");
            return !buckets.isEmpty();
        }

        @Override
        protected void onPostExecute(Boolean hasDrives) {
            if (hasDrives) {
                Log.d(TAG, "Buckets found, proceeding to list files.");
                new ListFilesTask().execute();
            } else {
                Toast.makeText(ViewFilesActivity.this, "No cloud accounts linked or initialization failed. Please add a bucket.", Toast.LENGTH_LONG).show();
                Log.e(TAG, "No buckets available after initialization.");
                finish();
            }
        }
    }

    private class ListFilesTask extends AsyncTask<Void, Void, List<Map<String, String>>> {
        @Override
        protected List<Map<String, String>> doInBackground(Void... voids) {
            List<Map<String, String>> fileList = new ArrayList<>();
            List<DriveManager.Bucket> buckets = driveManager.getSortedBuckets();
            Log.d(TAG, "Listing files from " + buckets.size() + " buckets.");

            // Use CountDownLatch to wait for all authentications
            CountDownLatch latch = new CountDownLatch(buckets.size());

            for (DriveManager.Bucket bucket : buckets) {
                Service drive = bucket.getDrive();
                int bucketIndex = bucket.getIndex();

                if (drive instanceof GoogleDrive) {
                    GoogleDrive googleDrive = (GoogleDrive) drive;
                    googleDrive.authenticateWithEmail(bucketIndex, userId, googleDrive.getAccountEmail(), new Service.AuthCallback() {
                        @Override
                        public void onAuthComplete(Object result) {
                            Log.d(TAG, "Google Drive authenticated for bucket " + bucketIndex + ": " + googleDrive.getAccountEmail());
                            listGoogleDriveFiles(googleDrive.getAccountEmail(), fileList);
                            latch.countDown();
                        }

                        @Override
                        public void onAuthFailed(String error) {
                            Log.e(TAG, "Google Drive auth failed for bucket " + bucketIndex + ": " + error);
                            latch.countDown();
                        }
                    });
                } else if (drive instanceof DropboxService) {
                    DropboxService dropboxService = (DropboxService) drive;
                    dropboxService.authenticate(bucketIndex, userId, new Service.AuthCallback() {
                        @Override
                        public void onAuthComplete(Object result) {
                            DbxClientV2 client = (DbxClientV2) result;
                            Log.d(TAG, "Dropbox authenticated for bucket " + bucketIndex);
                            listDropboxFiles(client, fileList, bucketIndex);
                            latch.countDown();
                        }

                        @Override
                        public void onAuthFailed(String error) {
                            Log.e(TAG, "Dropbox auth failed for bucket " + bucketIndex + ": " + error);
                            latch.countDown();
                        }
                    });
                }
            }

            try {
                latch.await(); // Wait for all authentications to complete
                Log.d(TAG, "All authentications completed, fileList size: " + fileList.size());
            } catch (InterruptedException e) {
                Log.e(TAG, "Interrupted while waiting for authentications: " + e.getMessage());
            }

            return fileList;
        }

        private void listGoogleDriveFiles(String email, List<Map<String, String>> fileList) {
            Drive googleDriveService = GoogleDriveHelper.getDriveService(ViewFilesActivity.this, email);
            if (googleDriveService == null) {
                Log.e(TAG, "Google Drive service null for " + email);
                return;
            }

            try {
                Drive.Files.List request = googleDriveService.files().list()
                        .setFields("nextPageToken, files(id, name, size)")
                        .setSpaces("drive")
                        .setPageSize(1000); // Max allowed by API, adjust if needed
                int totalFiles = 0;

                do {
                    com.google.api.services.drive.model.FileList fileListResult = request.execute();
                    List<File> files = fileListResult.getFiles();
                    if (files != null) {
                        synchronized (fileList) {
                            for (File file : files) {
                                Map<String, String> fileInfo = new HashMap<>();
                                fileInfo.put("name", file.getName());
                                fileInfo.put("size", file.getSize() != null ? formatSize(file.getSize()) : "Unknown");
                                fileInfo.put("provider", "Google Drive (" + email + ")");
                                //Adding file url from drive
                                fileInfo.put("url", "https://drive.google.com/file/d/" + file.getId() + "/view");
                                fileList.add(fileInfo);
                            }
                        }
                        totalFiles += files.size();
                        Log.d(TAG, "Retrieved page with " + files.size() + " files from Google Drive for " + email + ", total so far: " + totalFiles);
                    }
                    request.setPageToken(fileListResult.getNextPageToken());
                } while (request.getPageToken() != null && !request.getPageToken().isEmpty());

                Log.d(TAG, "Listed " + totalFiles + " files from Google Drive for " + email);
            } catch (IOException e) {
                Log.e(TAG, "Failed to list Google Drive files for " + email + ": " + e.getMessage());
            }
        }

        private void listDropboxFiles(DbxClientV2 dropboxClient, List<Map<String, String>> fileList, int bucketIndex) {
            try {
                ListFolderResult result = dropboxClient.files().listFolder("");
                while (true) {
                    for (com.dropbox.core.v2.files.Metadata metadata : result.getEntries()) {
                        if (metadata instanceof FileMetadata) {
                            FileMetadata file = (FileMetadata) metadata;
                            Map<String, String> fileInfo = new HashMap<>();
                            fileInfo.put("name", file.getName());
                            fileInfo.put("size", formatSize(file.getSize()));
                            fileInfo.put("provider", "Dropbox (Bucket " + bucketIndex + ")");
                            //Adding URL to view files
                            fileInfo.put("url", "https://www.dropbox.com/home" + file.getPathDisplay());
                            synchronized (fileList) {
                                fileList.add(fileInfo);
                            }
                        }
                    }
                    if (!result.getHasMore()) break;
                    result = dropboxClient.files().listFolderContinue(result.getCursor());
                }
                Log.d(TAG, "Listed files from Dropbox for bucket " + bucketIndex);
            } catch (DbxException e) {
                Log.e(TAG, "Failed to list Dropbox files for bucket " + bucketIndex + ": " + e.getMessage());
            }
        }

        @Override
        protected void onPostExecute(List<Map<String, String>> resultList) {
            if (resultList.isEmpty()) {
                Toast.makeText(ViewFilesActivity.this, "No files found or error occurred.", Toast.LENGTH_LONG).show();
                Log.w(TAG, "File list is empty.");
                return;
            }

            //Assign to the class-level fileList
            fileList = resultList;
            //Filter the files based on search query if any
            filterFiles(searchView.getQuery().toString());

            FileListAdapter adapter = new FileListAdapter(ViewFilesActivity.this, fileList, (url, name) -> {
                try {
                    Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                    startActivity(intent);
                } catch (Exception e) {
                    Toast.makeText(ViewFilesActivity.this, "Unable to open file: " + name, Toast.LENGTH_SHORT).show();
                    Log.e(TAG, "Failed to open file: " + url, e);
                }
            });
            recyclerViewFiles.setAdapter(adapter);

            Toast.makeText(ViewFilesActivity.this, "Listed " + fileList.size() + " files.", Toast.LENGTH_SHORT).show();
            Log.d(TAG, "Displayed " + fileList.size() + " files in RecyclerView");
        }
    }

    private String formatSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        int exp = (int) (Math.log(bytes) / Math.log(1024));
        String pre = "KMGTPE".charAt(exp - 1) + "";
        return String.format("%.1f %sB", bytes / Math.pow(1024, exp), pre);
    }
}
