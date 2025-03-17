package com.example.syncly;

import android.content.Context;
import android.util.Log;

import com.google.api.client.auth.oauth2.Credential;
import com.google.api.client.googleapis.auth.oauth2.GoogleAuthorizationCodeFlow;
import com.google.api.client.googleapis.auth.oauth2.GoogleClientSecrets;
import com.google.api.client.googleapis.auth.oauth2.GoogleCredential;
import com.google.api.client.googleapis.javanet.GoogleNetHttpTransport;
import com.google.api.client.http.javanet.NetHttpTransport;
import com.google.api.client.json.JsonFactory;
import com.google.api.client.json.gson.GsonFactory;
import com.google.api.services.drive.Drive;
import com.google.api.services.drive.DriveScopes;
import com.google.api.services.drive.model.File;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.UpdateOptions;
import org.bson.Document;

import java.io.IOException;
import java.io.InputStreamReader;
import java.security.GeneralSecurityException;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;

public class GoogleDrive extends Service {
    private static final String TAG = "GoogleDrive";
    private static final String CREDENTIALS_FILE = "credentials.json"; // Place in res/raw
    private static final JsonFactory JSON_FACTORY = GsonFactory.getDefaultInstance();
    private static final List<String> SCOPES = Collections.singletonList(DriveScopes.DRIVE);

    private Drive service;
    private final Context context;
    private final Database db = Database.getInstance();
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private Credential credential;

    public GoogleDrive(Context context) {
        this.context = context;
    }

    @Override
    public void authenticate(int bucketNumber, String userId, AuthCallback callback) {
        executor.execute(() -> {
            try {
                // Load client secrets
                GoogleClientSecrets clientSecrets;
                try (InputStreamReader reader = new InputStreamReader(context.getResources().openRawResource(R.raw.credentials))) {
                    clientSecrets = GoogleClientSecrets.load(JSON_FACTORY, reader);
                }

                // Build flow and trigger user authorization request
                GoogleAuthorizationCodeFlow flow = new GoogleAuthorizationCodeFlow.Builder(
                        GoogleNetHttpTransport.newTrustedTransport(),
                        JSON_FACTORY,
                        clientSecrets,
                        SCOPES)
                        .setAccessType("offline")
                        .build();

                // Check if credentials already exist in MongoDB
                Document tokenData = db.getTokensCollection()
                        .find(new Document("user_id", userId).append("bucket_number", bucketNumber))
                        .first();

                Credential credential = null;
                if (tokenData != null) {
                    // Load credentials from MongoDB
                    credential = new GoogleCredential.Builder()
                            .setTransport(flow.getTransport())
                            .setJsonFactory(JSON_FACTORY)
                            .setClientSecrets(clientSecrets)
                            .build()
                            .setAccessToken(tokenData.getString("access_token"))
                            .setRefreshToken(tokenData.getString("refresh_token"));

                    Log.d(TAG, "Loaded Google Drive credentials from MongoDB.");
                }

                if (credential == null) {
                    // Redirect user to Google's OAuth consent screen
                    String authorizationUrl = flow.newAuthorizationUrl()
                            .setRedirectUri("urn:ietf:wg:oauth:2.0:oob")
                            .build();
                    Log.d(TAG, "Authorization URL: " + authorizationUrl);
                    // TODO: Open the authorization URL in a browser or WebView
                    callback.onAuthFailed("OAuth flow not implemented; manual token setup required");
                    return;
                }

                // Create Drive service
                service = new Drive.Builder(flow.getTransport(), JSON_FACTORY, credential)
                        .setApplicationName("Syncly")
                        .build();

                // Update tokens in MongoDB
                updateTokenInDatabase(userId, bucketNumber, credential);

                callback.onAuthComplete(service);
            } catch (IOException | GeneralSecurityException e) {
                Log.e(TAG, "Google Drive authentication failed: " + e.getMessage());
                callback.onAuthFailed(e.getMessage());
            }
        });
    }

    private void updateTokenInDatabase(String userId, int bucketNumber, Credential credential) {
        MongoCollection<Document> tokensCollection = db.getTokensCollection();
        Document tokenDoc = new Document("user_id", userId)
                .append("bucket_number", bucketNumber)
                .append("access_token", credential.getAccessToken())
                .append("refresh_token", credential.getRefreshToken())
                .append("client_id", "your_client_id") // Replace with actual client ID
                .append("client_secret", "your_client_secret") // Replace with actual client secret
                .append("token_uri", "https://oauth2.googleapis.com/token")
                .append("scopes", SCOPES);
        tokensCollection.updateOne(
                new Document("user_id", userId).append("bucket_number", bucketNumber),
                new Document("$set", tokenDoc),
                new UpdateOptions().upsert(true));
    }

    @Override
    public void listFiles(Integer maxResults, String query, ListFilesCallback callback) {
        executor.execute(() -> {
            if (service == null) {
                callback.onListFailed("Drive service not initialized. Call authenticate() first.");
                return;
            }

            try {
                List<Map<String, Object>> filesList = new ArrayList<>();
                Drive.Files.List request = service.files().list()
                        .setFields("nextPageToken, files(id, name, mimeType, size)")
                        .setQ(query != null ? "name contains '" + query + "'" : null);
                if (maxResults != null) {
                    request.setPageSize(maxResults);
                }

                String pageToken = null;
                do {
                    com.google.api.services.drive.model.FileList result = request.setPageToken(pageToken).execute();
                    for (File file : result.getFiles()) {
                        Map<String, Object> fileInfo = new HashMap<>();
                        fileInfo.put("name", file.getName());
                        fileInfo.put("size", file.getSize() != null ? file.getSize().toString() : "Unknown");
                        fileInfo.put("path", "https://drive.google.com/file/d/" + file.getId() + "/view");
                        fileInfo.put("provider", "GoogleDrive");
                        filesList.add(fileInfo);
                    }
                    pageToken = result.getNextPageToken();
                } while (pageToken != null && (maxResults == null || filesList.size() < maxResults));

                callback.onFilesListed(filesList);
            } catch (IOException e) {
                callback.onListFailed("Error listing files: " + e.getMessage());
            }
        });
    }

    @Override
    public void checkStorage(StorageCallback callback) {
        executor.execute(() -> {
            if (service == null) {
                callback.onCheckFailed("Drive service not initialized. Call authenticate() first.");
                return;
            }

            try {
                Drive.About.Get about = service.about().get().setFields("storageQuota");
                com.google.api.services.drive.model.About result = about.execute();
                Long limit = result.getStorageQuota().getLimit();
                Long usage = result.getStorageQuota().getUsage();
                callback.onStorageChecked(new long[]{
                        limit != null ? limit : 0,
                        usage != null ? usage : 0
                });
            } catch (IOException e) {
                callback.onCheckFailed("Error checking storage: " + e.getMessage());
            }
        });
    }

    public Drive getService() {
        return service;
    }

    public void shutdown() {
        executor.shutdown();
    }
}
