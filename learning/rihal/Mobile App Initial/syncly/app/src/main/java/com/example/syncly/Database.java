package com.example.syncly;

import android.util.Log;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public class Database {
    private static Database instance;
    private MongoClient client;
    private MongoDatabase database;
    private MongoCollection<Document> usersCollection;
    private MongoCollection<Document> tokensCollection;
    private MongoCollection<Document> metadataCollection;
    private MongoCollection<Document> drivesCollection;
    private boolean isInitialized = false;

    private Database() {}

    public static Database getInstance() {
        if (instance == null) {
            synchronized (Database.class) {
                if (instance == null) {
                    instance = new Database();
                }
            }
        }
        return instance;
    }

    public synchronized void initialize() {
        if (isInitialized) return;
        try {
            client = MongoClients.create("mongodb://10.0.2.2:27017/?connectTimeoutMS=30000&socketTimeoutMS=30000");
            database = client.getDatabase("Syncly");

            usersCollection = database.getCollection("users");
            tokensCollection = database.getCollection("tokens");
            metadataCollection = database.getCollection("metadata");
            drivesCollection = database.getCollection("drives");

            Document ping = new Document("ping", 1);
            Document result = database.runCommand(ping);
            Log.d("Database", "Connected to MongoDB successfully. Ping result: " + result.toJson());
            isInitialized = true;
        } catch (Exception e) {
            Log.e("Database", "Failed to connect to MongoDB: " + e.getMessage(), e);
            isInitialized = false;
            throw e;
        }
    }

    public boolean isInitialized() {
        return isInitialized;
    }

    public MongoCollection<Document> getUsersCollection() {
        if (!isInitialized) initialize();
        return usersCollection;
    }

    public MongoCollection<Document> getTokensCollection() {
        if (!isInitialized) initialize();
        return tokensCollection;
    }

    public MongoCollection<Document> getMetadataCollection() {
        if (!isInitialized) initialize();
        return metadataCollection;
    }

    public MongoCollection<Document> getDrivesCollection() {
        if (!isInitialized) initialize();
        return drivesCollection;
    }

    public void closeConnection() {
        if (client != null) {
            client.close();
            System.out.println("MongoDB connection closed.");
            isInitialized = false;
        }
    }
}