package com.example.syncly;

import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;

public class DropboxAccountActivity extends AppCompatActivity {

    private static final String TAG = "DropboxAccountActivity";
    private static final String DROPBOX_APP_KEY = "w84emdpux17qpnj"; // Your Dropbox App Key
    private static final String DROPBOX_REDIRECT_URI = "syncly://dropbox-auth"; // Custom redirect URI

    private Button btnChooseAccount;
    private boolean authStarted = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_dropbox_account);
        Log.d(TAG, "onCreate called");

        btnChooseAccount = findViewById(R.id.btn_choose_account);

        btnChooseAccount.setOnClickListener(v -> {
            Log.d(TAG, "Choose account button clicked");
            authStarted = true;
            authenticateDropbox();
        });

        // Check if launched with redirect URI
        handleIntent(getIntent());
    }

    private void authenticateDropbox() {
        String authUrl = "https://www.dropbox.com/oauth2/authorize"
                + "?client_id=" + DROPBOX_APP_KEY
                + "&response_type=token"
                + "&redirect_uri=" + Uri.encode(DROPBOX_REDIRECT_URI);
        Log.d(TAG, "Starting Dropbox OAuth with URL: " + authUrl);

        Intent browserIntent = new Intent(Intent.ACTION_VIEW, Uri.parse(authUrl));
        browserIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_HISTORY);
        startActivity(browserIntent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        Log.d(TAG, "onResume called, authStarted: " + authStarted);
        handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        Log.d(TAG, "onNewIntent called with intent: " + intent);
        handleIntent(intent);
    }

    private void handleIntent(Intent intent) {
        Uri uri = intent.getData();
        if (uri != null) {
            Log.d(TAG, "Received URI: " + uri.toString());
            if (uri.toString().startsWith(DROPBOX_REDIRECT_URI)) {
                String fragment = uri.getFragment();
                Log.d(TAG, "Fragment: " + fragment);
                if (fragment != null) {
                    String accessToken = extractTokenFromFragment(fragment);
                    if (accessToken != null) {
                        Log.d(TAG, "Dropbox Access Token: " + accessToken);

                        SharedPreferences.Editor editor = getSharedPreferences("SynclyPrefs", MODE_PRIVATE).edit();
                        editor.putString("dropbox_access_token", accessToken);
                        editor.apply();

                        Toast.makeText(this, "Dropbox Account Linked!", Toast.LENGTH_SHORT).show();

                        Intent resultIntent = new Intent();
                        resultIntent.putExtra("dropboxAccessToken", accessToken);
                        setResult(RESULT_OK, resultIntent);
                        finish();
                    } else {
                        Log.e(TAG, "Failed to extract access token from fragment: " + fragment);
                        Toast.makeText(this, "Dropbox Authentication Failed: No token", Toast.LENGTH_LONG).show();
                    }
                } else {
                    Log.e(TAG, "No fragment in URI: " + uri);
                    Toast.makeText(this, "Dropbox Authentication Failed: Invalid redirect", Toast.LENGTH_LONG).show();
                }
            } else {
                Log.e(TAG, "URI does not match redirect URI: " + uri);
            }
            // Clear the intent data to prevent reprocessing
            intent.setData(null);
        } else if (authStarted) {
            Log.w(TAG, "No URI received after auth started. Redirect may have failed.");
            Toast.makeText(this, "Dropbox redirect failed. Please try again.", Toast.LENGTH_LONG).show();
        }
    }

    private String extractTokenFromFragment(String fragment) {
        if (fragment == null) return null;
        String[] params = fragment.split("&");
        for (String param : params) {
            if (param.startsWith("access_token=")) {
                return param.substring("access_token=".length());
            }
        }
        return null;
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        Log.d(TAG, "onDestroy called");
    }
}