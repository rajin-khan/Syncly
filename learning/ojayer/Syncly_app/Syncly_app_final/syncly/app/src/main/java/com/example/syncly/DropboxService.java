package com.example.syncly;

import android.content.Context;
import android.util.Log;
import com.dropbox.core.DbxException;
import com.dropbox.core.DbxRequestConfig;
import com.dropbox.core.oauth.DbxCredential;
import com.dropbox.core.v2.DbxClientV2;
import com.dropbox.core.v2.files.FileMetadata;
import com.dropbox.core.v2.files.ListFolderResult;
import org.bson.Document;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class DropboxService extends Service {
    private DbxClientV2 service;
    private final String appKey;
    private final String appSecret;
    private String accessToken;
    private String refreshToken;
    private final Database db = Database.getInstance();
    private static final String TAG = "DropboxService";
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Context context;

    public DropboxService(Context context) {
        this.context = context;
        this.appKey = context.getString(R.string.dropbox_app_key);
        this.appSecret = context.getString(R.string.dropbox_app_secret);
    }

    public String getAppKey() {
        return appKey;
    }

    public String getAppSecret() {
        return appSecret;
    }

    public String getAccessToken() {
        return accessToken;
    }

    public void setAccessToken(String accessToken) {
        this.accessToken = accessToken;
    }
    public String getRefreshToken() {
        return refreshToken;
    }
    public void setRefreshToken(String refreshToken) {
        this.refreshToken = refreshToken;
    }

    public boolean isAuthenticated() {
        // Add logic to check if the client is ready, e.g., if accessToken is valid
        return accessToken != null && !accessToken.isEmpty();
    }
    @Override
    public void authenticate(final int bucketNumber, final String userId, final AuthCallback callback) {
        executor.execute(() -> {
            try {
                Document driveDoc = db.getDrivesCollection()
                        .find(new Document("user_id", userId).append("bucket_number", bucketNumber))
                        .first();
                if (driveDoc != null) {
                    accessToken = driveDoc.getString("access_token");
                    refreshToken = driveDoc.getString("refresh_token");
                }
                if (accessToken == null) {
                    Log.e(TAG, "No Dropbox access token found in database for bucket " + bucketNumber);
                    throw new IllegalStateException("Please link a Dropbox account first");
                }

                DbxCredential creds = new DbxCredential(accessToken, -1L, refreshToken, appKey, appSecret);
                service = new DbxClientV2(DbxRequestConfig.newBuilder("Syncly").build(), creds);
                service.users().getCurrentAccount();
                Log.d(TAG, "Dropbox authenticated successfully for bucket " + bucketNumber);
                callback.onAuthComplete(service);
            } catch (DbxException e) {
                Log.e(TAG, "Dropbox authentication failed: " + e.getMessage(), e);
                if (e.getMessage().contains("expired")) {
                    refreshAccessToken(callback, bucketNumber, userId);
                } else {
                    callback.onAuthFailed("Invalid Dropbox token: " + e.getMessage());
                }
            } catch (Exception e) {
                Log.e(TAG, "Unexpected error during authentication: " + e.getMessage(), e);
                callback.onAuthFailed(e.getMessage());
            }
        });
    }

    private void refreshAccessToken(AuthCallback callback, int bucketNumber, String userId) {
        try {
            DbxCredential creds = new DbxCredential(accessToken, -1L, refreshToken, appKey, appSecret);
            creds.refresh(DbxRequestConfig.newBuilder("Syncly").build());
            accessToken = creds.getAccessToken();
            refreshToken = creds.getRefreshToken();
            service = new DbxClientV2(DbxRequestConfig.newBuilder("Syncly").build(), creds);

            // Update MongoDB with new tokens
            db.getDrivesCollection().updateOne(
                    new Document("user_id", userId).append("bucket_number", bucketNumber),
                    new Document("$set", new Document("access_token", accessToken).append("refresh_token", refreshToken))
            );
            Log.d(TAG, "Dropbox token refreshed successfully for bucket " + bucketNumber);
            callback.onAuthComplete(service);
        } catch (Exception e) {
            Log.e(TAG, "Failed to refresh Dropbox token: " + e.getMessage(), e);
            callback.onAuthFailed("Failed to refresh Dropbox token: " + e.getMessage());
        }
    }

    private void listFilesRecursively(String path, List<Map<String, Object>> filesList) throws DbxException {
        ListFolderResult result = service.files().listFolder(path);
        while (true) {
            for (com.dropbox.core.v2.files.Metadata entry : result.getEntries()) {
                if (entry instanceof FileMetadata) {
                    FileMetadata file = (FileMetadata) entry;
                    Map<String, Object> fileInfo = new HashMap<>();
                    fileInfo.put("name", file.getName());
                    fileInfo.put("size", file.getSize());
                    fileInfo.put("path", "https://www.dropbox.com/home" + file.getPathDisplay());
                    fileInfo.put("provider", "Dropbox");
                    filesList.add(fileInfo);
                } else if (entry instanceof com.dropbox.core.v2.files.FolderMetadata) {
                    listFilesRecursively(entry.getPathLower(), filesList);
                }
            }
            if (!result.getHasMore()) break;
            result = service.files().listFolderContinue(result.getCursor());
        }
    }

    @Override
    public void listFiles(final Integer maxResults, final String query, final ListFilesCallback callback) {
        executor.execute(() -> {
            try {
                if (service == null) {
                    throw new IllegalStateException("Dropbox service not authenticated. Call authenticate() first.");
                }
                List<Map<String, Object>> filesList = new ArrayList<>();
                listFilesRecursively("", filesList);
                if (maxResults != null && filesList.size() > maxResults) {
                    filesList = filesList.subList(0, maxResults);
                }
                callback.onFilesListed(filesList);
            } catch (DbxException e) {
                Log.e(TAG, "Dropbox API error: " + e.getMessage());
                callback.onListFailed(e.getMessage());
            }
        });
    }

    @Override
    public void checkStorage(final StorageCallback callback) {
        executor.execute(() -> {
            try {
                if (service == null) {
                    Log.e(TAG, "Service not authenticated. Call authenticate() first.");
                    callback.onCheckFailed("Service not authenticated.");
                    return;
                }
                com.dropbox.core.v2.users.SpaceUsage usage = service.users().getSpaceUsage();
                long limit = usage.getAllocation().getIndividualValue() != null
                        ? usage.getAllocation().getIndividualValue().getAllocated()
                        : 0;
                long used = usage.getUsed();
                Log.i(TAG, "Storage usage: " + used + " bytes used out of " + limit + " bytes allocated.");
                callback.onStorageChecked(new long[]{limit, used});
            } catch (DbxException e) {
                Log.e(TAG, "Error checking storage: " + e.getMessage());
                callback.onCheckFailed(e.getMessage());
            }
        });
    }

    @Override
    protected void finalize() throws Throwable {
        super.finalize();
        executor.shutdown();
    }
}