package org.example;

import com.syncly.db.MongoDBClient;
import com.syncly.service.DriveService;
import java.util.ArrayList;
import java.util.List;

public class DriveManager {
    private String userId;
    private List<DriveService> drives;
    private MongoDBClient db;

    public DriveManager(String userId) {
        this.userId = userId;
        this.drives = new ArrayList<>();
        this.db = MongoDBClient.getInstance();
        loadUserDrives();
    }

    private void loadUserDrives() {
        // Query drivesCollection and instantiate services
    }

    public void addDrive(DriveService drive, int bucketNumber, String driveType) {
        drive.authenticate(bucketNumber, userId);
        drives.add(drive);
        // Save to MongoDB
    }
}