import javafx.scene.control.*;
import javafx.scene.layout.*;
import javafx.geometry.*;
import javafx.scene.chart.PieChart;

public class MainUIController {

    private final BorderPane root;

    public MainUIController(BorderPane root) {
        this.root = root;
    }

    public void initUI() {
        // Create header, sidebar, and content sections
        VBox header = createHeader();
        VBox sidebar = createSidebar();
        VBox content = createContent();

        //Add sections to the root layout
        root.setTop(header);
        root.setLeft(sidebar);
        root.setCenter(content);
    }

    private VBox createHeader() {
        Label title = new Label("Google Drive Aggregator");
        title.setStyle("-fx-font-size: 24px; -fx-font-weight: bold;");

        HBox header = new HBox(title);
        header.setPadding(new Insets(10));
        header.setAlignment(Pos.CENTER);
        header.setStyle("-fx-background-color: #2b5797; -fx-text-fill: white;");

        return new VBox(header);
    }

    private VBox createSidebar() {
        Button addAccountButton = new Button("Add Google Account");
        Button uploadFileButton = new Button("Upload File");
        Button settingsButton = new Button("Settings");

        VBox sidebar = new VBox(10, addAccountButton, uploadFileButton, settingsButton);
        sidebar.setPadding(new Insets(10));
        sidebar.setStyle("-fx-background-color: #f4f4f4;");
        sidebar.setPrefWidth(200);

        //Event handlers for navigation
        addAccountButton.setOnAction(e -> displayAccounts());
        uploadFileButton.setOnAction(e -> displayUploadScreen());
        settingsButton.setOnAction(e -> displaySettings());

        return sidebar;
    }

    private VBox createContent() {
        Label welcomeLabel = new Label("Welcome to the Google Drive Aggregator!");
        welcomeLabel.setStyle("-fx-font-size: 18px;");

        VBox content = new VBox(10, welcomeLabel);
        content.setPadding(new Insets(20));
        content.setAlignment(Pos.TOP_CENTER);

        return content;
    }

    private void displayAccounts() {
        VBox accountList = new VBox(10);
        accountList.setPadding(new Insets(10));

        // Mock accounts
        Label account1 = new Label("user1@gmail.com (10 GB used of 15 GB)");
        Label account2 = new Label("user2@gmail.com (2 GB used of 15 GB)");

        accountList.getChildren().addAll(account1, account2);

        root.setCenter(accountList);
    }

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
            // TODO: Implement file chooser and upload logic
            uploadProgress.setProgress(0.5); // Mock progress
        });
    }

    private void displaySettings() {
        VBox settingsScreen = new VBox(10);
        settingsScreen.setPadding(new Insets(10));

        Label settingsLabel = new Label("App Settings:");
        Button manageAccountsButton = new Button("Manage Accounts");
        Button clearDataButton = new Button("Clear Local Data");

        settingsScreen.getChildren().addAll(settingsLabel, manageAccountsButton, clearDataButton);

        root.setCenter(settingsScreen);
    }
}
