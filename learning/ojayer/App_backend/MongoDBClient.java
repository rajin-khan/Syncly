package org.example;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public class MongoDBClient {
    private static MongoDBClient instance;
    private MongoClient client;
    private MongoDatabase db;
    public MongoCollection<Document> usersCollection;
    public MongoCollection<Document> tokensCollection;
    public MongoCollection<Document> drivesCollection;
    public MongoCollection<Document> metadataCollection;

    private MongoDBClient() {
        client = MongoClients.create("mongodb://localhost:27017");
        db = client.getDatabase("Syncly");
        usersCollection = db.getCollection("users");
        tokensCollection = db.getCollection("tokens");
        drivesCollection = db.getCollection("drives");
        metadataCollection = db.getCollection("metadata");
    }

    public static MongoDBClient getInstance() {
        if (instance == null) {
            instance = new MongoDBClient();
        }
        return instance;
    }

    public void close() {
        if (client != null) {
            client.close();
        }
    }
}