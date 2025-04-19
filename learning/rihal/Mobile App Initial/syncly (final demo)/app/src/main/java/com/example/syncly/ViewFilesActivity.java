package com.example.syncly;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.os.Environment;
import android.util.Log;
import android.widget.Button;
import androidx.recyclerview.widget.RecyclerView;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.appcompat.widget.SearchView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.annotation.NonNull;
import com.dropbox.core.DbxException;
import com.dropbox.core.v2.DbxClientV2;
import com.dropbox.core.v2.files.FileMetadata;
import com.dropbox.core.v2.files.ListFolderResult;
import com.google.api.services.drive.Drive;
import com.google.api.services.drive.model.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;

public class ViewFilesActivity extends AppCompatActivity implements FileListAdapter.OnDownloadClickListener {
    private static final String TAG = "ViewFilesActivity";
    private static final int STORAGE_PERMISSION_CODE = 100;

    private RecyclerView recyclerViewFiles;
    private Button btnRefresh;
    private String userId;
    private DriveManager driveManager;
    private SearchView searchView;
    private FileListAdapter adapter;
    private List<Map<String, String>> fileList = new ArrayList<>();
    private Map<String, String> pendingDownloadFile; // To store file for retry after permission grant

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_view_files);

        recyclerViewFiles = findViewById(R.id.recycler_view_files);
        recyclerViewFiles.setLayoutManager(new LinearLayoutManager(this));

        adapter = new FileListAdapter(this, fileList,
                (url, name) -> {
                    try {
                        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                        startActivity(intent);
                    } catch (Exception e) {
                        Toast.makeText(ViewFilesActivity.this, "Unable to open file: " + name, Toast.LENGTH_SHORT).show();
                        Log.e(TAG, "Failed to open file: " + url, e);
                    }
                },
                this);
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

        searchView = findViewById(R.id.search_view);
        searchView.setOnQueryTextListener(new SearchView.OnQueryTextListener() {
            @Override
            public boolean onQueryTextSubmit(String query) {
                adapter.filter(query);
                return true;
            }

            @Override
            public boolean onQueryTextChange(String newText) {
                adapter.filter(newText);
                return true;
            }
        });

        // Request storage permissions
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this,
                    new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE, Manifest.permission.READ_EXTERNAL_STORAGE},
                    STORAGE_PERMISSION_CODE);
        }

        new CheckDrivesTask().execute();
    }

    @Override
    public void onDownloadClick(Map<String, String> file) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            Toast.makeText(this, "Storage permission required to download files", Toast.LENGTH_SHORT).show();
            pendingDownloadFile = file; // Store the file to retry after permission grant
            ActivityCompat.requestPermissions(this,
                    new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE, Manifest.permission.READ_EXTERNAL_STORAGE},
                    STORAGE_PERMISSION_CODE);
            return;
        }
        new DownloadFileTask(file).execute();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == STORAGE_PERMISSION_CODE) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                Toast.makeText(this, "Storage permission granted", Toast.LENGTH_SHORT).show();
                // Retry download if there was a pending file
                if (pendingDownloadFile != null) {
                    new DownloadFileTask(pendingDownloadFile).execute();
                    pendingDownloadFile = null;
                }
            } else {
                Toast.makeText(this, "Storage permission denied", Toast.LENGTH_SHORT).show();
                pendingDownloadFile = null; // Clear pending file
            }
        }
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
                latch.await();
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
                        .setPageSize(1000);
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
                                fileInfo.put("url", "https://drive.google.com/file/d/" + file.getId() + "/view");
                                fileInfo.put("file_id", file.getId());
                                fileList.add(fileInfo);
                            }
                        }
                        totalFiles += files.size();
                        Log.d(TAG, "Retrieved page with " + files.size() + " files from Google Drive for " + email + ", total so far: " + totalFiles);
                    }
                    request.setPageToken(fileListResult.getNextPageToken());
                } while (request.getPageToken() != null && !request.getPageToken().isEmpty());

                Log.d(TAG, "Listed " + totalFiles + " files from Google Drive for " + email);
            } catch (Exception e) {
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
                            fileInfo.put("url", "https://www.dropbox.com/home" + file.getPathDisplay());
                            fileInfo.put("path", file.getPathDisplay());
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

            fileList.clear();
            fileList.addAll(resultList);
            adapter.filter(searchView.getQuery().toString());
            Toast.makeText(ViewFilesActivity.this, "Listed " + fileList.size() + " files.", Toast.LENGTH_SHORT).show();
            Log.d(TAG, "Displayed " + fileList.size() + " files in RecyclerView");
        }
    }

    private class DownloadFileTask extends AsyncTask<Void, Void, Boolean> {
        private Map<String, String> file;
        private String errorMessage;

        DownloadFileTask(Map<String, String> file) {
            this.file = file;
        }

        @Override
        protected void onPreExecute() {
            Toast.makeText(ViewFilesActivity.this, "Downloading " + file.get("name") + "...", Toast.LENGTH_SHORT).show();
        }

        @Override
        protected Boolean doInBackground(Void... voids) {
            try {
                java.io.File downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                java.io.File destinationFile = new java.io.File(downloadsDir, file.get("name"));
                if (destinationFile.exists()) {
                    destinationFile = new java.io.File(downloadsDir, System.currentTimeMillis() + "_" + file.get("name"));
                }

                List<DriveManager.Bucket> buckets = driveManager.getSortedBuckets();
                for (DriveManager.Bucket bucket : buckets) {
                    Service service = bucket.getDrive();
                    int bucketIndex = bucket.getIndex();
                    String provider = file.get("provider");

                    if (provider.startsWith("Google Drive") && service instanceof GoogleDrive) {
                        GoogleDrive googleDrive = (GoogleDrive) service;
                        authenticateService(service, bucketIndex);
                        String fileId = file.get("file_id");
                        Drive driveService = GoogleDriveHelper.getDriveService(ViewFilesActivity.this, googleDrive.getAccountEmail());
                        if (driveService != null && fileId != null) {
                            try (InputStream inputStream = driveService.files().get(fileId).executeMediaAsInputStream();
                                 FileOutputStream outputStream = new FileOutputStream(destinationFile)) {
                                byte[] buffer = new byte[1024];
                                int bytesRead;
                                while ((bytesRead = inputStream.read(buffer)) != -1) {
                                    outputStream.write(buffer, 0, bytesRead);
                                }
                                return true;
                            }
                        }
                    } else if (provider.startsWith("Dropbox") && service instanceof DropboxService) {
                        DropboxService dropboxService = (DropboxService) service;
                        authenticateService(service, bucketIndex);
                        String path = file.get("path");
                        DbxClientV2 dropboxClient = DropboxHelper.getDropboxClient(ViewFilesActivity.this,
                                dropboxService.getAccessToken(), dropboxService.getRefreshToken());
                        if (dropboxClient != null && path != null) {
                            try (InputStream inputStream = dropboxClient.files().download(path).getInputStream();
                                 FileOutputStream outputStream = new FileOutputStream(destinationFile)) {
                                byte[] buffer = new byte[1024];
                                int bytesRead;
                                while ((bytesRead = inputStream.read(buffer)) != -1) {
                                    outputStream.write(buffer, 0, bytesRead);
                                }
                                return true;
                            }
                        }
                    }
                }
                errorMessage = "Failed to find matching bucket for download";
                return false;
            } catch (Exception e) {
                Log.e(TAG, "Download failed for " + file.get("name") + ": " + e.getMessage(), e);
                errorMessage = e.getMessage();
                return false;
            }
        }

        @Override
        protected void onPostExecute(Boolean success) {
            if (success) {
                Toast.makeText(ViewFilesActivity.this, file.get("name") + " downloaded successfully", Toast.LENGTH_SHORT).show();
            } else {
                Toast.makeText(ViewFilesActivity.this, "Download failed: " + errorMessage, Toast.LENGTH_LONG).show();
            }
        }

        private void authenticateService(Service service, int bucketNumber) throws InterruptedException {
            if (service instanceof GoogleDrive && ((GoogleDrive) service).getDriveService() == null) {
                ((GoogleDrive) service).authenticateWithEmail(bucketNumber, userId, ((GoogleDrive) service).getAccountEmail(), new Service.AuthCallback() {
                    @Override
                    public void onAuthComplete(Object result) {
                        Log.d(TAG, "Google Drive authenticated for download: " + ((GoogleDrive) service).getAccountEmail());
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
                        Log.d(TAG, "Dropbox authenticated for download");
                    }
                    @Override
                    public void onAuthFailed(String error) {
                        Log.e(TAG, "Dropbox authentication failed: " + error);
                    }
                });
                Thread.sleep(1000);
            }
        }
    }

    private String formatSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        int exp = (int) (Math.log(bytes) / Math.log(1024));
        String pre = "KMGTPE".charAt(exp - 1) + "";
        return String.format("%.1f %sB", bytes / Math.pow(1024, exp), pre);
    }
}