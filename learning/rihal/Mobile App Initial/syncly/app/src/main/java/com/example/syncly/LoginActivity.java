package com.example.syncly;

import android.content.Intent;
import android.os.Bundle;
import android.text.method.HideReturnsTransformationMethod;
import android.text.method.PasswordTransformationMethod;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

public class LoginActivity extends AppCompatActivity {

    private EditText emailInput, passwordInput;
    private ImageView togglePasswordVisibility;
    private Button loginButton;
    private boolean isPasswordVisible = false; // Default state (hidden)

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login);

        // Initialize UI components
        emailInput = findViewById(R.id.email_input);
        passwordInput = findViewById(R.id.password_input);
        togglePasswordVisibility = findViewById(R.id.toggle_password_visibility);
        loginButton = findViewById(R.id.btn_login);

        // Set Click Listener for Password Toggle
        togglePasswordVisibility.setOnClickListener(v -> {
            if (isPasswordVisible) {
                // Hide password
                passwordInput.setTransformationMethod(PasswordTransformationMethod.getInstance());
                togglePasswordVisibility.setImageResource(R.drawable.ic_visibility_off);
            } else {
                // Show password
                passwordInput.setTransformationMethod(HideReturnsTransformationMethod.getInstance());
                togglePasswordVisibility.setImageResource(R.drawable.ic_visibility);
            }
            isPasswordVisible = !isPasswordVisible; // Toggle state
            passwordInput.setSelection(passwordInput.getText().length()); // Keep cursor at end
        });

        // Set login button click listener
        loginButton.setOnClickListener(v -> {
            String email = emailInput.getText().toString().trim();
            String password = passwordInput.getText().toString().trim();

            if (email.isEmpty() || password.isEmpty()) {
                Toast.makeText(LoginActivity.this, "Please enter both email and password", Toast.LENGTH_SHORT).show();
            } else {
                if (email.equals("test@example.com") && password.equals("password123")) {
                    Toast.makeText(LoginActivity.this, "Login Successful!", Toast.LENGTH_SHORT).show();
                    // Navigate to HomeActivity after successful login
                    Intent intent = new Intent(LoginActivity.this, HomeActivity.class);
                    startActivity(intent);
                    finish(); // Close the LoginActivity so user can't go back
                } else {
                    Toast.makeText(LoginActivity.this, "Invalid email or password", Toast.LENGTH_SHORT).show();
                }
            }
        });
    }
}
