package com.example.syncly;

import android.content.Context;
import android.util.Log;
import com.google.api.client.googleapis.extensions.android.gms.auth.GoogleAccountCredential;
import com.google.api.client.googleapis.javanet.GoogleNetHttpTransport;
import com.google.api.client.json.JsonFactory;
import com.google.api.client.json.gson.GsonFactory;
import com.google.api.services.drive.Drive;
import com.google.api.services.drive.DriveScopes;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.util.Collections;

public class GoogleDriveHelper {
    private static final String TAG = "GoogleDriveHelper";
    private static final JsonFactory JSON_FACTORY = GsonFactory.getDefaultInstance();

    public static Drive getDriveService(Context context, String accountEmail) {
        try {
            if (accountEmail == null || accountEmail.isEmpty()) {
                Log.e(TAG, "Google Account email is null or empty!");
                return null;
            }

            GoogleAccountCredential credential = GoogleAccountCredential.usingOAuth2(
                    context, Collections.singletonList(DriveScopes.DRIVE)); // Changed to DRIVE
            credential.setSelectedAccountName(accountEmail);
            Log.d(TAG, "Credential set for account email: " + accountEmail);

            Drive drive = new Drive.Builder(
                    GoogleNetHttpTransport.newTrustedTransport(),
                    JSON_FACTORY,
                    credential
            ).setApplicationName("Syncly").build();
            Log.d(TAG, "Drive service initialized successfully for email: " + accountEmail);
            return drive;

        } catch (IOException | GeneralSecurityException e) {
            Log.e(TAG, "Error initializing Google Drive API", e);
            return null;
        }
    }
}