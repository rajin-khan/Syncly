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

        // Initialize buttons
        viewFilesButton = findViewById(R.id.btn_view_files);
        searchFilesButton = findViewById(R.id.btn_search_files);
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
        searchFilesButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Search Files Clicked", Toast.LENGTH_SHORT).show();
            // Navigate to SearchFilesActivity (To be implemented)
            // Intent intent = new Intent(HomeActivity.this, SearchFilesActivity.class);
            // startActivity(intent);
        });

        // Add New Bucket Button Click Listener
        addBucketButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Add New Bucket Clicked", Toast.LENGTH_SHORT).show();
            //Navigate to AddBucketActivity
            Intent intent = new Intent(HomeActivity.this, AddBucketActivity.class);
            startActivity(intent);
        });

        // Upload Files Button Click Listener
        uploadFilesButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Upload Files Clicked", Toast.LENGTH_SHORT).show();
            // Navigate to UploadFilesActivity (To be implemented)
            // Intent intent = new Intent(HomeActivity.this, UploadFilesActivity.class);
            // startActivity(intent);
        });

        // Exit Button Click Listener
        exitButton.setOnClickListener(v -> {
            Toast.makeText(HomeActivity.this, "Exiting Application", Toast.LENGTH_SHORT).show();
            finishAffinity(); // Closes all activities and exits the app
        });
    }
}
