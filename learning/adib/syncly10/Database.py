# --- START OF FILE Database.py ---

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import logging # Add logging
import os # For potential env var usage

logger = logging.getLogger(__name__) # Use logger

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            try:
                # Use environment variable or default
                mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
                cls._instance.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)

                # Check connection
                cls._instance.client.admin.command('ismaster')
                logger.info(f"Successfully connected to MongoDB at {mongo_uri}.")

                db_name = os.getenv("MONGODB_DB_NAME", "Syncly") # Allow overriding DB name
                cls._instance.db = cls._instance.client[db_name]
                cls._instance.users_collection = cls._instance.db['users']
                cls._instance.tokens_collection = cls._instance.db['tokens'] # For service tokens
                cls._instance.metadata_collection = cls._instance.db['metadata'] # File metadata
                cls._instance.drives_collection = cls._instance.db['drives'] # User drive config
                # --- Add the new collection attribute ---
                cls._instance.pending_links_collection = cls._instance.db['pending_links'] # For bot auth links
                # --- End Add ---

            except ConnectionFailure as e:
                logger.error(f"Failed to connect to MongoDB at {mongo_uri}: {e}")
                cls._instance.client = None
                cls._instance.db = None
                # Set all collections to None explicitly
                cls._instance.users_collection = None
                cls._instance.tokens_collection = None
                cls._instance.metadata_collection = None
                cls._instance.drives_collection = None
                cls._instance.pending_links_collection = None
                # Should probably exit or raise here in a real app
            except Exception as e: # Catch other potential errors during init
                 logger.error(f"An unexpected error occurred during Database initialization: {e}", exc_info=True)
                 cls._instance = None # Ensure instance remains None on other errors
                 raise # Re-raise the exception


        return cls._instance

    @classmethod
    def get_instance(cls):
        """Returns the singleton instance of Database, creating if necessary."""
        if cls._instance is None:
             try:
                 # This triggers __new__ if instance is None
                 Database()
             except Exception as e:
                 logger.critical(f"Failed to create Database instance in get_instance: {e}")
                 return None # Return None if creation failed

        # Check if the instance was created but connection failed
        if cls._instance and (cls._instance.client is None or cls._instance.db is None):
             logger.error("Database instance exists but is not connected/initialized properly.")
             return None

        return cls._instance

    def close_connection(self):
        """Closes the MongoDB connection."""
        if hasattr(self, 'client') and self.client:
            try:
                self.client.close()
                logger.info("MongoDB connection closed.")
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {e}")
        # Optionally reset the singleton instance?
        # Database._instance = None

# --- END OF FILE Database.py ---