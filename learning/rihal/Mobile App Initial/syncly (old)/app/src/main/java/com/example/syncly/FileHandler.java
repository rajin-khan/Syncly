package com.example.syncly;

public abstract class FileHandler {

    // Abstract method for uploading the full file
    public abstract void uploadFile(String filePath, String fileName, String mimeType);

    // Abstract method to update metadata
    public abstract void updateMetadata(String metadata);

    // Abstract method to search for a file
    public abstract void searchFile();

    //Abstract method to download a file
    public abstract void downloadFile(String fileName, String savePath);
}
