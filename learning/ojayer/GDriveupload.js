const fs = require("fs");
const path = require("path");
const { google } = require("googleapis");

// Load Google Drive credentials
const CREDENTIALS_PATH = "credentials.json"; // Update this with your JSON file path
const SCOPES = ["https://www.googleapis.com/auth/drive.file"];

// Authenticate Google Drive API
function authenticateGoogleDrive() {
    const auth = new google.auth.GoogleAuth({
        keyFile: CREDENTIALS_PATH,
        scopes: SCOPES,
    });
    return google.drive({ version: "v3", auth });
}

// Function to upload a file to Google Drive
async function uploadToDrive(drive, filePath, fileName, folderId) {
    const fileMetadata = {
        name: fileName,
        parents: folderId ? [folderId] : undefined, // Add the file to a specific folder if provided
    };
    const media = {
        mimeType: "application/octet-stream",
        body: fs.createReadStream(filePath),
    };
    const response = await drive.files.create({
        resource: fileMetadata,
        media: media,
        fields: "id",
    });
    return response.data.id;
}

// Function to split a file into chunks and upload to Google Drive
async function splitFile(filePath, chunkSize, folderId) {
    const drive = authenticateGoogleDrive();
    const readStream = fs.createReadStream(filePath, { highWaterMark: chunkSize });
    let chunkIndex = 0;

    for await (const chunk of readStream) {
        const chunkFileName = `${path.basename(filePath)}.part${chunkIndex}`;
        const tempFilePath = path.join(__dirname, chunkFileName);

        // Write the chunk to a temporary file
        fs.writeFileSync(tempFilePath, chunk);

        // Upload the chunk to Google Drive
        const fileId = await uploadToDrive(drive, tempFilePath, chunkFileName, folderId);
        console.log(`Uploaded chunk ${chunkIndex} with file ID: ${fileId}`);

        // Remove the temporary file after upload
        fs.unlinkSync(tempFilePath);

        chunkIndex++;
    }

    console.log(`File successfully split and uploaded in ${chunkIndex} chunks.`);
}

// Replace with your file path and chunk size
const filePath = "csv_result-Rice_Cammeo_Osmancik new.csv";
const chunkSize = 1024 * 10; // 10 KB

// Replace with the ID of the folder where chunks should be uploaded (or null for root directory)
const folderId = "13QsCiHzjSm26gKPiomrtJaSpBcHFlZzF";

splitFile(filePath, chunkSize, folderId).catch((err) => {
    console.error("Error during file splitting and uploading:", err.message);
});

