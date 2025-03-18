package com.example.syncly;

import android.accounts.Account;
import android.accounts.AccountManager;
import android.content.Intent;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;

import com.google.android.gms.auth.api.Auth;
import com.google.android.gms.auth.api.signin.GoogleSignIn;
import com.google.android.gms.auth.api.signin.GoogleSignInAccount;
import com.google.android.gms.auth.api.signin.GoogleSignInClient;
import com.google.android.gms.auth.api.signin.GoogleSignInOptions;
import com.google.android.gms.common.api.ApiException;
import com.google.android.gms.tasks.Task;

public class GoogleDriveAccountActivity extends AppCompatActivity {

    private static final int RC_SIGN_IN = 100;
    private static final String TAG = "GoogleDriveAccountActivity";
    private GoogleSignInClient mGoogleSignInClient;
    private Button btnChooseAccount;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_google_drive_account);

        btnChooseAccount = findViewById(R.id.btn_choose_account);

        // Configure sign-in to request Google Drive access
        GoogleSignInOptions gso = new GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
                .requestEmail()
                .requestScopes(new com.google.android.gms.common.api.Scope("https://www.googleapis.com/auth/drive.file")) // Matches DRIVE_FILE scope
                .build();

        mGoogleSignInClient = GoogleSignIn.getClient(this, gso);

        btnChooseAccount.setOnClickListener(v -> signIn());
    }

    private void signIn() {
        Log.d(TAG, "Initiating Google Sign-In");
        Intent signInIntent = mGoogleSignInClient.getSignInIntent();
        startActivityForResult(signInIntent, RC_SIGN_IN);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        if (requestCode == RC_SIGN_IN) {
            Task<GoogleSignInAccount> task = GoogleSignIn.getSignedInAccountFromIntent(data);
            try {
                GoogleSignInAccount account = task.getResult(ApiException.class);
                if (account != null) {
                    String accountEmail = account.getEmail();
                    Log.d(TAG, "Sign-in successful, selected account: " + accountEmail);
                    Toast.makeText(this, "Selected Account: " + accountEmail, Toast.LENGTH_LONG).show();

                    // Save the selected account to shared preferences
                    getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                            .edit()
                            .putString("google_account_email", accountEmail)
                            .apply();

                    // Send the selected account back to AddBucketActivity
                    Intent resultIntent = new Intent();
                    resultIntent.putExtra("selectedAccount", accountEmail);
                    setResult(RESULT_OK, resultIntent);
                    finish();
                } else {
                    Log.w(TAG, "No account retrieved from sign-in");
                    Toast.makeText(this, "No account selected", Toast.LENGTH_SHORT).show();
                }
            } catch (ApiException e) {
                Log.e(TAG, "Sign-in failed with status code: " + e.getStatusCode(), e);
                Toast.makeText(this, "Sign-in failed: " + e.getMessage(), Toast.LENGTH_SHORT).show();
            }
        }
    }
}