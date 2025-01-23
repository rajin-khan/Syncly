package com.example.demo;

import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.ListView;
import javafx.scene.layout.VBox;

public class MainController {

    private VBox root;

    public MainController(VBox root) {
        this.root = root;
    }

    public void initUI() {
        Label titleLabel = new Label("Google Drive Aggregator");
        Button addAccountButton = new Button("Add Google Account");
        ListView<String> accountsList = new ListView<>();

        // Event to add account
        addAccountButton.setOnAction(e -> {
            // Handle Google account login and add account
            String account = addGoogleAccount();
            if (account != null) {
                accountsList.getItems().add(account);
            }
        });

        root.getChildren().addAll(titleLabel, addAccountButton, accountsList);
    }

    private String addGoogleAccount() {
        // TODO: Implement Google OAuth2 login and return account email
        return "user@example.com";
    }
}
