from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            try:
                # Initialize MongoDB client and collections
                cls._instance.client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
                cls._instance.db = cls._instance.client['Syncly']
                cls._instance.users_collection = cls._instance.db['users']
                cls._instance.tokens_collection = cls._instance.db['tokens']
                cls._instance.metadata_collection = cls._instance.db['metadata']
                cls._instance.drives_collection = cls._instance.db['drives']

                # Test the connection
                cls._instance.client.admin.command('ping')
                print("Connected to MongoDB successfully.")
            except ConnectionFailure:
                print("Failed to connect to MongoDB")
                cls._instance.client = None  # Prevent usage of a broken connection
        return cls._instance

    @classmethod
    def get_instance(cls):
        """Returns the singleton instance of Database"""
        if cls._instance is None:
            cls._instance = Database()
        return cls._instance

    def close_connection(self):
        """Closes the MongoDB connection"""
        if self.client:
            self.client.close()
            print("MongoDB connection closed.")