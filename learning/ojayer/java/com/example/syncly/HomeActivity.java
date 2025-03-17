package com.example.syncly;

import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

public class HomeActivity extends AppCompatActivity {

    private Button viewFilesButton, searchFilesButton, addBucketButton, uploadFilesButton, exitButton;
    private String userId; // For app logic (e.g., MongoDB username)

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_home);

        // Retrieve userId from LoginActivity
        userId = getIntent().getStringExtra("userId");

        // Initialize buttons
        viewFilesButton = findViewById(R.id.btn_view_files);
        searchFilesButton = findViewById(R.id.btn_search_files);
        addBucketButton = findViewById(R.id.btn_add_bucket);
        uploadFilesButton = findViewById(R.id.btn_upload_files);
        exitButton = findViewById(R.id.btn_exit);

        // View Files Button Click Listener
        viewFilesButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "View Files Clicked", Toast.LENGTH_SHORT).show();

            String googleAccountEmail = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                    .getString("google_account_email", null);
            String dropboxAccessToken = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                    .getString("dropbox_access_token", null);

            if (googleAccountEmail == null && dropboxAccessToken == null) {
                Toast.makeText(HomeActivity.this, "No Cloud Account Found. Please Authenticate.", Toast.LENGTH_LONG).show();
                return;
            }

            Intent intent = new Intent(HomeActivity.this, ViewFilesActivity.class);
            intent.putExtra("userId", userId);
            intent.putExtra("googleAccount", googleAccountEmail);
            intent.putExtra("dropboxAccessToken", dropboxAccessToken);
            startActivity(intent);
        });

        // Search Files Button Click Listener
        searchFilesButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Search Files Clicked", Toast.LENGTH_SHORT).show();
            Intent intent = new Intent(HomeActivity.this, SearchFilesActivity.class);
            intent.putExtra("userId", userId);
            startActivity(intent);
        });

        // Add New Bucket Button Click Listener
        addBucketButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Add Bucket Clicked", Toast.LENGTH_SHORT).show();
            Intent intent = new Intent(HomeActivity.this, AddBucketActivity.class);
            intent.putExtra("userId", userId);
            startActivity(intent);
        });

        // Upload Files Button Click Listener
        uploadFilesButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Upload Files Clicked", Toast.LENGTH_SHORT).show();

            String googleAccountEmail = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                    .getString("google_account_email", null);
            String dropboxAccessToken = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                    .getString("dropbox_access_token", null);

            if (googleAccountEmail == null && dropboxAccessToken == null) {
                Toast.makeText(HomeActivity.this, "No Cloud Account Found. Please Authenticate.", Toast.LENGTH_LONG).show();
                return;
            }

            Intent intent = new Intent(HomeActivity.this, UploadFilesActivity.class);
            intent.putExtra("userId", userId);
            intent.putExtra("googleAccount", googleAccountEmail);
            intent.putExtra("dropboxAccessToken", dropboxAccessToken);
            startActivity(intent);
        });

        // Exit Button Click Listener
        exitButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Logging Out", Toast.LENGTH_SHORT).show();
            Intent intent = new Intent(HomeActivity.this, LoginActivity.class);
            intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
            finish();
        });
    }
}