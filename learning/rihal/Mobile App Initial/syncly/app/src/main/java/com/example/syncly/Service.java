package com.example.syncly;
import java.util.Map;
import java.util.List;

public abstract class Service {

    public interface AuthCallback {
        void onAuthComplete(Object result);
        void onAuthFailed(String error);
    }

    public interface ListFilesCallback {
        void onFilesListed(List<Map<String, Object>> files);
        void onListFailed(String error);
    }

    public interface StorageCallback {
        void onStorageChecked(long[] storage);
        void onCheckFailed(String error);
    }

    public abstract void authenticate(int bucketNumber, String userId, AuthCallback callback);
    public abstract void listFiles(Integer maxResults, String query, ListFilesCallback callback);
    public abstract void checkStorage(StorageCallback callback);
}