package com.example.demo;

import java.io.*;
import java.util.ArrayList;
import java.util.List;

public class FileSplitter {
    public static List<File> splitFile(File file, int chunkSizeMB) throws IOException {
        List<File> chunkFiles = new ArrayList<>();
        int chunkSize = chunkSizeMB * 1024 * 1024;
        try (FileInputStream fis = new FileInputStream(file)) {
            byte[] buffer = new byte[chunkSize];
            int bytesRead;
            int partNumber = 1;
            while ((bytesRead = fis.read(buffer)) > 0) {
                File chunkFile = new File(file.getParent(), file.getName() + ".part" + partNumber++);
                try (FileOutputStream fos = new FileOutputStream(chunkFile)) {
                    fos.write(buffer, 0, bytesRead);
                }
                chunkFiles.add(chunkFile);
            }
        }
        return chunkFiles;
    }
}
