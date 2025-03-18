package com.example.syncly;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

public class HomeActivity extends AppCompatActivity {

    private Button viewFilesButton, searchFilesButton, addBucketButton, uploadFilesButton, exitButton;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_home); // Linking the layout
        // Retrieve userId from LoginActivity
        String userId = getIntent().getStringExtra("userId");


        // Initialize buttons
        viewFilesButton = findViewById(R.id.btn_view_files);
        //searchFilesButton = findViewById(R.id.btn_search_files);
        addBucketButton = findViewById(R.id.btn_add_bucket);
        uploadFilesButton = findViewById(R.id.btn_upload_files);
        exitButton = findViewById(R.id.btn_exit);


        // View Files Button Click Listener
        viewFilesButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "View Files Clicked", Toast.LENGTH_SHORT).show();
            // Navigate to ViewFilesActivity (To be implemented)
            // Intent intent = new Intent(HomeActivity.this, ViewFilesActivity.class);
            // startActivity(intent);
        });

        // Search Files Button Click Listener
        /*searchFilesButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Search Files Clicked", Toast.LENGTH_SHORT).show();
            // Navigate to SearchFilesActivity (To be implemented)
            // Intent intent = new Intent(HomeActivity.this, SearchFilesActivity.class);
            // startActivity(intent);
        });*/

        // Add New Bucket Button Click Listener
        addBucketButton.setOnClickListener(v -> {
            // Navigate to AddBucketActivity and pass the userId
            Intent intent = new Intent(HomeActivity.this, AddBucketActivity.class);
            intent.putExtra("userId", userId); // Pass userId to AddBucketActivity
            startActivity(intent);
        });

        uploadFilesButton.setOnClickListener(v -> {
            // Retrieve saved Google and Dropbox accounts
            String googleAccount = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                    .getString("google_account_email", null);
            String dropboxAccessToken = getSharedPreferences("SynclyPrefs", MODE_PRIVATE)
                    .getString("dropbox_access_token", null);

            if (googleAccount == null && dropboxAccessToken == null) {
                Toast.makeText(HomeActivity.this, "No Cloud Account Found. Please Authenticate.", Toast.LENGTH_LONG).show();
                return;
            }

            // Navigate to UploadFilesActivity
            Intent intent = new Intent(HomeActivity.this, UploadFilesActivity.class);
            intent.putExtra("userId", googleAccount);
            intent.putExtra("dropboxAccessToken", dropboxAccessToken);
            startActivity(intent);
        });

        // Exit Button Click Listener
        exitButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Logging Out", Toast.LENGTH_SHORT).show();
            Intent intent = new Intent(HomeActivity.this, LoginActivity.class);     //Returning to Login screen
            startActivity(intent);
        });
    }
}
