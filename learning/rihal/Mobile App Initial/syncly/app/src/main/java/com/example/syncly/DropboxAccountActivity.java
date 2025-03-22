package com.example.syncly;

import android.content.Intent;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class DropboxAccountActivity extends AppCompatActivity {
    private static final String TAG = "DropboxAccountActivity";
    private static final String DROPBOX_APP_KEY = "w84emdpux17qpnj";
    private static final String DROPBOX_REDIRECT_URI = "syncly://dropbox-auth";

    private Button btnChooseAccount;
    private boolean authStarted = false;
    private String codeVerifier; // PKCE: Code verifier
    private String codeChallenge; // PKCE: Code challenge

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_dropbox_account);
        Log.d(TAG, "onCreate called");

        btnChooseAccount = findViewById(R.id.dbtn_choose_account);

        btnChooseAccount.setOnClickListener(v -> {
            Log.d(TAG, "Choose account button clicked");
            authStarted = true;
            authenticateDropbox();
        });
    }

    private void authenticateDropbox() {
        // Generate PKCE code verifier and challenge
        codeVerifier = generateCodeVerifier();
        codeChallenge = generateCodeChallenge(codeVerifier);

        String authUrl = "https://www.dropbox.com/oauth2/authorize" +
                "?client_id=" + DROPBOX_APP_KEY +
                "&response_type=code" +
                "&redirect_uri=" + Uri.encode(DROPBOX_REDIRECT_URI) +
                "&code_challenge=" + Uri.encode(codeChallenge) +
                "&code_challenge_method=S256" +
                "&token_access_type=offline" + // Request offline access for refresh_token
                "&state=dropbox_auth_state";
        Log.d(TAG, "Starting Dropbox OAuth with URL: " + authUrl);

        Intent browserIntent = new Intent(Intent.ACTION_VIEW, Uri.parse(authUrl));
        browserIntent.addFlags(Intent.FLAG_ACTIVITY_NO_HISTORY);
        startActivity(browserIntent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        Log.d(TAG, "onResume called, authStarted: " + authStarted);
        if (authStarted && !processedRedirect) { // Add flag to prevent duplicate processing
            handleIntent(getIntent());
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        Log.d(TAG, "onNewIntent called with intent: " + intent);
        if (!processedRedirect) { // Check flag here too
            handleIntent(intent);
        }
    }

    private boolean processedRedirect = false; // Add class field

    private void handleIntent(Intent intent) {
        if (intent == null || intent.getData() == null) {
            Log.d(TAG, "No intent data to handle");
            return;
        }

        Uri uri = intent.getData();
        Log.d(TAG, "Handling redirect URI: " + uri);

        if (uri != null && uri.toString().startsWith(DROPBOX_REDIRECT_URI)) {
            processedRedirect = true; // Set flag to true after processing
            String code = uri.getQueryParameter("code");
            String state = uri.getQueryParameter("state");
            String error = uri.getQueryParameter("error");

            if (error != null) {
                Log.e(TAG, "OAuth error received: " + error + ", description: " + uri.getQueryParameter("error_description"));
                Toast.makeText(this, "Dropbox authentication failed: " + error, Toast.LENGTH_LONG).show();
                finish();
                return;
            }

            if (!"dropbox_auth_state".equals(state)) {
                Log.e(TAG, "State mismatch. Expected: dropbox_auth_state, Received: " + state);
                Toast.makeText(this, "Dropbox authentication failed: Invalid state", Toast.LENGTH_LONG).show();
                finish();
                return;
            }

            if (code != null) {
                Log.d(TAG, "Authorization code received: " + code);
                new ExchangeCodeForTokenTask().execute(code);
            } else {
                Log.e(TAG, "No code found in redirect URI: " + uri);
                Toast.makeText(this, "Dropbox authentication failed: No code received", Toast.LENGTH_LONG).show();
                finish();
            }
        }
    }

    // PKCE: Generate a random code verifier
    private String generateCodeVerifier() {
        SecureRandom sr = new SecureRandom();
        byte[] code = new byte[32]; // 32 bytes = 256 bits
        sr.nextBytes(code);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(code);
    }

    // PKCE: Generate code challenge from verifier using SHA-256
    private String generateCodeChallenge(String verifier) {
        try {
            java.security.MessageDigest md = java.security.MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(verifier.getBytes("UTF-8"));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(digest);
        } catch (Exception e) {
            Log.e(TAG, "Failed to generate code challenge: " + e.getMessage(), e);
            return verifier; // Fallback (less secure)
        }
    }

    private class ExchangeCodeForTokenTask extends AsyncTask<String, Void, Map<String, String>> {
        @Override
        protected Map<String, String> doInBackground(String... codes) {
            String code = codes[0];
            try {
                URL url = new URL("https://api.dropboxapi.com/oauth2/token");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
                conn.setDoOutput(true);

                String params = "code=" + Uri.encode(code) +
                        "&grant_type=authorization_code" +
                        "&client_id=" + DROPBOX_APP_KEY +
                        "&client_secret=" + getString(R.string.dropbox_app_secret) +
                        "&redirect_uri=" + Uri.encode(DROPBOX_REDIRECT_URI) +
                        "&code_verifier=" + Uri.encode(codeVerifier);
                Log.d(TAG, "Sending token request with params: " + params);

                try (OutputStream os = conn.getOutputStream()) {
                    os.write(params.getBytes("UTF-8"));
                    os.flush();
                }

                int responseCode = conn.getResponseCode();
                if (responseCode != HttpURLConnection.HTTP_OK) {
                    BufferedReader errorReader = new BufferedReader(new InputStreamReader(conn.getErrorStream()));
                    String errorResponse = errorReader.lines().collect(Collectors.joining());
                    Log.e(TAG, "Token exchange failed with HTTP " + responseCode + ": " + errorResponse);
                    return null;
                }

                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                String response = reader.lines().collect(Collectors.joining());
                Log.d(TAG, "Token exchange response: " + response);

                JSONObject json = new JSONObject(response);
                Map<String, String> tokens = new HashMap<>();
                tokens.put("access_token", json.getString("access_token"));
                // Handle refresh_token optionally
                if (json.has("refresh_token")) {
                    tokens.put("refresh_token", json.getString("refresh_token"));
                } else {
                    Log.w(TAG, "No refresh_token in response; using access_token only");
                    tokens.put("refresh_token", null);
                }
                return tokens;
            } catch (Exception e) {
                Log.e(TAG, "Token exchange failed: " + e.getMessage(), e);
                return null;
            }
        }

        @Override
        protected void onPostExecute(Map<String, String> tokens) {
            if (tokens != null) {
                String accessToken = tokens.get("access_token");
                String refreshToken = tokens.get("refresh_token");
                Log.d(TAG, "Successfully obtained access_token: " + accessToken + ", refresh_token: " + (refreshToken != null ? refreshToken : "none"));
                Intent resultIntent = new Intent();
                resultIntent.putExtra("dropboxAccessToken", accessToken);
                resultIntent.putExtra("dropboxRefreshToken", refreshToken);
                setResult(RESULT_OK, resultIntent);
                finish();
            } else {
                Toast.makeText(DropboxAccountActivity.this, "Failed to get Dropbox token", Toast.LENGTH_LONG).show();
                finish();
            }
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        Log.d(TAG, "onDestroy called");
    }
}
