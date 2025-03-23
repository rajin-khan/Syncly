package com.example.syncly;

import android.content.Context;
import android.util.Log;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import com.dropbox.core.DbxException;
import com.dropbox.core.v2.DbxClientV2;
import com.google.api.services.drive.Drive;

public class DriveManager {
    private static final String TAG = "DriveManager";
    private static DriveManager instance;
    private final ObjectId userId;
    private final String tokenDir;
    private final Context context;
    private final List<Bucket> buckets = Collections.synchronizedList(new ArrayList<>());
    private final ExecutorService executorService = Executors.newSingleThreadExecutor();
    private final Database db = Database.getInstance();
    private CountDownLatch initialLoadLatch = new CountDownLatch(1);

    private DriveManager(String userId, String tokenDir, Context context) {
        this.userId = new ObjectId(userId);
        this.tokenDir = tokenDir;
        this.context = context;
        loadUserDrives();
    }

    public static synchronized DriveManager getInstance(String userId, String tokenDir, Context context) {
        if (instance == null || !instance.userId.toString().equals(userId)) {
            instance = new DriveManager(userId, tokenDir, context);
        }
        return instance;
    }

    private void loadUserDrives() {
        executorService.submit(() -> {
            try {
                MongoCollection<Document> drivesCollection = db.getDrivesCollection();
                List<Document> driveDocs = drivesCollection.find(new Document("user_id", userId.toString())).into(new ArrayList<>());
                Log.d(TAG, "Found " + driveDocs.size() + " drives for user " + userId + ": " + driveDocs);
                buckets.clear();
                for (Document doc : driveDocs) {
                    String type = doc.getString("type");
                    int bucketNumber = doc.getInteger("bucket_number");
                    Service drive = null;
                    if ("GoogleDrive".equals(type)) {
                        String accountEmail = doc.getString("account_email");
                        GoogleDrive googleDrive = new GoogleDrive(context);
                        drive = googleDrive;
                        googleDrive.setAccountEmail(accountEmail);
                        Log.d(TAG, "Loaded GoogleDrive with email: " + accountEmail + " (Bucket " + bucketNumber + ") - authentication deferred");
                    } else if ("Dropbox".equals(type)) {
                        String accessToken = doc.getString("access_token");
                        String refreshToken = doc.getString("refresh_token");
                        DropboxService dropboxService = new DropboxService(context);
                        drive = dropboxService;
                        dropboxService.setAccessToken(accessToken);
                        dropboxService.setRefreshToken(refreshToken);
                        dropboxService.authenticate(bucketNumber, userId.toString(), new Service.AuthCallback() {
                            @Override
                            public void onAuthComplete(Object result) {
                                Log.d(TAG, "Dropbox authenticated as bucket " + bucketNumber);
                            }
                            @Override
                            public void onAuthFailed(String error) {
                                Log.e(TAG, "Dropbox auth failed: " + error);
                            }
                        });
                    }
                    if (drive != null) {
                        buckets.add(new Bucket(drive, bucketNumber, context));
                    }
                }
                Log.d(TAG, "Finished loading " + buckets.size() + " drives.");
            } catch (Exception e) {
                Log.e(TAG, "Failed to load drives: " + e.getMessage(), e);
            } finally {
                initialLoadLatch.countDown();
            }
        });
    }

    public void addDrive(Service drive, int bucketNumber, String driveType) {
        executorService.submit(() -> {
            try {
                Bucket bucket = new Bucket(drive, bucketNumber, context);
                synchronized (buckets) {
                    buckets.add(bucket);
                }
                Document driveDoc = new Document("user_id", userId.toString())
                        .append("type", driveType)
                        .append("bucket_number", bucketNumber);
                if (drive instanceof GoogleDrive) {
                    String email = ((GoogleDrive) drive).getAccountEmail();
                    driveDoc.append("account_email", email);
                    Log.d(TAG, "Adding Google Drive with email: " + email);
                } else if (drive instanceof DropboxService) {
                    driveDoc.append("access_token", ((DropboxService) drive).getAccessToken())
                            .append("refresh_token", ((DropboxService) drive).getRefreshToken());
                }
                db.getDrivesCollection().insertOne(driveDoc);
                Log.d(TAG, "Inserted drive into database: " + driveDoc);

                updateUserDrivesArray();
            } catch (Exception e) {
                Log.e(TAG, "Failed to add drive: " + e.getMessage(), e);
            }
        });
    }

    private void updateUserDrivesArray() {
        synchronized (buckets) {
            List<Integer> bucketNumbers = new ArrayList<>();
            for (Bucket bucket : buckets) {
                if (!bucketNumbers.contains(bucket.getIndex())) {
                    bucketNumbers.add(bucket.getIndex());
                }
            }
            UpdateResult result = db.getUsersCollection().updateOne(
                    new Document("_id", userId),
                    new Document("$set", new Document("drives", bucketNumbers)));
            Log.d(TAG, "User drives array updated: " + bucketNumbers + ", matched: " + result.getMatchedCount() + ", modified: " + result.getModifiedCount());
        }
    }

    public List<Bucket> getSortedBuckets() {
        try {
            initialLoadLatch.await();
        } catch (InterruptedException e) {
            Log.e(TAG, "Interrupted while waiting for initial load", e);
        }
        synchronized (buckets) {
            List<Bucket> sortedBuckets = new ArrayList<>(buckets);
            Collections.sort(sortedBuckets, (b1, b2) -> Integer.compare(b1.getIndex(), b2.getIndex()));
            Log.d(TAG, "Returning sorted buckets: " + sortedBuckets.size());
            return sortedBuckets;
        }
    }

    public static class Bucket {
        private final Service drive;
        private final int index;
        private final Context context;

        // Default total space values in bytes
        private static final long GOOGLE_DRIVE_DEFAULT_TOTAL_SPACE = 15L * 1024 * 1024 * 1024; // 15 GB
        private static final long DROPBOX_DEFAULT_TOTAL_SPACE = 2L * 1024 * 1024 * 1024;     // 2 GB

        Bucket(Service drive, int index, Context context) {
            this.drive = drive;
            this.index = index;
            this.context = context;
        }

        public Service getDrive() {
            return drive;
        }

        public int getIndex() {
            return index;
        }

        public long getFreeSpace() {
            if (drive instanceof GoogleDrive) {
                Drive googleDriveService = GoogleDriveHelper.getDriveService(context, ((GoogleDrive) drive).getAccountEmail());
                if (googleDriveService != null) {
                    try {
                        com.google.api.services.drive.model.About about = googleDriveService.about().get()
                                .setFields("storageQuota")
                                .execute();
                        long limit = about.getStorageQuota().getLimit() != null ? about.getStorageQuota().getLimit() : Long.MAX_VALUE;
                        long usage = about.getStorageQuota().getUsage() != null ? about.getStorageQuota().getUsage() : 0;
                        return limit - usage;
                    } catch (Exception e) {
                        Log.e(TAG, "Failed to get Google Drive free space: " + e.getMessage());
                        return -1; // Unknown
                    }
                }
            } else if (drive instanceof DropboxService) {
                DbxClientV2 dropboxClient = DropboxHelper.getDropboxClient(context,
                        ((DropboxService) drive).getAccessToken(), ((DropboxService) drive).getRefreshToken());
                if (dropboxClient != null) {
                    try {
                        com.dropbox.core.v2.users.SpaceUsage spaceUsage = dropboxClient.users().getSpaceUsage();
                        long used = spaceUsage.getUsed();
                        long allocated = spaceUsage.getAllocation().getIndividualValue() != null ?
                                spaceUsage.getAllocation().getIndividualValue().getAllocated() : Long.MAX_VALUE;
                        return allocated - used;
                    } catch (DbxException e) {
                        Log.e(TAG, "Failed to get Dropbox free space: " + e.getMessage());
                        return -1; // Unknown
                    }
                }
            }
            return -1; // Unknown if drive is null or unrecognized
        }

        public long getTotalSpace() {
            if (drive instanceof GoogleDrive) {
                Drive googleDriveService = GoogleDriveHelper.getDriveService(context, ((GoogleDrive) drive).getAccountEmail());
                if (googleDriveService != null) {
                    try {
                        com.google.api.services.drive.model.About about = googleDriveService.about().get()
                                .setFields("storageQuota")
                                .execute();
                        Long limit = about.getStorageQuota().getLimit();
                        return (limit != null && limit > 0) ? limit : GOOGLE_DRIVE_DEFAULT_TOTAL_SPACE;
                    } catch (Exception e) {
                        Log.e(TAG, "Failed to get Google Drive total space: " + e.getMessage());
                        return GOOGLE_DRIVE_DEFAULT_TOTAL_SPACE; // Fallback to default
                    }
                }
                return GOOGLE_DRIVE_DEFAULT_TOTAL_SPACE; // Fallback if service is null
            } else if (drive instanceof DropboxService) {
                DbxClientV2 dropboxClient = DropboxHelper.getDropboxClient(context,
                        ((DropboxService) drive).getAccessToken(), ((DropboxService) drive).getRefreshToken());
                if (dropboxClient != null) {
                    try {
                        com.dropbox.core.v2.users.SpaceUsage spaceUsage = dropboxClient.users().getSpaceUsage();
                        if (spaceUsage.getAllocation().getIndividualValue() != null) {
                            long allocated = spaceUsage.getAllocation().getIndividualValue().getAllocated();
                            return allocated > 0 ? allocated : DROPBOX_DEFAULT_TOTAL_SPACE;
                        }
                        return DROPBOX_DEFAULT_TOTAL_SPACE;
                    } catch (DbxException e) {
                        Log.e(TAG, "Failed to get Dropbox total space: " + e.getMessage());
                        return DROPBOX_DEFAULT_TOTAL_SPACE; // Fallback to default
                    }
                }
                return DROPBOX_DEFAULT_TOTAL_SPACE; // Fallback if client is null
            }
            return -1; // Unknown if drive is null or unrecognized
        }
    }
}
