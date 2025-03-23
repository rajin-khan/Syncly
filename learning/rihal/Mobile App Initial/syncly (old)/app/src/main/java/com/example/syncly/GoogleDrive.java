package com.example.syncly;

import android.content.Context;
import android.util.Log;

import com.google.api.client.googleapis.extensions.android.gms.auth.GoogleAccountCredential;
import com.google.api.client.googleapis.javanet.GoogleNetHttpTransport;
import com.google.api.client.http.HttpTransport;
import com.google.api.client.json.JsonFactory;
import com.google.api.client.json.gson.GsonFactory;
import com.google.api.services.drive.Drive;
import com.google.api.services.drive.DriveScopes;

import java.io.IOException;
import java.security.GeneralSecurityException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class GoogleDrive extends Service {
    private static final String TAG = "GoogleDrive";
    private static final JsonFactory JSON_FACTORY = GsonFactory.getDefaultInstance();
    private final Context context;
    private Drive driveService;
    private String accountEmail;
    private int bucketNumber;
    private String userId;

    public GoogleDrive(Context context) {
        this.context = context;
    }
    public void setAccountEmail(String accountEmail) {
        this.accountEmail = accountEmail;
    }

    public Drive getDriveService() {
        return driveService;
    }

    @Override
    public void authenticate(int bucketNumber, String userId, AuthCallback callback) {
        Log.e(TAG, "authenticate() not supported. Use authenticateWithEmail instead.");
        callback.onAuthFailed("authenticate() not supported for GoogleDrive. Use authenticateWithEmail.");
    }

    public void authenticateWithEmail(int bucketNumber, String userId, String accountEmail, AuthCallback callback) {
        this.bucketNumber = bucketNumber;
        this.userId = userId;
        this.accountEmail = accountEmail;

        new Thread(() -> {
            try {
                GoogleAccountCredential credential = GoogleAccountCredential.usingOAuth2(
                        context, Collections.singletonList(DriveScopes.DRIVE)); // Changed to DRIVE
                credential.setSelectedAccountName(accountEmail);

                HttpTransport transport = GoogleNetHttpTransport.newTrustedTransport();
                driveService = new Drive.Builder(transport, JSON_FACTORY, credential)
                        .setApplicationName("Syncly")
                        .build();

                Log.d(TAG, "Google Drive authenticated successfully for: " + accountEmail + " (Bucket " + bucketNumber + ")");
                callback.onAuthComplete(driveService);
            } catch (IOException | GeneralSecurityException e) {
                Log.e(TAG, "Authentication failed for " + accountEmail + ": " + e.getMessage(), e);
                callback.onAuthFailed(e.getMessage());
            }
        }).start();
    }

    public String getAccountEmail() {
        return accountEmail;
    }

    @Override
    public void checkStorage(StorageCallback callback) {
        if (driveService == null) {
            callback.onCheckFailed("Drive service not initialized.");
            return;
        }

        new Thread(() -> {
            try {
                com.google.api.services.drive.model.About about = driveService.about().get()
                        .setFields("storageQuota")
                        .execute();
                long limit = about.getStorageQuota().getLimit() != null ? about.getStorageQuota().getLimit() : Long.MAX_VALUE;
                long usage = about.getStorageQuota().getUsage() != null ? about.getStorageQuota().getUsage() : 0;
                callback.onStorageChecked(new long[]{limit, usage});
            } catch (IOException e) {
                Log.e(TAG, "Error checking storage: " + e.getMessage());
                callback.onCheckFailed(e.getMessage());
            }
        }).start();
    }

    @Override
    public void listFiles(Integer maxResults, String query, ListFilesCallback callback) {
        if (driveService == null) {
            callback.onListFailed("Drive service not initialized.");
            return;
        }

        new Thread(() -> {
            try {
                Drive.Files.List request = driveService.files().list()
                        .setFields("files(id, name, size)")
                        .setSpaces("drive");
                if (query != null && !query.isEmpty()) {
                    request.setQ(query);
                }
                if (maxResults != null) {
                    request.setPageSize(maxResults);
                }

                List<com.google.api.services.drive.model.File> files = request.execute().getFiles();
                List<Map<String, Object>> fileList = new ArrayList<>();
                for (com.google.api.services.drive.model.File file : files) {
                    Map<String, Object> fileInfo = new HashMap<>();
                    fileInfo.put("name", file.getName());
                    fileInfo.put("size", file.getSize() != null ? file.getSize().toString() : "Unknown");
                    fileInfo.put("provider", "GoogleDrive");
                    fileInfo.put("id", file.getId());
                    fileList.add(fileInfo);
                }
                Log.d(TAG, "Listed " + files.size() + " files from Google Drive");
                callback.onFilesListed(fileList);
            } catch (IOException e) {
                Log.e(TAG, "Error listing files: " + e.getMessage());
                callback.onListFailed(e.getMessage());
            }
        }).start();
    }

    public void shutdown() {
        driveService = null;
        accountEmail = null;
        Log.d(TAG, "GoogleDrive shutdown completed.");
    }
}