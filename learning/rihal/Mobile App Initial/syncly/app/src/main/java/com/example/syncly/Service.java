package com.example.syncly;

// Import necessary libraries
public abstract class Service {

    // Abstract method for authentication
    public abstract void authenticate(int bucketNumber);

    // Abstract method for listing files
    public abstract void listFiles(Integer maxResults, String query);

    // Abstract method to check storage
    public abstract void checkStorage();
}
