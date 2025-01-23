import com.google.api.services.drive.Drive;
import com.google.api.services.drive.model.File;

import java.io.FileInputStream;
import java.io.IOException;

public class DriveUploader {

    private final Drive driveService;

    public DriveUploader(Drive driveService) {
        this.driveService = driveService;
    }

    public void uploadFile(java.io.File file, String parentFolderId) throws IOException {
        File fileMetadata = new File();
        fileMetadata.setName(file.getName());
        if (parentFolderId != null) {
            fileMetadata.setParents(java.util.Collections.singletonList(parentFolderId));
        }

        try (FileInputStream fileInputStream = new FileInputStream(file)) {
            Drive.Files.Create request = driveService.files().create(fileMetadata, new com.google.api.client.http.InputStreamContent(
                    "application/octet-stream", fileInputStream));
            request.execute();
        }
    }
}
