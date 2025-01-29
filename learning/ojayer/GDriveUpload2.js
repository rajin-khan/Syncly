const fs = require("fs");
const path = require("path");
const { google } = require("googleapis");
const stream = require("stream");

// Load Google Drive credentials
const CREDENTIALS_PATH = "credentials.json";
const SCOPES = ["https://www.googleapis.com/auth/drive.file"];

// Authenticate Google Drive
async function authenticateGoogleDrive() {
    const auth = new google.auth.GoogleAuth({
        keyFile: CREDENTIALS_PATH,
        scopes: SCOPES,
    });
    return google.drive({ version: "v3", auth });
}

// Upload a chunk directly to Google Drive
async function uploadToDrive(drive, chunk, chunkFileName, folderId) {
    const fileMetadata = {
        name: chunkFileName,
        parents: folderId ? [folderId] : undefined,
    };

    const readableStream = new stream.Readable();
    readableStream.push(chunk);
    readableStream.push(null);

    const media = {
        mimeType: "application/octet-stream",
        body: readableStream,
    };

    const response = await drive.files.create({
        resource: fileMetadata,
        media: media,
        fields: "id",
    });

    return response.data.id;
}

// Download a chunk from Google Drive
async function downloadFromDrive(drive, fileId) {
    const response = await drive.files.get(
        { fileId: fileId, alt: "media" },
        { responseType: "stream" }
    );
    return response.data;
}

// Split file, upload chunks to Google Drive, and save metadata
async function splitFile(filePath, chunkSize, folderId) {
    // Authenticate Google Drive
    const drive = await authenticateGoogleDrive();
    // Create a read stream with a highWaterMark option to read the file in chunks
    const readStream = fs.createReadStream(filePath, { highWaterMark: chunkSize });
    // Initialize chunk index and array to store chunk IDs
    let chunkIndex = 0;
    // Loop through each chunk and upload to Google Drive
    const chunkIds = [];

    // Read the file in chunks
    for await (const chunk of readStream) {
        // Upload the chunk to Google Drive
        const chunkFileName = `${path.basename(filePath)}.part${chunkIndex}`;
        // Upload the chunk to Google Drive directly from the stream
        const fileId = await uploadToDrive(drive, chunk, chunkFileName, folderId);
        console.log(`Uploaded chunk ${chunkIndex} with file ID: ${fileId}`);
        // Store the chunk ID
        chunkIds.push(fileId);
        chunkIndex++;
    }
    // Save metadata file with chunk IDs
    fs.writeFileSync(`${filePath}.metadata.json`, JSON.stringify(chunkIds)); // Save chunk IDs
    console.log(`File split and uploaded in ${chunkIndex} chunks.`);
}

// Merge chunks into a single file after downloading from Google Drive
async function mergeFiles(outputFilePath, metadataFile) {
    if (!fs.existsSync(metadataFile)) {
        console.error("Metadata file not found!");
        return;
    }

    //
    const chunkIds = JSON.parse(fs.readFileSync(metadataFile, "utf-8"));
    // Authenticate Google Drive
    const drive = await authenticateGoogleDrive();
    // Create a write stream to save the merged file
    const writeStream = fs.createWriteStream(outputFilePath);

    for (const fileId of chunkIds) {
        console.log(`Downloading chunk: ${fileId}`);
        // Download the chunk from Google Drive
        const chunkStream = await downloadFromDrive(drive, fileId);

        // Pipe the chunk stream to the write stream
        await new Promise((resolve, reject) => {
            chunkStream.pipe(writeStream, { end: false });
            // Resolve the promise when the chunk stream ends
            chunkStream.on("end", resolve);
            // Reject the promise if there is an error
            chunkStream.on("error", reject);
        });
    }

    // Close the write stream after merging all chunks
    writeStream.end();
    console.log(`Files merged successfully into ${outputFilePath}`);
}

// File path and chunk size
const filePath = "csv_result-Rice_Cammeo_Osmancik new.csv";
const chunkSize = 1024 * 10; // 10 KB
const folderId = "13QsCiHzjSm26gKPiomrtJaSpBcHFlZzF";
const metadataFile = `csv_result-Rice_Cammeo_Osmancik new.csv.metadata.json`;

// Uncomment to split and upload
//splitFile(filePath, chunkSize, folderId).catch(err => console.error("Error splitting and uploading:", err));

// Uncomment to merge and download
 mergeFiles("merged_file.csv", metadataFile).catch(err => console.error("Error merging:", err));


splitFile(filePath, chunkSize, folderId).catch((err) => {
    console.error("Error during file splitting and uploading:", err.message);
});
