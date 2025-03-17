package com.example.syncly;

import android.content.Context;
import android.content.SharedPreferences;
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
                // Get token from SharedPreferences
                SharedPreferences prefs = context.getSharedPreferences("SynclyPrefs", Context.MODE_PRIVATE);
                String accessToken = prefs.getString("dropbox_access_token", null);
                if (accessToken == null) {
                    Log.e(TAG, "No Dropbox access token found in SharedPreferences");
                    callback.onAuthFailed("Please link a Dropbox account first");
                    return;
                }

                // Implicit grant flow: no refresh token or expireAt
                DbxCredential creds = new DbxCredential(accessToken, null, null, appKey, appSecret);
                service = new DbxClientV2(DbxRequestConfig.newBuilder("Syncly").build(), creds);

                // Verify the token works
                service.users().getCurrentAccount();
                Log.i(TAG, "Dropbox client initialized successfully with token from SharedPreferences");

                // Store in MongoDB (optional, with fallback)
                try {
                    if (!db.isInitialized()) db.initialize();
                    db.getTokensCollection().updateOne(
                            new Document("user_id", userId).append("bucket_number", bucketNumber),
                            new Document("$set", new Document()
                                    .append("access_token", accessToken)
                                    .append("refresh_token", null) // Implicit flow doesn’t provide this
                                    .append("app_key", appKey)
                                    .append("app_secret", appSecret)),
                            new UpdateOptions().upsert(true)
                    );
                    db.getUsersCollection().updateOne(
                            new Document("_id", userId),
                            new Document("$addToSet", new Document("drives", bucketNumber)),
                            new UpdateOptions().upsert(true)
                    );
                    Log.i(TAG, "Dropbox token stored in MongoDB for bucket " + bucketNumber);
                } catch (Exception e) {
                    Log.w(TAG, "Failed to store token in MongoDB: " + e.getMessage() + ". Using SharedPreferences token.");
                }

                callback.onAuthComplete(service);
            } catch (DbxException e) {
                Log.e(TAG, "Dropbox authentication failed: " + e.getMessage());
                callback.onAuthFailed("Invalid Dropbox token: " + e.getMessage());
            } catch (Exception e) {
                Log.e(TAG, "Unexpected error during authentication: " + e.getMessage());
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