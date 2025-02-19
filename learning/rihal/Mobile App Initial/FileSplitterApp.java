import javafx.application.Application;
import javafx.geometry.Insets;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.TextField;
import javafx.scene.layout.VBox;
import javafx.stage.FileChooser;
import javafx.stage.Stage;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;

public class FileSplitterApp extends Application {

    private File selectedFile;

    public static void main(String[] args) {
        launch(args);
    }

    @Override
    public void start(Stage primaryStage) {
        primaryStage.setTitle("File Splitter");

        //UI Components
        Label fileLabel = new Label("Selected File: None");
        Button selectFileButton = new Button("Select File");
        Label chunkSizeLabel = new Label("Chunk Size (in bytes):");
        TextField chunkSizeField = new TextField();
        Button splitButton = new Button("Split File");
        Label statusLabel = new Label();

        //File Chooser
        FileChooser fileChooser = new FileChooser();

        //Event Handlers
        selectFileButton.setOnAction(e -> {
            selectedFile = fileChooser.showOpenDialog(primaryStage);
            if (selectedFile != null) {
                fileLabel.setText("Selected File: " + selectedFile.getName());
            }
        });

        splitButton.setOnAction(e -> {
            if (selectedFile == null) {
                statusLabel.setText("Please select a file first!");
                return;
            }

            try {
                int chunkSize = Integer.parseInt(chunkSizeField.getText());
                if (chunkSize <= 0) {
                    statusLabel.setText("Chunk size must be greater than 0!");
                    return;
                }

                splitFile(selectedFile, chunkSize);
                statusLabel.setText("File split successfully!");
            } catch (NumberFormatException ex) {
                statusLabel.setText("Invalid chunk size. Please enter a valid number.");
            } catch (IOException ex) {
                statusLabel.setText("An error occurred while splitting the file.");
                ex.printStackTrace();
            }
        });

        //Layout
        VBox layout = new VBox(10);
        layout.setPadding(new Insets(10));
        layout.getChildren().addAll(fileLabel, selectFileButton, chunkSizeLabel, chunkSizeField, splitButton, statusLabel);

        //Scene
        Scene scene = new Scene(layout, 400, 200);
        primaryStage.setScene(scene);
        primaryStage.show();
    }

    //Method to split the file
    private void splitFile(File file, int chunkSize) throws IOException {
        try (FileInputStream fis = new FileInputStream(file)) {
            byte[] buffer = new byte[chunkSize];
            int bytesRead;
            int fileChunk = 0;

            while ((bytesRead = fis.read(buffer)) > 0) {
                File chunkFile = new File(file.getAbsolutePath() + ".part" + fileChunk + ".csv");
                try (FileOutputStream fos = new FileOutputStream(chunkFile)) {
                    fos.write(buffer, 0, bytesRead);
                }
                fileChunk++;
            }

            System.out.println("File split into " + fileChunk + " chunks");
        }
    }
}
