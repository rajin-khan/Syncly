import os
import hmac
import hashlib
import secrets
import time
import base64
import qrcode
import uuid
from datetime import datetime, timedelta
import pyotp
import jwt
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from Database import Database

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secure secret key for sessions
app.config['JWT_SECRET_KEY'] = os.urandom(32)
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)

class AuthSystem:
    def __init__(self):
        self.db = Database().get_instance()
        self.tokens_collection = self.db.db['auth_tokens']
        self.otp_collection = self.db.db['otp_secrets']
        self.session_collection = self.db.db['sessions']
        
        # Ensure indexes for better performance
        self.db.users_collection.create_index('username', unique=True)
        self.db.users_collection.create_index('email', unique=True)
        self.tokens_collection.create_index('refresh_token', unique=True)
        self.tokens_collection.create_index('expiry', expireAfterSeconds=0)
        self.otp_collection.create_index('user_id')
        self.session_collection.create_index('expiry', expireAfterSeconds=0)

    def hash_password(self, password):
        """Generate a secure password hash using Werkzeug's implementation."""
        return generate_password_hash(password, method='pbkdf2:sha256:100000')
    
    def verify_password(self, stored_hash, provided_password):
        """Verify a password against its stored hash."""
        return check_password_hash(stored_hash, provided_password)
    
    def register_user(self, username, email, password):
        """Register a new user with enhanced security."""
        # Check if username or email already exists
        if self.db.users_collection.find_one({"$or": [{"username": username}, {"email": email}]}):
            return None, "Username or email already exists"
        
        # Hash the password securely
        password_hash = self.hash_password(password)
        
        # Create OTP secret for 2FA
        otp_secret = pyotp.random_base32()
        
        # Insert user data
        user_id = self.db.users_collection.insert_one({
            "username": username,
            "email": email,
            "password": password_hash,
            "created_at": datetime.utcnow(),
            "drives": [],
            "mfa_enabled": False,
            "account_locked": False,
            "failed_login_attempts": 0,
            "last_login": None
        }).inserted_id
        
        # Store OTP secret separately
        self.otp_collection.insert_one({
            "user_id": user_id,
            "otp_secret": otp_secret,
            "verified": False
        })
        
        return user_id, "User registered successfully"
    
    def generate_otp_setup(self, user_id, username):
        """Generate OTP setup information for 2FA."""
        otp_data = self.otp_collection.find_one({"user_id": user_id})
        if not otp_data:
            return None
        
        otp_secret = otp_data["otp_secret"]
        totp = pyotp.TOTP(otp_secret)
        
        # Generate QR code for OTP app
        otp_auth_url = totp.provisioning_uri(username, issuer_name="Syncly")
        qr = qrcode.make(otp_auth_url)
        qr_path = f"static/qr_codes/{user_id}.png"
        os.makedirs(os.path.dirname(qr_path), exist_ok=True)
        qr.save(qr_path)
        
        return {
            "secret": otp_secret,
            "qr_code_path": qr_path,
            "auth_url": otp_auth_url
        }
    
    def verify_otp(self, user_id, otp_code):
        """Verify OTP code for 2FA."""
        otp_data = self.otp_collection.find_one({"user_id": user_id})
        if not otp_data:
            return False
        
        totp = pyotp.TOTP(otp_data["otp_secret"])
        is_valid = totp.verify(otp_code)
        
        if is_valid and not otp_data["verified"]:
            # Mark OTP as verified after first successful verification
            self.otp_collection.update_one(
                {"user_id": user_id},
                {"$set": {"verified": True}}
            )
            self.db.users_collection.update_one(
                {"_id": user_id},
                {"$set": {"mfa_enabled": True}}
            )
        
        return is_valid
    
    def login_user(self, username, password):
        """Login a user with enhanced security."""
        user = self.db.users_collection.find_one({"username": username})
        if not user:
            return None, "User not found"
        
        # Check if account is locked
        if user.get("account_locked", False):
            lock_time = user.get("lock_time", datetime.utcnow() - timedelta(minutes=30))
            if datetime.utcnow() - lock_time < timedelta(minutes=30):
                return None, "Account is temporarily locked. Please try again later."
            else:
                # Reset lock if 30 minutes have passed
                self.db.users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"account_locked": False, "failed_login_attempts": 0}}
                )
        
        # Verify password
        if not self.verify_password(user["password"], password):
            # Increment failed login attempts
            failed_attempts = user.get("failed_login_attempts", 0) + 1
            lock_account = failed_attempts >= 5
            
            self.db.users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {
                    "failed_login_attempts": failed_attempts,
                    "account_locked": lock_account,
                    "lock_time": datetime.utcnow() if lock_account else None
                }}
            )
            
            if lock_account:
                return None, "Too many failed attempts. Account is temporarily locked."
            return None, "Invalid password"
        
        # Reset failed login attempts
        self.db.users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"failed_login_attempts": 0, "last_login": datetime.utcnow()}}
        )
        
        # Check if MFA is enabled
        if user.get("mfa_enabled", False):
            return user["_id"], "2FA_REQUIRED"
        
        # Generate JWT tokens
        access_token, refresh_token = self.generate_tokens(user["_id"])
        
        return user["_id"], {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "mfa_enabled": user.get("mfa_enabled", False)
        }
    
    def generate_tokens(self, user_id):
        """Generate JWT access and refresh tokens."""
        # Generate access token
        access_token_payload = {
            "user_id": str(user_id),
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "token_type": "access"
        }
        
        # Generate refresh token with longer expiry
        refresh_token_payload = {
            "user_id": str(user_id),
            "exp": datetime.utcnow() + timedelta(days=30),
            "iat": datetime.utcnow(),
            "token_type": "refresh",
            "jti": str(uuid.uuid4())  # Unique identifier for refresh token
        }
        
        access_token = jwt.encode(access_token_payload, app.config['JWT_SECRET_KEY'], algorithm="HS256")
        refresh_token = jwt.encode(refresh_token_payload, app.config['JWT_SECRET_KEY'], algorithm="HS256")
        
        # Store refresh token in database for revocation capability
        self.tokens_collection.insert_one({
            "user_id": user_id,
            "refresh_token": refresh_token,
            "expiry": refresh_token_payload["exp"],
            "revoked": False
        })
        
        return access_token, refresh_token
    
    def refresh_access_token(self, refresh_token):
        """Get a new access token using a refresh token."""
        try:
            # Verify the refresh token
            payload = jwt.decode(refresh_token, app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            
            # Check if it's actually a refresh token
            if payload.get("token_type") != "refresh":
                return None, "Invalid token type"
            
            user_id = payload.get("user_id")
            jti = payload.get("jti")
            
            # Check if token has been revoked
            token_data = self.tokens_collection.find_one({
                "refresh_token": refresh_token,
                "revoked": False
            })
            
            if not token_data:
                return None, "Token has been revoked"
            
            # Generate new access token
            access_token_payload = {
                "user_id": user_id,
                "exp": datetime.utcnow() + timedelta(hours=1),
                "iat": datetime.utcnow(),
                "token_type": "access"
            }
            
            new_access_token = jwt.encode(access_token_payload, app.config['JWT_SECRET_KEY'], algorithm="HS256")
            
            return new_access_token, "Token refreshed successfully"
            
        except jwt.ExpiredSignatureError:
            return None, "Token has expired"
        except jwt.InvalidTokenError:
            return None, "Invalid token"
    
    def revoke_token(self, refresh_token):
        """Revoke a refresh token."""
        self.tokens_collection.update_one(
            {"refresh_token": refresh_token},
            {"$set": {"revoked": True}}
        )
    
    def create_session(self, user_id):
        """Create a session for a user."""
        session_id = str(uuid.uuid4())
        expiry = datetime.utcnow() + timedelta(hours=24)
        
        self.session_collection.insert_one({
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "expiry": expiry,
            "active": True
        })
        
        return session_id
    
    def validate_session(self, session_id):
        """Validate a session."""
        session_data = self.session_collection.find_one({
            "session_id": session_id,
            "active": True,
            "expiry": {"$gt": datetime.utcnow()}
        })
        
        return session_data is not None
    
    def end_session(self, session_id):
        """End a user session."""
        self.session_collection.update_one(
            {"session_id": session_id},
            {"$set": {"active": False}}
        )
    
    def verify_access_token(self, token):
        """Verify an access token and return the user ID."""
        try:
            payload = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            
            # Check if it's an access token
            if payload.get("token_type") != "access":
                return None
            
            return payload.get("user_id")
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

# Initialize the authentication system
auth_system = AuthSystem()

# Flask routes for authentication
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        user_id, message = auth_system.register_user(username, email, password)
        
        if user_id:
            # Generate OTP setup for 2FA
            otp_setup = auth_system.generate_otp_setup(user_id, username)
            session['user_id'] = str(user_id)
            return redirect(url_for('setup_2fa'))
        else:
            return render_template('register.html', error=message)
    
    return render_template('register.html')

@app.route('/setup-2fa', methods=['GET', 'POST'])
def setup_2fa():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = auth_system.db.users_collection.find_one({"_id": user_id})
    
    if request.method == 'POST':
        otp_code = request.form.get('otp_code')
        
        if auth_system.verify_otp(user_id, otp_code):
            return redirect(url_for('login'))
        else:
            return render_template('setup_2fa.html', error="Invalid OTP code")
    
    otp_setup = auth_system.generate_otp_setup(user_id, user['username'])
    
    return render_template('setup_2fa.html', 
                           secret=otp_setup['secret'],
                           qr_code=otp_setup['qr_code_path'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_id, result = auth_system.login_user(username, password)
        
        if not user_id:
            return render_template('login.html', error=result)
        
        if result == "2FA_REQUIRED":
            session['user_id'] = str(user_id)
            session['awaiting_2fa'] = True
            return redirect(url_for('verify_2fa'))
        
        session['user_id'] = str(user_id)
        session['access_token'] = result['access_token']
        session['refresh_token'] = result['refresh_token']
        
        return redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    if 'user_id' not in session or not session.get('awaiting_2fa'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        otp_code = request.form.get('otp_code')
        user_id = session['user_id']
        
        if auth_system.verify_otp(user_id, otp_code):
            # Generate JWT tokens after successful 2FA
            access_token, refresh_token = auth_system.generate_tokens(user_id)
            
            # Clear awaiting_2fa flag
            session.pop('awaiting_2fa', None)
            
            # Store tokens in session
            session['access_token'] = access_token
            session['refresh_token'] = refresh_token
            
            return redirect(url_for('dashboard'))
        else:
            return render_template('verify_2fa.html', error="Invalid OTP code")
    
    return render_template('verify_2fa.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or 'access_token' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = auth_system.db.users_collection.find_one({"_id": user_id})
    
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    return render_template('dashboard.html', username=user['username'])

@app.route('/logout')
def logout():
    if 'refresh_token' in session:
        auth_system.revoke_token(session['refresh_token'])
    
    session.clear()
    return redirect(url_for('login'))

@app.route('/refresh-token')
def refresh_token():
    if 'refresh_token' not in session:
        return redirect(url_for('login'))
    
    refresh_token = session['refresh_token']
    new_access_token, message = auth_system.refresh_access_token(refresh_token)
    
    if not new_access_token:
        session.clear()
        return redirect(url_for('login'))
    
    session['access_token'] = new_access_token
    return redirect(url_for('dashboard'))

# API routes for JWT authentication
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    if not username or not email or not password:
        return jsonify({"error": "Missing required fields"}), 400
    
    user_id, message = auth_system.register_user(username, email, password)
    
    if not user_id:
        return jsonify({"error": message}), 400
    
    otp_setup = auth_system.generate_otp_setup(user_id, username)
    
    return jsonify({
        "message": "User registered successfully",
        "user_id": str(user_id),
        "otp_setup": {
            "secret": otp_setup["secret"],
            "qr_code_url": otp_setup["qr_code_path"],
            "auth_url": otp_setup["auth_url"]
        }
    }), 201

@app.route('/api/verify-otp', methods=['POST'])
def api_verify_otp():
    data = request.get_json()
    user_id = data.get('user_id')
    otp_code = data.get('otp_code')
    
    if not user_id or not otp_code:
        return jsonify({"error": "Missing required fields"}), 400
    
    if auth_system.verify_otp(user_id, otp_code):
        # Enable 2FA for the user if it's the first verification
        user = auth_system.db.users_collection.find_one({"_id": user_id})
        if not user.get("mfa_enabled", False):
            auth_system.db.users_collection.update_one(
                {"_id": user_id},
                {"$set": {"mfa_enabled": True}}
            )
        
        return jsonify({"message": "OTP verified successfully"}), 200
    else:
        return jsonify({"error": "Invalid OTP code"}), 400

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Missing required fields"}), 400
    
    user_id, result = auth_system.login_user(username, password)
    
    if not user_id:
        return jsonify({"error": result}), 401
    
    if result == "2FA_REQUIRED":
        return jsonify({
            "message": "2FA verification required",
            "user_id": str(user_id),
            "require_2fa": True
        }), 200
    
    return jsonify({
        "message": "Login successful",
        "user_id": str(user_id),
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "mfa_enabled": result["mfa_enabled"]
    }), 200

@app.route('/api/login-2fa', methods=['POST'])
def api_login_2fa():
    data = request.get_json()
    user_id = data.get('user_id')
    otp_code = data.get('otp_code')
    
    if not user_id or not otp_code:
        return jsonify({"error": "Missing required fields"}), 400
    
    if auth_system.verify_otp(user_id, otp_code):
        access_token, refresh_token = auth_system.generate_tokens(user_id)
        
        return jsonify({
            "message": "Login successful",
            "user_id": str(user_id),
            "access_token": access_token,
            "refresh_token": refresh_token
        }), 200
    else:
        return jsonify({"error": "Invalid OTP code"}), 401

@app.route('/api/refresh-token', methods=['POST'])
def api_refresh_token():
    data = request.get_json()
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({"error": "Missing refresh token"}), 400
    
    new_access_token, message = auth_system.refresh_access_token(refresh_token)
    
    if not new_access_token:
        return jsonify({"error": message}), 401
    
    return jsonify({
        "message": "Token refreshed successfully",
        "access_token": new_access_token
    }), 200

@app.route('/api/logout', methods=['POST'])
def api_logout():
    data = request.get_json()
    refresh_token = data.get('refresh_token')
    
    if refresh_token:
        auth_system.revoke_token(refresh_token)
    
    return jsonify({"message": "Logged out successfully"}), 200

# JWT token verification decorator for API routes
def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        token = auth_header.split(' ')[1]
        user_id = auth_system.verify_access_token(token)
        
        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401
        
        return f(user_id, *args, **kwargs)
    
    return decorated

@app.route('/api/protected', methods=['GET'])
@jwt_required
def api_protected(user_id):
    user = auth_system.db.users_collection.find_one({"_id": user_id})
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({
        "message": "Access granted to protected resource",
        "user_id": str(user_id),
        "username": user["username"]
    }), 200

if __name__ == '__main__':
    app.run(debug=True)