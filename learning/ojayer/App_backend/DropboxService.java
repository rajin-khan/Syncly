package com.example.syncly;

import android.content.Context;
import android.util.Log;
import com.dropbox.core.DbxException;
import com.dropbox.core.DbxRequestConfig;
import com.dropbox.core.oauth.DbxCredential;
import com.dropbox.core.v2.DbxClientV2;
import com.dropbox.core.v2.files.FileMetadata;
import com.dropbox.core.v2.files.ListFolderResult;
import com.mongodb.client.model.UpdateOptions;
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

    @Override
    public void authenticate(final int bucketNumber, final String userId, final AuthCallback callback) {
        executor.execute(() -> {
            try {
                Document tokenData = db.getTokensCollection()
                        .find(new Document("user_id", userId).append("bucket_number", bucketNumber))
                        .first();

                DbxCredential creds = null;
                if (tokenData != null) {
                    try {
                        creds = new DbxCredential(
                                tokenData.getString("access_token"),
                                tokenData.getLong("expireAt"),
                                tokenData.getString("refresh_token"),
                                appKey,
                                appSecret
                        );

                        // Check if the token has expired
                        if (creds.getExpiresAt() < System.currentTimeMillis()) {
                            // Refresh the token
                            DbxRequestConfig config = DbxRequestConfig.newBuilder("Syncly").build();
                            creds.refresh(config); // Refresh the token using DbxRequestConfig
                            Log.i(TAG, "Dropbox token refreshed successfully.");

                            // Update the tokens in the database after refreshing
                            db.getTokensCollection().updateOne(
                                    new Document("user_id", userId).append("bucket_number", bucketNumber),
                                    new Document("$set", new Document()
                                            .append("access_token", creds.getAccessToken())
                                            .append("refresh_token", creds.getRefreshToken())
                                            .append("expireAt", creds.getExpiresAt())),
                                    new UpdateOptions().upsert(true)
                            );
                            Log.i(TAG, "Updated Dropbox tokens in MongoDB after refresh.");
                        }

                        service = new DbxClientV2(DbxRequestConfig.newBuilder("Syncly").build(), creds);
                        service.users().getCurrentAccount();
                        Log.i(TAG, "Dropbox client initialized successfully with existing token.");
                    } catch (Exception e) {
                        Log.e(TAG, "Error loading token: " + e.getMessage() + ". Re-authenticating.");
                        creds = null;
                    }
                }

                if (creds == null || service == null) {
                    Log.i(TAG, "No valid token found. Perform OAuth flow externally and provide tokens.");
                    // TODO: Implement OAuth flow to get access token, refresh token, and expiration time
                    String accessToken = "your_access_token_here"; // Replace with real token from OAuth
                    String refreshToken = "your_refresh_token_here"; // Replace with real token from OAuth
                    long expireAt = System.currentTimeMillis() + (3600 * 1000); // Token expires in 1 hour

                    creds = new DbxCredential(accessToken, expireAt, refreshToken, appKey, appSecret);
                    service = new DbxClientV2(DbxRequestConfig.newBuilder("Syncly").build(), creds);

                    // Store the tokens in the database
                    db.getTokensCollection().updateOne(
                            new Document("user_id", userId).append("bucket_number", bucketNumber),
                            new Document("$set", new Document()
                                    .append("access_token", accessToken)
                                    .append("refresh_token", refreshToken)
                                    .append("expireAt", expireAt)
                                    .append("app_key", appKey)
                                    .append("app_secret", appSecret)),
                            new UpdateOptions().upsert(true)
                    );
                    Log.i(TAG, "New Dropbox tokens stored in MongoDB.");
                }

                db.getUsersCollection().updateOne(
                        new Document("_id", userId),
                        new Document("$addToSet", new Document("drives", bucketNumber)),
                        new UpdateOptions().upsert(true)
                );

                callback.onAuthComplete(service);
            } catch (Exception e) {
                Log.e(TAG, "Auth task failed: " + e.getMessage());
                callback.onAuthFailed(e.getMessage());
            }
        });
    }
    @Override
    public void listFiles(final Integer maxResults, final String query, final ListFilesCallback callback) {
        executor.execute(() -> {
            try {
                if (service == null) {
                    throw new IllegalStateException("Dropbox service not authenticated. Call authenticate() first.");
                }

                List<Map<String, Object>> filesList = new ArrayList<>();
                ListFolderResult result = service.files().listFolder("");
                while (true) {
                    for (com.dropbox.core.v2.files.Metadata entry : result.getEntries()) {
                        if (entry instanceof FileMetadata) {
                            FileMetadata file = (FileMetadata) entry;
                            String fileLink = "https://www.dropbox.com/home" + file.getPathDisplay();
                            Map<String, Object> fileInfo = new HashMap<>();
                            fileInfo.put("name", file.getName());
                            fileInfo.put("size", file.getSize());
                            fileInfo.put("path", fileLink);
                            fileInfo.put("provider", "Dropbox");
                            filesList.add(fileInfo);
                        }
                    }
                    if (!result.getHasMore()) break;
                    result = service.files().listFolderContinue(result.getCursor());
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
