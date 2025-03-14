package com.example.syncly;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

public class LoginActivity extends AppCompatActivity {

    private EditText emailInput, passwordInput;
    private Button loginButton;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login); // Linking the layout

        //Initialize views
        emailInput = findViewById(R.id.email_input);
        passwordInput = findViewById(R.id.password_input);
        loginButton = findViewById(R.id.btn_login);

        //Set login button click listener
        loginButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                //Get email and password input
                String email = emailInput.getText().toString();
                String password = passwordInput.getText().toString();

                //Simple validation (check if fields are empty)
                if (email.isEmpty() || password.isEmpty()) {
                    //Show a Toast if fields are empty
                    Toast.makeText(LoginActivity.this, "Please enter both email and password", Toast.LENGTH_SHORT).show();
                } else {
                    //Simulate login (you can replace this with actual authentication logic)
                    //Here we can also add backend integration for authentication

                    //Example login success
                    if (email.equals("test@example.com") && password.equals("password123")) {
                        //Navigate to HomeActivity (you can change it to another screen)
                        Intent intent = new Intent(LoginActivity.this, HomeActivity.class);
                        startActivity(intent);
                        finish(); //Optional: Close the LoginActivity after transitioning
                    } else {
                        //Invalid login attempt
                        Toast.makeText(LoginActivity.this, "Invalid email or password", Toast.LENGTH_SHORT).show();
                    }
                }
            }
        });
    }
}
