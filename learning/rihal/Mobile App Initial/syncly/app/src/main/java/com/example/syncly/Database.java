package com.example.syncly;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import android.util.Log;

public class Database {

    private static Database instance;
    private MongoClient client;
    private MongoDatabase database;
    private MongoCollection<Document> usersCollection;
    private MongoCollection<Document> tokensCollection;
    private MongoCollection<Document> metadataCollection;
    private MongoCollection<Document> drivesCollection;
    private static final String TAG = "MongoDB";

    private Database() {
        try {
            // Use MongoClients instead of MongoClient
            client = MongoClients.create("mongodb://192.168.0.105:27017");   // Update with your connection string
            database = client.getDatabase("Syncly"); // Correct way to get the database

            // Initialize collections
            usersCollection = database.getCollection("users");
            tokensCollection = database.getCollection("tokens");
            metadataCollection = database.getCollection("metadata");
            drivesCollection = database.getCollection("drives");

            // Test the connection
            Document ping = new Document("ping", 1);
            database.runCommand(ping);
            Log.d(TAG, "✅ Connected to MongoDB successfully.");
        } catch (Exception e) {
            Log.e(TAG, "❌ Failed to connect to MongoDB: " + e.getMessage());
        }
    }

    public static Database getInstance() {
        if (instance == null) {
            instance = new Database();
        }
        return instance;
    }

    // Getter for database
    public MongoDatabase getDatabase() {
        return database;
    }
    // Getter methods for collections
    public MongoCollection<Document> getUsersCollection() {
        return usersCollection;
    }

    public MongoCollection<Document> getTokensCollection() {
        return tokensCollection;
    }

    public MongoCollection<Document> getMetadataCollection() {
        return metadataCollection;
    }

    public MongoCollection<Document> getDrivesCollection() {
        return drivesCollection;
    }

    // Close the MongoDB connection
    public void closeConnection() {
        if (client != null) {
            client.close();
            Log.e(TAG, "MongoDB connection closed.");
        }
    }
}
