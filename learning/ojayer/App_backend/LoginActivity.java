package com.example.syncly;

import android.content.Intent;
import android.os.AsyncTask;
import android.os.Bundle;
import android.text.method.HideReturnsTransformationMethod;
import android.text.method.PasswordTransformationMethod;
import android.util.Base64;
import android.util.Log;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public class LoginActivity extends AppCompatActivity {

    private EditText usernameInput, passwordInput;
    private ImageView togglePasswordVisibility;
    private Button loginButton;
    private boolean isPasswordVisible = false;
    private static final String TAG = "MongoDB";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login);

        usernameInput = findViewById(R.id.username_input);
        passwordInput = findViewById(R.id.password_input);
        togglePasswordVisibility = findViewById(R.id.toggle_password_visibility);
        loginButton = findViewById(R.id.btn_login);

        // Toggle Password Visibility
        togglePasswordVisibility.setOnClickListener(v -> {
            if (isPasswordVisible) {
                passwordInput.setTransformationMethod(PasswordTransformationMethod.getInstance());
                togglePasswordVisibility.setImageResource(R.drawable.ic_visibility_off);
            } else {
                passwordInput.setTransformationMethod(HideReturnsTransformationMethod.getInstance());
                togglePasswordVisibility.setImageResource(R.drawable.ic_visibility);
            }
            isPasswordVisible = !isPasswordVisible;
            passwordInput.setSelection(passwordInput.getText().length());
        });

        // Handle login button click
        loginButton.setOnClickListener(v -> {
            String username = usernameInput.getText().toString().trim();
            String password = passwordInput.getText().toString().trim();

            if (username.isEmpty() || password.isEmpty()) {
                Toast.makeText(LoginActivity.this, "Please enter both username and password", Toast.LENGTH_SHORT).show();
            } else {
                new LoginUserTask().execute(username, password);
            }
        });
    }

    // AsyncTask to run login verification in the background
    private class LoginUserTask extends AsyncTask<String, Void, Boolean> {
        private String username;
        private String errorMessage = "";

        @Override
        protected Boolean doInBackground(String... params) {
            username = params[0];
            String password = params[1];

            try {
                MongoCollection<Document> usersCollection = Database.getInstance().getUsersCollection();

                // Find the user in the database
                Document user = usersCollection.find(new Document("username", username)).first();
                if (user == null) {
                    errorMessage = "User not found. Please register first.";
                    return false;
                }

                // Hash the input password
                String hashedPassword = hashPassword(password);
                if (hashedPassword == null) {
                    errorMessage = "Error hashing password";
                    return false;
                }

                // Verify password
                if (!user.getString("password").equals(hashedPassword)) {
                    errorMessage = "Incorrect password. Please try again.";
                    return false;
                }

                Log.d(TAG, "User '" + username + "' logged in successfully.");
                return true;

            } catch (Exception e) {
                Log.e(TAG, "Error during login: " + e.getMessage());
                errorMessage = "Login failed: " + e.getMessage();
                return false;
            }
        }

        @Override
        protected void onPostExecute(Boolean success) {
            if (success) {
                Toast.makeText(LoginActivity.this, "Login successful", Toast.LENGTH_SHORT).show();
                Intent intent = new Intent(LoginActivity.this, HomeActivity.class);
                intent.putExtra("userId", username); // Pass the userId to HomeActivity
                startActivity(intent);
                finish();
            } else {
                Toast.makeText(LoginActivity.this, errorMessage, Toast.LENGTH_SHORT).show();
            }
        }
    }

    private String hashPassword(String password) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(password.getBytes());
            return Base64.encodeToString(hash, Base64.NO_WRAP);
        } catch (NoSuchAlgorithmException e) {
            Log.e(TAG, "Password hashing error: " + e.getMessage());
            return null;
        }
    }
}