package org.example;

import com.google.api.client.auth.oauth2.Credential;
import com.google.api.client.googleapis.javanet.GoogleNetHttpTransport;
import com.google.api.client.json.gson.GsonFactory;
import com.google.api.services.drive.Drive;
import com.google.api.client.googleapis.auth.oauth2.GoogleAuthorizationCodeFlow;
import java.io.FileInputStream;
import java.util.Collections;

public class GoogleDriveService implements DriveService {
    private Drive service;
    private static final String CREDENTIALS_FILE = "src/main/resources/credentials.json";

    @Override
    public void authenticate(int bucketNumber, String userId) {
        try {
            GoogleAuthorizationCodeFlow flow = new GoogleAuthorizationCodeFlow.Builder(
                    GoogleNetHttpTransport.newTrustedTransport(),
                    GsonFactory.getDefaultInstance(),
                    "client_id", "client_secret", Collections.singletonList("https://www.googleapis.com/auth/drive"))
                    .setDataStoreFactory(new FileDataStoreFactory(new java.io.File("tokens")))
                    .build();
            Credential credential = flow.loadCredential(userId + "_" + bucketNumber);
            if (credential == null) {
                String url = flow.newAuthorizationUrl().setRedirectUri("urn:ietf:wg:oauth:2.0:oob").build();
                System.out.println("Authorize: " + url);
                String code = new Scanner(System.in).nextLine();
                credential = flow.newTokenRequest(code).execute();
                flow.createAndStoreCredential(credential, userId + "_" + bucketNumber);
            }
            service = new Drive.Builder(GoogleNetHttpTransport.newTrustedTransport(), GsonFactory.getDefaultInstance(), credential)
                    .setApplicationName("Syncly").build();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    @Override
    public List<Map<String, Object>> listFiles(String query) {
        // Implement file listing
        return new ArrayList<>();
    }

    @Override
    public long[] checkStorage() {
        // Implement storage check
        return new long[]{0, 0};
    }
}