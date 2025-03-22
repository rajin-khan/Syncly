package com.example.syncly;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;
import com.dropbox.core.DbxRequestConfig;
import com.dropbox.core.oauth.DbxCredential;
import com.dropbox.core.v2.DbxClientV2;

public class DropboxHelper {
    private static final String TAG = "DropboxHelper";

    public static DbxClientV2 getDropboxClient(Context context) {
        try {
            SharedPreferences prefs = context.getSharedPreferences("SynclyPrefs", Context.MODE_PRIVATE);
            String accessToken = prefs.getString("dropbox_access_token", null);
            if (accessToken == null || accessToken.isEmpty()) {
                Log.e(TAG, "Dropbox access token is null or empty!");
                return null;
            }

            DbxCredential credential = new DbxCredential(accessToken, null, null,
                    context.getString(R.string.dropbox_app_key),
                    context.getString(R.string.dropbox_app_secret));
            DbxClientV2 client = new DbxClientV2(
                    DbxRequestConfig.newBuilder("Syncly").build(),
                    credential
            );
            Log.d(TAG, "Dropbox client initialized successfully");
            return client;
        } catch (Exception e) {
            Log.e(TAG, "Error initializing Dropbox client", e);
            return null;
        }
    }
}