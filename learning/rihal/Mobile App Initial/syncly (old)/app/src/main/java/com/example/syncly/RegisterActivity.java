package com.example.syncly;

import android.content.Intent;
import android.os.AsyncTask;
import android.os.Bundle;
import android.text.method.HideReturnsTransformationMethod;
import android.text.method.PasswordTransformationMethod;
import android.util.Log;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.BasicBSONList;
import org.bson.types.ObjectId;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public class RegisterActivity extends AppCompatActivity {

    private EditText usernameInput, passwordInput;
    private Button registerButton;
    private ImageView togglePasswordVisibility;
    private boolean isPasswordVisible = false;
    private static final String TAG = "MongoDB";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_register);

        usernameInput = findViewById(R.id.username_input_register);
        passwordInput = findViewById(R.id.password_input);
        registerButton = findViewById(R.id.btn_register);
        togglePasswordVisibility = findViewById(R.id.toggle_password_visibility);

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

        registerButton.setOnClickListener(v -> {
            String username = usernameInput.getText().toString().trim();
            String password = passwordInput.getText().toString().trim();
            if (username.isEmpty() || password.isEmpty()) {
                Toast.makeText(RegisterActivity.this, "Please fill in all fields", Toast.LENGTH_SHORT).show();
            } else {
                new RegisterUserTask().execute(username, password);
            }
        });
    }

    private class RegisterUserTask extends AsyncTask<String, Void, String> { // Return ObjectId as String
        private String username;
        private String errorMessage = "";

        @Override
        protected String doInBackground(String... params) {
            username = params[0];
            String password = params[1];

            try {
                MongoCollection<Document> usersCollection = Database.getInstance().getUsersCollection();

                Document existingUser = usersCollection.find(new Document("username", username)).first();
                if (existingUser != null) {
                    errorMessage = "Username already taken";
                    return null;
                }

                String hashedPassword = hashPassword(password);
                if (hashedPassword == null) {
                    errorMessage = "Error hashing password";
                    return null;
                }

                Document newUser = new Document("username", username)
                        .append("password", hashedPassword)
                        .append("drives", new BasicBSONList());
                usersCollection.insertOne(newUser);
                return newUser.getObjectId("_id").toHexString(); // Return the generated ObjectId

            } catch (Exception e) {
                Log.e(TAG, "Error during registration: " + e.getMessage());
                errorMessage = "Registration failed: " + e.getMessage();
                return null;
            }
        }

        @Override
        protected void onPostExecute(String objectId) {
            if (objectId != null) {
                Toast.makeText(RegisterActivity.this, "Registration is complete", Toast.LENGTH_SHORT).show();
                Intent intent = new Intent(RegisterActivity.this, LoginActivity.class);
                intent.putExtra("username", username); // Pass username for login
                startActivity(intent);
                finish();
            } else {
                Toast.makeText(RegisterActivity.this, errorMessage, Toast.LENGTH_SHORT).show();
            }
        }
    }

    private String hashPassword(String password) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(password.getBytes());
            return android.util.Base64.encodeToString(hash, android.util.Base64.NO_WRAP);
        } catch (NoSuchAlgorithmException e) {
            Log.e(TAG, "Password hashing error: " + e.getMessage());
            return null;
        }
    }
}