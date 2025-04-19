# --- START OF FILE Database.py ---

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import logging # Add logging

logger = logging.getLogger(__name__) # Use logger

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            try:
                # Initialize MongoDB client and collections
                # Consider using an environment variable for the URI for flexibility
                mongo_uri = "mongodb://localhost:27017/"
                cls._instance.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)

                # The ismaster command is cheap and does not require auth.
                cls._instance.client.admin.command('ismaster')
                logger.info(f"Successfully connected to MongoDB at {mongo_uri}.")

                cls._instance.db = cls._instance.client['Syncly']
                cls._instance.users_collection = cls._instance.db['users']
                cls._instance.tokens_collection = cls._instance.db['tokens']
                cls._instance.metadata_collection = cls._instance.db['metadata']
                cls._instance.drives_collection = cls._instance.db['drives']
                # --- Add the new collection attribute ---
                cls._instance.pending_links_collection = cls._instance.db['pending_links']
                # --- End Add ---

            except ConnectionFailure as e:
                logger.error(f"Failed to connect to MongoDB at {mongo_uri}: {e}")
                cls._instance.client = None # Prevent usage of a broken connection
                cls._instance.db = None
                # Set other collections to None as well if connection fails
                cls._instance.users_collection = None
                cls._instance.tokens_collection = None
                cls._instance.metadata_collection = None
                cls._instance.drives_collection = None
                cls._instance.pending_links_collection = None
            except Exception as e: # Catch other potential errors during init
                 logger.error(f"An unexpected error occurred during Database initialization: {e}", exc_info=True)
                 cls._instance = None # Ensure instance remains None on other errors
                 raise # Re-raise the exception to prevent app from starting with broken DB access


        return cls._instance

    @classmethod
    def get_instance(cls):
        """Returns the singleton instance of Database, creating if necessary."""
        # This check ensures that if the initial __new__ failed, we retry/re-raise
        if cls._instance is None:
             try:
                 cls._instance = cls() # Attempt to create instance via __new__
             except Exception as e:
                 # If creation fails again, log and return None or re-raise
                 logger.critical(f"Failed to create Database instance in get_instance: {e}")
                 return None # Or re-raise depending on desired app behavior
        # Additional check in case __new__ returned None previously but instance variable wasn't reset
        if cls._instance and (cls._instance.client is None or cls._instance.db is None):
             logger.error("Database instance exists but is not connected.")
             # Optionally try to reconnect or just return None
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
        # Prevent reuse after close?
        # Database._instance = None


# --- END OF FILE Database.py ---