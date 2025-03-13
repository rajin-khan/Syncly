import hashlib
from Database import Database

class UserReg:
    def __init__(self):
        # Use the singleton Database instance
        self.db = Database().get_instance()
        self.users_collection = self.db.users_collection

    def register_user(self, username, password):
        """
        Register a new user.
        """
        if self.users_collection.find_one({"username": username}):
            print("Username already exists. Please choose a different username.")
            return None

        # Hash the password for security
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        # Insert the new user into the database
        user_id = self.users_collection.insert_one({
            "username": username,
            "password": hashed_password,
            "drives": []  # Initialize an empty list for drives
        }).inserted_id

        print(f"User '{username}' registered successfully with ID: {user_id}")
        return user_id

    def login_user(self, username, password):
        """
        Log in an existing user.
        """
        user = self.users_collection.find_one({"username": username})
        if not user:
            print("User not found. Please register first.")
            return None

        # Verify the password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        if user["password"] != hashed_password:
            print("Incorrect password. Please try again.")
            return None

        print(f"User '{username}' logged in successfully.")
        return user["_id"]