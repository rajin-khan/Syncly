package com.example.syncly;

import android.accounts.Account;
import android.accounts.AccountManager;
import android.content.Intent;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;

import com.google.android.gms.auth.api.signin.GoogleSignIn;
import com.google.android.gms.auth.api.signin.GoogleSignInAccount;
import com.google.android.gms.auth.api.signin.GoogleSignInClient;
import com.google.android.gms.auth.api.signin.GoogleSignInOptions;
import com.google.android.gms.common.api.ApiException;
import com.google.android.gms.tasks.Task;

import com.google.api.client.googleapis.extensions.android.gms.auth.GoogleAccountCredential;
import com.google.api.client.googleapis.javanet.GoogleNetHttpTransport;
import com.google.api.client.http.HttpRequest;
import com.google.api.client.http.HttpRequestInitializer;
import com.google.api.client.json.gson.GsonFactory;
import com.google.api.services.drive.DriveScopes;
import com.mongodb.client.model.UpdateOptions;

import com.google.api.client.auth.oauth2.Credential;

import com.google.api.services.drive.Drive;
import org.bson.Document; // This import is required for Document class

import java.io.IOException;
import java.security.GeneralSecurityException;
import java.util.Collections;

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
                .requestScopes(new com.google.android.gms.common.api.Scope(DriveScopes.DRIVE))
                .build();

        mGoogleSignInClient = GoogleSignIn.getClient(this, gso);

        // Use existing button to allow multiple accounts to authenticate
        btnChooseAccount.setOnClickListener(v -> signOutAndSignIn());
    }

    private void signOutAndSignIn() {
        // Sign out the current account before starting the sign-in process
        mGoogleSignInClient.signOut().addOnCompleteListener(this, task -> {
            Log.d(TAG, "Signed out successfully.");
            // Now start the sign-in process
            signIn();
        });
    }

    private void signIn() {
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
                    Log.d(TAG, "Selected Account: " + accountEmail);
                    Toast.makeText(this, "Selected Account: " + accountEmail, Toast.LENGTH_LONG).show();

                    // Fetch next bucket number based on how many accounts are already authenticated
                    long bucketNumber = getNextBucketNumber(); // Ensure a unique bucket number for each account

                    // Store the selected account in MongoDB
                    storeGoogleDriveToken(account, (int)bucketNumber);

                    // Send the selected account's email and bucket number back to AddBucketActivity
                    Intent resultIntent = new Intent();
                    resultIntent.putExtra("selectedAccount", accountEmail);
                    resultIntent.putExtra("bucketNumber", bucketNumber);
                    setResult(RESULT_OK, resultIntent);
                    finish();
                }
            } catch (ApiException | GeneralSecurityException | IOException e) {
                Log.e(TAG, "Sign in failed", e);
                Toast.makeText(this, "Sign in failed: " + e.getMessage(), Toast.LENGTH_SHORT).show();
            }
        }
    }

    private long getNextBucketNumber() {
        // Fetch the last bucket number from the database and increment by 1
        long lastBucketNumber = Database.getInstance().getTokensCollection().countDocuments();
        return lastBucketNumber + 1;
    }

    private void storeGoogleDriveToken(GoogleSignInAccount account, int bucketNumber) throws GeneralSecurityException, IOException {
        // Use GoogleSignInAccount to get the access token for Google Drive
        String accessToken = account.getIdToken();  // This is the ID token, not the access token. Use OAuth2 flow to get access token.

        // Set up the Google Drive service with the account
        Drive googleDriveService = new Drive.Builder(
                GoogleNetHttpTransport.newTrustedTransport(),
                GsonFactory.getDefaultInstance(),
                new HttpRequestInitializer() {
                    @Override
                    public void initialize(HttpRequest request) throws IOException {
                        // Use the ID token and request access token using OAuth2.0 flow
                        request.getHeaders().setAuthorization("Bearer " + accessToken);
                    }
                })
                .setApplicationName("Syncly")
                .build();

        // Save token info in MongoDB (tokens collection)
        Database.getInstance().storeGoogleDriveToken(account.getEmail(), bucketNumber, accessToken, account.getServerAuthCode());

        // Add the drive information to the drives collection (for storing bucket info)
        Document driveDoc = new Document("user_id", account.getEmail())
                .append("type", "GoogleDrive") // Or "Dropbox" if using Dropbox
                .append("bucket_number", bucketNumber)
                .append("app_key", null) // For Google Drive, app_key is not necessary
                .append("app_secret", null); // For Google Drive, app_secret is not necessary

        Database.getInstance().getDrivesCollection().insertOne(driveDoc);

        // Update the user's drive list in MongoDB with the new bucket number (in the users collection)
        Database.getInstance().getUsersCollection().updateOne(
                new Document("_id", account.getEmail()),
                new Document("$addToSet", new Document("drives", bucketNumber)),
                new UpdateOptions().upsert(true)
        );
    }
}
