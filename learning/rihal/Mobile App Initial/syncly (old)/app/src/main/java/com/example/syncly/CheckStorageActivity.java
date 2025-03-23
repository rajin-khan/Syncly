package com.example.syncly;

import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CheckStorageActivity extends AppCompatActivity {
    private static final String TAG = "CheckStorageActivity";
    private ProgressBar pbCombinedStorage;
    private TextView tvStorageBreakdown;
    private String userId;
    private DriveManager driveManager;
    private Map<String, Long> totalFreeSpace = new HashMap<>();
    private Map<String, Long> totalSpace = new HashMap<>();
    private TextView tvStorageSummary;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_check_storage);

        pbCombinedStorage = findViewById(R.id.pb_combined_storage);
        tvStorageBreakdown = findViewById(R.id.tv_storage_breakdown);
        tvStorageSummary = findViewById(R.id.tv_storage_summary);

        userId = getIntent().getStringExtra("userId");
        if (userId == null) {
            Log.e(TAG, "userId is null, cannot proceed");
            Toast.makeText(this, "Error: User ID not found", Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        Log.d(TAG, "Retrieved userId from intent: " + userId);

        String tokenDir = getFilesDir().getAbsolutePath();
        driveManager = DriveManager.getInstance(userId, tokenDir, this);

        new CheckStorageTask().execute();
    }

    private class CheckStorageTask extends AsyncTask<Void, Void, Boolean> {
        private Map<String, Map<Integer, Long>> bucketFreeSpaceInfo = new HashMap<>();
        private Map<String, Map<Integer, Long>> bucketTotalSpaceInfo = new HashMap<>();
        private long combinedTotalSpace = 0L;
        private long combinedFreeSpace = 0L;

        @Override
        protected Boolean doInBackground(Void... voids) {
            try {
                List<DriveManager.Bucket> buckets = driveManager.getSortedBuckets();
                bucketFreeSpaceInfo.put("GoogleDrive", new HashMap<>());
                bucketFreeSpaceInfo.put("Dropbox", new HashMap<>());
                bucketTotalSpaceInfo.put("GoogleDrive", new HashMap<>());
                bucketTotalSpaceInfo.put("Dropbox", new HashMap<>());
                totalFreeSpace.put("GoogleDrive", 0L);
                totalFreeSpace.put("Dropbox", 0L);
                totalSpace.put("GoogleDrive", 0L);
                totalSpace.put("Dropbox", 0L);

                for (DriveManager.Bucket bucket : buckets) {
                    Service service = bucket.getDrive();
                    long freeSpace = bucket.getFreeSpace();
                    long totalBucketSpace = bucket.getTotalSpace();

                    // Skip buckets where free space or total space couldn't be retrieved
                    if (freeSpace < 0 || totalBucketSpace < 0) {
                        Log.w(TAG, "Skipping bucket " + bucket.getIndex() + ": Invalid space data (free=" + freeSpace + ", total=" + totalBucketSpace + ")");
                        continue;
                    }

                    if (service instanceof GoogleDrive) {
                        bucketFreeSpaceInfo.get("GoogleDrive").put(bucket.getIndex(), freeSpace);
                        bucketTotalSpaceInfo.get("GoogleDrive").put(bucket.getIndex(), totalBucketSpace);
                        totalFreeSpace.put("GoogleDrive", totalFreeSpace.get("GoogleDrive") + freeSpace);
                        totalSpace.put("GoogleDrive", totalSpace.get("GoogleDrive") + totalBucketSpace);
                    } else if (service instanceof DropboxService) {
                        bucketFreeSpaceInfo.get("Dropbox").put(bucket.getIndex(), freeSpace);
                        bucketTotalSpaceInfo.get("Dropbox").put(bucket.getIndex(), totalBucketSpace);
                        totalFreeSpace.put("Dropbox", totalFreeSpace.get("Dropbox") + freeSpace);
                        totalSpace.put("Dropbox", totalSpace.get("Dropbox") + totalBucketSpace);
                    }
                    combinedTotalSpace += totalBucketSpace;
                    combinedFreeSpace += freeSpace;
                }
                return !bucketFreeSpaceInfo.get("GoogleDrive").isEmpty() || !bucketFreeSpaceInfo.get("Dropbox").isEmpty();
            } catch (Exception e) {
                Log.e(TAG, "Failed to check storage: " + e.getMessage(), e);
                return false;
            }
        }

        @Override
        protected void onPostExecute(Boolean success) {
            if (!success) {
                Toast.makeText(CheckStorageActivity.this, "No storage buckets available.", Toast.LENGTH_LONG).show();
                tvStorageBreakdown.setText("No buckets found.");
                pbCombinedStorage.setProgress(0);
                return;
            }

            if (combinedTotalSpace > 0) {
                long usedSpace = combinedTotalSpace - combinedFreeSpace;
                int progress = (int) ((usedSpace * 100L) / combinedTotalSpace);
                pbCombinedStorage.setProgress(progress);
                long totalSpaceMB = combinedTotalSpace / (1024 * 1024);
                long usedSpaceMB = usedSpace / (1024 * 1024);
                tvStorageSummary.setText(String.format("%d MB / %d MB used", usedSpaceMB, totalSpaceMB));
                Log.d(TAG, "Combined Total Space: " + combinedTotalSpace + " bytes, Free Space: " + combinedFreeSpace + " bytes, Progress: " + progress + "%");
            } else {
                tvStorageSummary.setText("0 MB / 0 MB used");
                pbCombinedStorage.setProgress(0);
            }

            // Update TextView with breakdown (mimicking the screenshot style)
            StringBuilder breakdown = new StringBuilder("Available Bucket Space:\n\n");
            boolean hasBuckets = false;

            for (String driveType : bucketFreeSpaceInfo.keySet()) {
                Map<Integer, Long> freeSpaceBuckets = bucketFreeSpaceInfo.get(driveType);
                for (Integer bucketIndex : freeSpaceBuckets.keySet()) {
                    long freeSpaceMB = freeSpaceBuckets.get(bucketIndex) / (1024 * 1024);
                    breakdown.append(String.format("%s bucket %d: %d MB free\n", driveType, bucketIndex, freeSpaceMB));
                    hasBuckets = true;
                }
            }

            if (!hasBuckets) {
                breakdown.append("No buckets with valid space data found.");
            }

            tvStorageBreakdown.setText(breakdown.toString());
        }
    }
}