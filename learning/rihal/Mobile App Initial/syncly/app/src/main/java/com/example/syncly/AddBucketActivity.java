package com.example.syncly;

import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

public class AddBucketActivity extends AppCompatActivity {

    private Button btnGoogleDrive, btnDropbox;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_add_bucket); // Linking the layout

        // Initialize buttons
        btnGoogleDrive = findViewById(R.id.btn_google_drive);
        btnDropbox = findViewById(R.id.btn_dropbox);

        // Google Drive button click listener
        btnGoogleDrive.setOnClickListener(v -> {
            // Handle Google Drive authentication and storage creation
            authenticateGoogleDrive();
        });

        // Dropbox button click listener
        btnDropbox.setOnClickListener(v -> {
            // Handle Dropbox authentication and storage creation
            authenticateDropbox();
        });
    }

    private void authenticateGoogleDrive() {
        // Placeholder code for Google Drive authentication
        // Here you would add the authentication code using Google Drive SDK
        // Example: googleDriveService.authenticate(...);
        Toast.makeText(this, "Google Drive Authentication", Toast.LENGTH_SHORT).show();
        // Proceed with adding a new Google Drive bucket/storage
    }

    private void authenticateDropbox() {
        // Placeholder code for Dropbox authentication
        // Here you would add the authentication code using Dropbox SDK
        // Example: dropboxService.authenticate(...);
        Toast.makeText(this, "Dropbox Authentication", Toast.LENGTH_SHORT).show();
        // Proceed with adding a new Dropbox bucket/storage
    }
}
