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
    private static final String DROPBOX_APP_KEY = "iekqmer228dhy6r"; // Replace with your actual Dropbox App Key
    private static final String DROPBOX_REDIRECT_URI = "https://www.dropbox.com/1/oauth2/redirect";

    private Button btnChooseAccount;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_dropbox_account);

        btnChooseAccount = findViewById(R.id.btn_choose_account);

        btnChooseAccount.setOnClickListener(v -> {
            // Start Dropbox OAuth 2.0 authentication in an external browser
            authenticateDropbox();
        });
    }

    private void authenticateDropbox() {
        String authUrl = "https://www.dropbox.com/oauth2/authorize"
                + "?client_id=" + DROPBOX_APP_KEY
                + "&response_type=token"
                + "&redirect_uri=" + DROPBOX_REDIRECT_URI;

        Intent browserIntent = new Intent(Intent.ACTION_VIEW, Uri.parse(authUrl));
        browserIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_HISTORY);
        startActivity(browserIntent);
    }

    @Override
    protected void onResume() {
        super.onResume();

        // Check if authentication returned a token in the redirect URI
        Uri uri = getIntent().getData();
        if (uri != null && uri.toString().startsWith(DROPBOX_REDIRECT_URI)) {
            String accessToken = uri.getQueryParameter("access_token");
            if (accessToken != null) {
                Log.d(TAG, "Dropbox Access Token: " + accessToken);

                // Save the token in SharedPreferences
                getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                        .edit()
                        .putString("dropbox_access_token", accessToken)
                        .apply();

                Toast.makeText(this, "Dropbox Account Linked!", Toast.LENGTH_SHORT).show();

                // Send the result back to AddBucketActivity
                Intent resultIntent = new Intent();
                resultIntent.putExtra("dropboxAccessToken", accessToken);
                setResult(RESULT_OK, resultIntent);
                finish();
            }
        }
    }
}
