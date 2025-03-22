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
import org.bson.types.ObjectId;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public class LoginActivity extends AppCompatActivity {

    private EditText usernameInput, passwordInput;
    private ImageView togglePasswordVisibility;
    private Button loginButton, registerButton;
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
        registerButton = findViewById(R.id.btn_register);

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

        loginButton.setOnClickListener(v -> {
            String username = usernameInput.getText().toString().trim();
            String password = passwordInput.getText().toString().trim();

            if (username.isEmpty() || password.isEmpty()) {
                Toast.makeText(LoginActivity.this, "Please enter both username and password", Toast.LENGTH_SHORT).show();
            } else {
                new LoginUserTask().execute(username, password);
            }
        });

        registerButton.setOnClickListener(v -> {
            Intent intent = new Intent(LoginActivity.this, RegisterActivity.class);
            startActivity(intent);
        });
    }

    private class LoginUserTask extends AsyncTask<String, Void, String> { // Return ObjectId as String
        private String username;
        private String errorMessage = "";

        @Override
        protected String doInBackground(String... params) {
            username = params[0];
            String password = params[1];

            try {
                MongoCollection<Document> usersCollection = Database.getInstance().getUsersCollection();

                Document user = usersCollection.find(new Document("username", username)).first();
                if (user == null) {
                    errorMessage = "User not found. Please register first.";
                    return null;
                }

                String hashedPassword = hashPassword(password);
                if (hashedPassword == null) {
                    errorMessage = "Error hashing password";
                    return null;
                }

                if (!user.getString("password").equals(hashedPassword)) {
                    errorMessage = "Incorrect password. Please try again.";
                    return null;
                }

                Log.d(TAG, "User '" + username + "' logged in successfully.");
                return user.getObjectId("_id").toHexString(); // Return ObjectId

            } catch (Exception e) {
                Log.e(TAG, "Error during login: " + e.getMessage());
                errorMessage = "Login failed: " + e.getMessage();
                return null;
            }
        }

        @Override
        protected void onPostExecute(String objectId) {
            if (objectId != null) {
                Toast.makeText(LoginActivity.this, "Login successful", Toast.LENGTH_SHORT).show();
                Intent intent = new Intent(LoginActivity.this, HomeActivity.class);
                intent.putExtra("userId", objectId); // Pass ObjectId as userId
                intent.putExtra("username", username); // Pass username for intent extras
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