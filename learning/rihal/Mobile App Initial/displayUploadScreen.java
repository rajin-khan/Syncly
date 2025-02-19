import javafx.stage.FileChooser;

private void displayUploadScreen() {
    VBox uploadScreen = new VBox(10);
    uploadScreen.setPadding(new Insets(10));

    Label uploadLabel = new Label("Upload File:");
    Button chooseFileButton = new Button("Choose File");
    ProgressBar uploadProgress = new ProgressBar(0);

    uploadScreen.getChildren().addAll(uploadLabel, chooseFileButton, uploadProgress);

    root.setCenter(uploadScreen);

    //Event handler for file upload
    chooseFileButton.setOnAction(e -> {
        FileChooser fileChooser = new FileChooser();
        java.io.File selectedFile = fileChooser.showOpenDialog(null);
        if (selectedFile != null) {
            uploadProgress.setProgress(0.5); // Mock progress
            //TODO: Implement file splitting and upload logic
        }
    });
}
