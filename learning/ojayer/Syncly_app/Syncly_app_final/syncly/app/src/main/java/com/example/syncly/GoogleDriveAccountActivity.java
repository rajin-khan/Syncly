package com.example.syncly;

import android.content.Intent;
import android.os.Bundle;
import android.util.Log;
import androidx.appcompat.app.AppCompatActivity;
import com.google.android.gms.auth.api.signin.GoogleSignIn;
import com.google.android.gms.auth.api.signin.GoogleSignInAccount;
import com.google.android.gms.auth.api.signin.GoogleSignInClient;
import com.google.android.gms.auth.api.signin.GoogleSignInOptions;
import com.google.android.gms.common.api.ApiException;
import com.google.android.gms.tasks.Task;

public class GoogleDriveAccountActivity extends AppCompatActivity {
    private static final String TAG = "GoogleDriveAccountActivity";
    private static final int RC_SIGN_IN = 9001;
    private GoogleSignInClient mGoogleSignInClient;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_google_drive_account);

        // Configure sign-in to request email and full Drive scope
        GoogleSignInOptions gso = new GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
                .requestEmail()
                .requestScopes(new com.google.android.gms.common.api.Scope("https://www.googleapis.com/auth/drive")) // Changed to DRIVE
                .build();
        mGoogleSignInClient = GoogleSignIn.getClient(this, gso);

        // Sign out to ensure the account picker is shown
        mGoogleSignInClient.signOut().addOnCompleteListener(this, task -> {
            Log.d(TAG, "Signed out previous Google account to force account picker");
            Intent signInIntent = mGoogleSignInClient.getSignInIntent();
            startActivityForResult(signInIntent, RC_SIGN_IN);
        });
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == RC_SIGN_IN) {
            Task<GoogleSignInAccount> task = GoogleSignIn.getSignedInAccountFromIntent(data);
            try {
                GoogleSignInAccount account = task.getResult(ApiException.class);
                String email = account.getEmail();
                Log.d(TAG, "Sign-in successful, selected account: " + email);

                Intent resultIntent = new Intent();
                resultIntent.putExtra("googleAccountEmail", email);
                setResult(RESULT_OK, resultIntent);
                finish();
            } catch (ApiException e) {
                Log.e(TAG, "Sign-in failed: " + e.getStatusCode(), e);
                setResult(RESULT_CANCELED);
                finish();
            }
        }
    }
}