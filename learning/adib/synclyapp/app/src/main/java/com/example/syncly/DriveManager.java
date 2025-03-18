package com.example.syncly;

import android.content.Context;
import android.util.Log;

import com.mongodb.client.model.UpdateOptions;
import org.bson.Document;

import java.util.function.Consumer;
import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class DriveManager {
    private final String userId;
    private final List<Service> drives;
    private final String tokenDir;
    private List<Bucket> sortedBuckets;
    private final Database db;
    private final ExecutorService executor = Executors.newSingleThreadExecutor(); // Background thread executor
    private static final String TAG = "DriveManager";
    private final Context context; // Add context for GoogleDrive initialization

    public DriveManager(String userId, String tokenDir, Context context) {
        this.userId = userId;
        this.tokenDir = tokenDir;
        this.context = context; // Initialize context
        this.drives = new ArrayList<>();
        this.sortedBuckets = new ArrayList<>();
        this.db = Database.getInstance();

        // Initialize MongoDB in a background thread
        executor.execute(() -> {
            if (!db.isInitialized()) {
                db.initialize();
            }
            loadUserDrives();
        });

        File dir = new File(tokenDir);
        if (!dir.exists()) {
            dir.mkdirs();
        }
    }

    public void loadUserDrives() {
        List<Document> userDrives = db.getDrivesCollection()
                .find(new Document("user_id", userId))
                .into(new ArrayList<>());

        List<Future<Void>> futures = new ArrayList<>();
        for (Document drive : userDrives) {
            String driveType = drive.getString("type");
            int bucketNumber = drive.getInteger("bucket_number");

            // Authenticate Google Drive accounts stored in MongoDB
            Future<Void> future = executor.submit(new Callable<Void>() {
                @Override
                public Void call() {
                    if ("GoogleDrive".equals(driveType)) {
                        GoogleDrive gd = new GoogleDrive(context); // Pass context to GoogleDrive
                        gd.authenticate(bucketNumber, userId, new Service.AuthCallback() {
                            @Override
                            public void onAuthComplete(Object result) {
                                synchronized (drives) {
                                    drives.add(gd); // Add authenticated Google Drive account
                                }
                                Log.d(TAG, "GoogleDrive authenticated successfully.");
                            }

                            @Override
                            public void onAuthFailed(String error) {
                                Log.e(TAG, "GoogleDrive authentication failed: " + error);
                            }
                        });
                    } else if ("Dropbox".equals(driveType)) {
                        String appKey = drive.getString("app_key");
                        String appSecret = drive.getString("app_secret");
                        DropboxService dbx = new DropboxService(context); // Pass context to DropboxService
                        dbx.authenticate(bucketNumber, userId, new Service.AuthCallback() {
                            @Override
                            public void onAuthComplete(Object result) {
                                synchronized (drives) {
                                    drives.add(dbx); // Add Dropbox service
                                }
                                Log.d(TAG, "Dropbox authenticated successfully.");
                            }

                            @Override
                            public void onAuthFailed(String error) {
                                Log.e(TAG, "Dropbox authentication failed: " + error);
                            }
                        });
                    }
                    return null;
                }
            });
            futures.add(future);
        }

        // Wait for all futures to complete
        for (Future<Void> future : futures) {
            try {
                future.get(); // Blocks until the task is complete
            } catch (InterruptedException | ExecutionException e) {
                Log.e(TAG, "Error loading user drives: " + e.getMessage());
            }
        }
    }


    public void addDrive(Service drive, int bucketNumber, String driveType) {
        Future<Void> future = executor.submit(new Callable<Void>() {
            @Override
            public Void call() {
                drive.authenticate(bucketNumber, userId, new Service.AuthCallback() {
                    @Override
                    public void onAuthComplete(Object result) {
                        synchronized (drives) {
                            drives.add(drive);
                        }
                        Log.d(TAG, driveType + " added successfully as bucket " + bucketNumber);

                        Document driveDoc = new Document()
                                .append("user_id", userId)
                                .append("type", driveType)
                                .append("bucket_number", bucketNumber)
                                .append("app_key", drive instanceof DropboxService ? ((DropboxService) drive).getAppKey() : null)
                                .append("app_secret", drive instanceof DropboxService ? ((DropboxService) drive).getAppSecret() : null);

                        db.getDrivesCollection().insertOne(driveDoc);

                        // Update the user's drives list in MongoDB
                        db.getUsersCollection().updateOne(
                                new Document("_id", userId),
                                new Document("$addToSet", new Document("drives", bucketNumber)),
                                new UpdateOptions().upsert(true)
                        );
                    }

                    @Override
                    public void onAuthFailed(String error) {
                        Log.e(TAG, "Failed to authenticate drive: " + error);
                    }
                });
                return null;
            }
        });

        try {
            future.get(); // Blocks until the task is complete
        } catch (InterruptedException | ExecutionException e) {
            Log.e(TAG, "Error adding drive: " + e.getMessage());
        }
    }


    public Map<String, Object> checkAllStorages() {
        sortedBuckets.clear();
        List<Map<String, Object>> storageInfo = Collections.synchronizedList(new ArrayList<>());
        long[] totals = new long[]{0, 0}; // [totalLimit, totalUsage]

        List<Future<Void>> futures = new ArrayList<>();
        for (int i = 0; i < drives.size(); i++) {
            final int driveIndex = i;
            Service drive = drives.get(i);
            Future<Void> future = executor.submit(new Callable<Void>() {
                @Override
                public Void call() {
                    drive.checkStorage(new Service.StorageCallback() {
                        @Override
                        public void onStorageChecked(long[] storage) {
                            long limit = storage[0];
                            long usage = storage[1];
                            long free = limit - usage;

                            synchronized (sortedBuckets) {
                                if (free > 0) {
                                    sortedBuckets.add(new Bucket(free, drive, driveIndex));
                                }
                            }

                            synchronized (totals) {
                                totals[0] += limit;
                                totals[1] += usage;
                            }

                            Map<String, Object> info = new HashMap<>();
                            info.put("Drive Number", driveIndex + 1);
                            info.put("Storage Limit (GB)", limit / Math.pow(1024, 3));
                            info.put("Used Storage (GB)", usage / Math.pow(1024, 3));
                            info.put("Free Storage (GB)", free / Math.pow(1024, 3));
                            info.put("Provider", drive.getClass().getSimpleName());
                            storageInfo.add(info);
                        }

                        @Override
                        public void onCheckFailed(String error) {
                            Log.e(TAG, "Error checking storage for drive " + driveIndex + ": " + error);
                        }
                    });
                    return null;
                }
            });
            futures.add(future);
        }

        // Wait for all futures to complete
        for (Future<Void> future : futures) {
            try {
                future.get();
            } catch (InterruptedException | ExecutionException e) {
                Log.e(TAG, "Error checking storages: " + e.getMessage());
            }
        }

        Collections.sort(sortedBuckets, (a, b) -> Long.compare(b.getFreeSpace(), a.getFreeSpace()));

        Map<String, Object> result = new HashMap<>();
        result.put("storageInfo", storageInfo);
        result.put("totalLimit", totals[0]);
        result.put("totalUsage", totals[1]);
        return result;
    }

    public List<Bucket> getSortedBuckets() {
        return sortedBuckets;
    }

    public void updateSortedBuckets() {
        checkAllStorages();
    }

    public void getAllAuthenticatedBuckets(Consumer<List<String>> callback) {
        executor.execute(() -> {
            List<String> authenticatedBuckets = new ArrayList<>();
            try {
                List<Document> tokens = db.getTokensCollection()
                        .find(new Document("user_id", userId))
                        .into(new ArrayList<>());
                for (Document token : tokens) {
                    authenticatedBuckets.add(String.valueOf(token.getInteger("bucket_number")));
                }
            } catch (Exception e) {
                Log.e(TAG, "Error fetching authenticated buckets: " + e.getMessage());
            }
            callback.accept(authenticatedBuckets);
        });
    }


    public static String[] parsePartInfo(String fileName) {
        String[] patterns = {
                "^(.*?)\\.part(\\d+)$",                // .part0, .part1
                "^(.*?)_part[_\\-]?(\\d+)(\\..*)?$",   // _part0, _part_1, _part-2
                "^(.*?)\\.(\\d+)$",                    // .000, .001
                "^(.*?)(\\d{3})(\\..*)?$"              // Generic 3-digit numbering (e.g., .001)
        };

        for (String pattern : patterns) {
            Matcher matcher = Pattern.compile(pattern).matcher(fileName);
            if (matcher.matches()) {
                String base = matcher.group(1);
                String partNum = matcher.group(2);
                if (pattern.equals(patterns[1]) && matcher.groupCount() >= 3 && matcher.group(3) != null) {
                    base += matcher.group(3);
                } else if (pattern.equals(patterns[3]) && matcher.groupCount() >= 3 && matcher.group(3) != null) {
                    base += matcher.group(3);
                }
                return new String[]{base, partNum};
            }
        }
        return new String[]{null, null};
    }

    private List<Map<String, Object>> getFilesFromDrive(Service drive, String query) {
        Future<List<Map<String, Object>>> future = executor.submit(new Callable<List<Map<String, Object>>>() {
            @Override
            public List<Map<String, Object>> call() {
                final List<Map<String, Object>> filesList = new ArrayList<>();
                drive.listFiles(null, query, new Service.ListFilesCallback() {
                    @Override
                    public void onFilesListed(List<Map<String, Object>> files) {
                        filesList.addAll(files);
                    }

                    @Override
                    public void onListFailed(String error) {
                        Log.e(TAG, "Error retrieving files from " + drive.getClass().getSimpleName() + ": " + error);
                    }
                });
                return filesList;
            }
        });

        try {
            return future.get();
        } catch (InterruptedException | ExecutionException e) {
            Log.e(TAG, "Error getting files from drive: " + e.getMessage());
            return new ArrayList<>();
        }
    }

    public void listFilesFromAllBuckets(String query) {
        if (drives.isEmpty()) {
            Log.e(TAG, "No authenticated drives found. Please add a new bucket first.");
            return;
        }

        List<Map<String, Object>> allFiles = new ArrayList<>();
        Set<String> seenFiles = new HashSet<>();

        List<Future<Void>> futures = new ArrayList<>();
        for (Service drive : drives) {
            Future<Void> future = executor.submit(new Callable<Void>() {
                @Override
                public Void call() {
                    drive.listFiles(null, query, new Service.ListFilesCallback() {
                        @Override
                        public void onFilesListed(List<Map<String, Object>> files) {
                            synchronized (allFiles) {
                                for (Map<String, Object> file : files) {
                                    String fileName = (String) file.get("name");
                                    if (!seenFiles.contains(fileName)) {
                                        allFiles.add(file);
                                        seenFiles.add(fileName);
                                    }
                                }
                            }
                        }

                        @Override
                        public void onListFailed(String error) {
                            Log.e(TAG, "Error listing files: " + error);
                        }
                    });
                    return null;
                }
            });
            futures.add(future);
        }

        // Wait for all futures to complete
        for (Future<Void> future : futures) {
            try {
                future.get();
            } catch (InterruptedException | ExecutionException e) {
                Log.e(TAG, "Error listing files from buckets: " + e.getMessage());
            }
        }

        Collections.sort(allFiles, (a, b) -> ((String) a.get("name")).compareToIgnoreCase((String) b.get("name")));
        paginateFiles(allFiles, 30);
    }

    private void displayFiles(List<Map<String, Object>> allFiles, int startIndex, int pageSize) {
        Log.d(TAG, "\nFiles (Sorted Alphabetically):\n");
        int endIndex = Math.min(startIndex + pageSize, allFiles.size());
        for (int i = startIndex; i < endIndex; i++) {
            Map<String, Object> file = allFiles.get(i);
            String name = (String) file.get("name");
            String provider = (String) file.get("provider");
            String sizeStr = file.get("size") instanceof String && !"Unknown".equals(file.get("size"))
                    ? String.format("%.2f MB", Float.parseFloat((String) file.get("size")) / (1024 * 1024))
                    : "Unknown size";
            String path = (String) file.get("path");
            Log.d(TAG, String.format("%d. %s (%s) - %s", i + 1, name, provider, sizeStr));
            Log.d(TAG, "   View file: " + path + "\n");
        }
    }

    private void paginateFiles(List<Map<String, Object>> allFiles, int pageSize) {
        int totalFiles = allFiles.size();
        int startIndex = 0;

        while (startIndex < totalFiles) {
            displayFiles(allFiles, startIndex, pageSize);
            startIndex += pageSize;
            // In Python, there's an interactive prompt; here, we log all pages at once
            // For interactivity, you'd need a UI component in Android
        }
    }

    public static class Bucket {
        private final long freeSpace;
        private final Service drive;
        private final int index;

        public Bucket(long freeSpace, Service drive, int index) {
            this.freeSpace = freeSpace;
            this.drive = drive;
            this.index = index;
        }

        public long getFreeSpace() {
            return freeSpace;
        }

        public Service getDrive() {
            return drive;
        }

        public int getIndex() {
            return index;
        }
    }

    public void shutdown() {
        executor.shutdown();
        for (Service drive : drives) {
            if (drive instanceof GoogleDrive) {
                ((GoogleDrive) drive).shutdown();
            } else if (drive instanceof DropboxService) {
                // DropboxService shuts down in finalize, but could add explicit shutdown
            }
        }
    }
}