package com.example.syncly;

import android.content.Context;
import android.util.Log;
import com.google.api.client.googleapis.extensions.android.gms.auth.GoogleAccountCredential;
import com.google.api.client.googleapis.javanet.GoogleNetHttpTransport;
import com.google.api.client.json.JsonFactory;
import com.google.api.client.json.gson.GsonFactory;
import com.google.api.services.drive.Drive;
import com.google.api.services.drive.DriveScopes;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.util.Collections;

public class GoogleDriveHelper {
    private static final String TAG = "GoogleDriveHelper";
    private static final JsonFactory JSON_FACTORY = GsonFactory.getDefaultInstance();

    public static Drive getDriveService(Context context, String userId) {
        try {
            if (userId == null || userId.isEmpty()) {
                Log.e(TAG, "Google Account is null or empty!");
                return null;
            }

            GoogleAccountCredential credential = GoogleAccountCredential.usingOAuth2(
                    context, Collections.singletonList(DriveScopes.DRIVE_FILE)
            );
            credential.setSelectedAccountName(userId);

            return new Drive.Builder(
                    GoogleNetHttpTransport.newTrustedTransport(),
                    JSON_FACTORY,
                    credential
            ).setApplicationName("Syncly").build();

        } catch (IOException | GeneralSecurityException e) {
            Log.e(TAG, "Error initializing Google Drive API", e);
            return null;
        }
    }

    public void storeGoogleDriveToken(String userId, int bucketNumber, String accessToken, String refreshToken) {
        MongoCollection<Document> tokensCollection = Database.getInstance().getTokensCollection();
        Document tokenDoc = new Document("user_id", userId)
                .append("bucket_number", bucketNumber)
                .append("access_token", accessToken)
                .append("refresh_token", refreshToken);
        tokensCollection.updateOne(
                new Document("user_id", userId).append("bucket_number", bucketNumber),
                new Document("$set", tokenDoc),
                new UpdateOptions().upsert(true)
        );
    }
}
