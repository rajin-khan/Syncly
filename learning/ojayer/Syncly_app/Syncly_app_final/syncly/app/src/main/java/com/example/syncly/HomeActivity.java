package com.example.syncly;

import android.content.Intent;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public class HomeActivity extends AppCompatActivity {

    private Button viewFilesButton, addBucketButton, uploadFilesButton, exitButton;
    private String userId; // ObjectId as string
    private String username; // For logging and intent extras
    private static final String TAG = "HomeActivity";
    private List<String> googleEmails = new ArrayList<>(); // Store Google Drive emails
    private List<String> dropboxTokens = new ArrayList<>(); // Store Dropbox tokens
    private DriveManager driveManager; // Added field declaration

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_home);

        userId = getIntent().getStringExtra("userId");
        username = getIntent().getStringExtra("username");
        String tokenDir = getFilesDir().getAbsolutePath();
        driveManager = DriveManager.getInstance(userId, tokenDir, this); // Initialize here

        viewFilesButton = findViewById(R.id.btn_view_files);
        addBucketButton = findViewById(R.id.btn_add_bucket);
        uploadFilesButton = findViewById(R.id.btn_upload_files);
        exitButton = findViewById(R.id.btn_exit);

        viewFilesButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "View Files Clicked", Toast.LENGTH_SHORT).show();
            new FetchAuthenticatedBucketsTask("view").execute();
        });

        addBucketButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Add Bucket Clicked", Toast.LENGTH_SHORT).show();
            Intent intent = new Intent(HomeActivity.this, AddBucketActivity.class);
            intent.putExtra("userId", userId);
            startActivity(intent);
        });

        uploadFilesButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Upload Files Clicked", Toast.LENGTH_SHORT).show();
            new FetchAuthenticatedBucketsTask("upload").execute();
        });

        exitButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Logging Out", Toast.LENGTH_SHORT).show();
            Intent intent = new Intent(HomeActivity.this, LoginActivity.class);
            intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
            finish();
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshBuckets();
    }

    private void refreshBuckets() {
        List<DriveManager.Bucket> buckets = driveManager.getSortedBuckets();
        Log.d(TAG, "Fetched authenticated buckets for view: " + buckets);
        List<String> googleEmailsLocal = new ArrayList<>(); // Local variable to avoid overwriting class field
        List<String> dropboxTokensLocal = new ArrayList<>(); // Local variable to avoid overwriting class field
        for (DriveManager.Bucket bucket : buckets) {
            Service service = bucket.getDrive();
            if (service instanceof GoogleDrive) {
                googleEmailsLocal.add(((GoogleDrive) service).getAccountEmail());
            } else if (service instanceof DropboxService) {
                dropboxTokensLocal.add(((DropboxService) service).getAccessToken());
            }
        }
        Log.d(TAG, "Authenticated buckets for view: " + buckets);
        Log.d(TAG, "Google Account Emails for view: " + googleEmailsLocal);
        Log.d(TAG, "Dropbox Access Tokens for view: " + (dropboxTokensLocal.isEmpty() ? "none" : dropboxTokensLocal));
    }

    private class FetchAuthenticatedBucketsTask extends AsyncTask<Void, Void, List<String>> {
        private final String action;

        FetchAuthenticatedBucketsTask(String action) {
            this.action = action;
        }

        @Override
        protected List<String> doInBackground(Void... params) {
            try {
                MongoCollection<Document> drivesCollection = Database.getInstance().getDrivesCollection();
                List<Document> drives = drivesCollection.find(new Document("user_id", userId)).into(new ArrayList<>());
                List<String> bucketNumbers = new ArrayList<>();
                googleEmails.clear();
                dropboxTokens.clear();
                for (Document drive : drives) {
                    String bucket = String.valueOf(drive.getInteger("bucket_number"));
                    bucketNumbers.add(bucket);
                    String googleEmail = drive.getString("account_email");
                    String dropboxToken = drive.getString("access_token");
                    Log.d(TAG, "Checking bucket " + bucket + ": Google=" + googleEmail + ", Dropbox=" + (dropboxToken != null ? "<token>" : "null"));
                    if (googleEmail != null) googleEmails.add(googleEmail);
                    if (dropboxToken != null) dropboxTokens.add(dropboxToken);
                }
                Log.d(TAG, "Fetched authenticated buckets for " + action + ": " + bucketNumbers);
                return bucketNumbers;
            } catch (Exception e) {
                Log.e(TAG, "Error fetching authenticated buckets for " + action + ": " + e.toString(), e);
                return new ArrayList<>();
            }
        }

        @Override
        protected void onPostExecute(List<String> authenticatedBuckets) {
            Log.d(TAG, "Authenticated buckets for " + action + ": " + authenticatedBuckets.toString());
            Log.d(TAG, "Google Account Emails for " + action + ": " + googleEmails);
            Log.d(TAG, "Dropbox Access Tokens for " + action + ": " + (dropboxTokens.isEmpty() ? "none" : dropboxTokens.size() + " tokens"));

            if (googleEmails.isEmpty() && dropboxTokens.isEmpty() && authenticatedBuckets.isEmpty()) {
                Toast.makeText(HomeActivity.this, "No Cloud Account Found. Please Authenticate.", Toast.LENGTH_LONG).show();
                return;
            }

            Intent intent;
            if ("view".equals(action)) {
                intent = new Intent(HomeActivity.this, ViewFilesActivity.class);
            } else {
                intent = new Intent(HomeActivity.this, UploadFilesActivity.class);
            }
            intent.putExtra("userId", userId);
            intent.putStringArrayListExtra("googleAccountEmails", new ArrayList<>(googleEmails));
            intent.putStringArrayListExtra("dropboxAccessTokens", new ArrayList<>(dropboxTokens));
            intent.putStringArrayListExtra("authenticatedBuckets", new ArrayList<>(authenticatedBuckets));
            startActivity(intent);
        }
    }
}