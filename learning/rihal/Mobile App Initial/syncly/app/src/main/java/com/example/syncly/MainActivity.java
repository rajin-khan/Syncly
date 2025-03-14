package com.example.syncly;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {
    private Button startButton, loginButton;
    private Database db = Database.getInstance();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        startButton = findViewById(R.id.btn_start);
        loginButton = findViewById(R.id.btn_login);

        startButton.setOnClickListener(v -> {
            //Start here button clicked
            //You can navigate to a different activity if needed
        });

        loginButton.setOnClickListener(v -> {
            //Login button clicked, navigate to LoginActivity
            Intent intent = new Intent(MainActivity.this, LoginActivity.class);
            startActivity(intent);
        });
    }
}
