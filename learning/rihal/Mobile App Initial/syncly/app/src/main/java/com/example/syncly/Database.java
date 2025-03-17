package com.example.syncly;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.UpdateOptions;

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
            // Use 10.0.2.2 for emulator access to localhost
            client = MongoClients.create("mongodb://10.0.2.2:27017/?connectTimeoutMS=30000&socketTimeoutMS=30000");
            database = client.getDatabase("Syncly");

            usersCollection = database.getCollection("users");
            tokensCollection = database.getCollection("tokens");
            metadataCollection = database.getCollection("metadata");
            drivesCollection = database.getCollection("drives");

            Document ping = new Document("ping", 1);
            Document result = database.runCommand(ping);
            System.out.println("Connected to MongoDB successfully. Ping result: " + result.toJson());
            isInitialized = true;
        } catch (Exception e) {
            System.err.println("Failed to connect to MongoDB: " + e.getMessage());
            e.printStackTrace();
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

    public void storeGoogleDriveToken(String userId, int bucketNumber, String accessToken, String refreshToken) {
        MongoCollection<Document> tokensCollection = getTokensCollection();
        Document tokenDoc = new Document("user_id", userId)
                .append("bucket_number", bucketNumber)
                .append("type", "GoogleDrive")
                .append("access_token", accessToken)
                .append("refresh_token", refreshToken);
        tokensCollection.updateOne(
                new Document("user_id", userId).append("bucket_number", bucketNumber),
                new Document("$set", tokenDoc),
                new UpdateOptions().upsert(true)
        );
    }

    public void closeConnection() {
        if (client != null) {
            client.close();
            System.out.println("MongoDB connection closed.");
            isInitialized = false;
        }
    }
}