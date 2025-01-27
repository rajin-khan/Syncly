package com.example.demo;

import javafx.application.Application;
import javafx.scene.Scene;
import javafx.scene.layout.VBox;
import javafx.stage.Stage;

public class HomePage extends Application {

    @Override
    public void start(Stage primaryStage) {
        primaryStage.setTitle("Google Drive Aggregator");

        VBox root = new VBox();
        Scene scene = new Scene(root, 600, 400);

        //Initialize the main UI controller
        MainController mainController = new MainController(root);
        mainController.initUI();

        primaryStage.setScene(scene);
        primaryStage.show();
    }

    public static void main(String[] args) {
        launch(args);
    }
}
