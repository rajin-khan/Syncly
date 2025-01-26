const fs = require("fs");
const path = require("path");
const { google } = require("googleapis");
const stream = require("stream");

// Load Google Drive credentials
const CREDENTIALS_PATH = "credentials.json";
const SCOPES = ["https://www.googleapis.com/auth/drive.file"];

// Authenticate Google Drive
function authenticateGoogleDrive() {
    const auth = new google.auth.GoogleAuth({
        keyFile: CREDENTIALS_PATH,
        scopes: SCOPES,
    });
    return google.drive({ version: "v3", auth });
}

// Function to upload a chunk directly to Google Drive without storing it on disk
async function uploadToDrive(drive, chunk, chunkFileName, folderId) {
    const fileMetadata = {
        name: chunkFileName,
        parents: folderId ? [folderId] : undefined, // Add the file to a specific folder if provided
    };

    // Create a Readable stream from the chunk
    const readableStream = new stream.Readable();
    readableStream.push(chunk); // Push the chunk into the stream
    readableStream.push(null); // Signal end of stream

    const media = {
        mimeType: "application/octet-stream",
        body: readableStream, // Pass the readable stream
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

        // Upload the chunk to Google Drive directly from the stream
        const fileId = await uploadToDrive(drive, chunk, chunkFileName, folderId);
        console.log(`Uploaded chunk ${chunkIndex} with file ID: ${fileId}`);


        chunkIndex++;
    }

    console.log(`File successfully split and uploaded in ${chunkIndex} chunks.`);
}

// file path and chunk size
const filePath = "csv_result-Rice_Cammeo_Osmancik new.csv";
const chunkSize = 1024 * 10; // 10 KB

// FolderId where the file will be uploaded
const folderId = "13QsCiHzjSm26gKPiomrtJaSpBcHFlZzF";

splitFile(filePath, chunkSize, folderId).catch((err) => {
    console.error("Error during file splitting and uploading:", err.message);
});