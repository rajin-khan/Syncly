package com.example.syncly;

import android.content.Context;
import android.util.Log;
import com.dropbox.core.DbxRequestConfig;
import com.dropbox.core.oauth.DbxCredential;
import com.dropbox.core.v2.DbxClientV2;

public class DropboxHelper {
    private static final String TAG = "DropboxHelper";

    public static DbxClientV2 getDropboxClient(Context context, String accessToken, String refreshToken) {
        if (accessToken == null || accessToken.isEmpty()) {
            Log.e(TAG, "Access token is null or empty!");
            return null;
        }
        DbxRequestConfig config = DbxRequestConfig.newBuilder("Syncly").build();
        String appKey = context.getString(R.string.dropbox_app_key);
        String appSecret = context.getString(R.string.dropbox_app_secret);
        DbxCredential creds = new DbxCredential(accessToken, -1L, refreshToken, appKey, appSecret);
        return new DbxClientV2(config, creds);
    }
}