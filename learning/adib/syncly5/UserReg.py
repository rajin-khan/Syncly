import hashlib
from Database import Database
from AuthManager import AuthManager

class UserReg:
    def __init__(self):
        self.db = Database().get_instance()
        self.auth_manager = AuthManager()

    def register_user(self, username, password, email):
        """Register a new user with OTP verification."""
        return self.auth_manager.register_user(username, password, email)

    def login_user(self, username, password):
        """Log in an existing user."""
        return self.auth_manager.login_user(username, password)