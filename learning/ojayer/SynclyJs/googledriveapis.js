const fs = require('fs');
const { google } = require('googleapis');
const path = require('path');

const CREDENTIALS_PATH = './credentials.json';
const TOKEN_PATH = './token.json';

// Authenticate with Google Drive
async function authenticate() {
    const { client_id, client_secret, redirect_uris } = require(CREDENTIALS_PATH).installed;
    const oAuth2Client = new google.auth.OAuth2(client_id, client_secret, redirect_uris[0]);

    if (fs.existsSync(TOKEN_PATH)) {
        const token = fs.readFileSync(TOKEN_PATH);
        oAuth2Client.setCredentials(JSON.parse(token));
    } else {
        const authUrl = oAuth2Client.generateAuthUrl({
            access_type: 'offline',
            scope: ['https://www.googleapis.com/auth/drive.file'],
        });
        console.log('Authorize this app by visiting this URL:', authUrl);

        const rl = require('readline').createInterface({
            input: process.stdin,
            output: process.stdout,
        });

        rl.question('Enter the code from that page here: ', async (code) => {
            const { tokens } = await oAuth2Client.getToken(code);
            oAuth2Client.setCredentials(tokens);
            fs.writeFileSync(TOKEN_PATH, JSON.stringify(tokens));
            console.log('Token stored to', TOKEN_PATH);
            rl.close();
        });
    }

    return oAuth2Client;
}

// Upload a file to Google Drive
async function uploadFile(auth, filePath, fileName) {
    const drive = google.drive({ version: 'v3', auth });

    const fileMetadata = { name: fileName };
    const media = {
        mimeType: 'application/octet-stream',
        body: fs.createReadStream(filePath),
    };

    try {
        const response = await drive.files.create({
            requestBody: fileMetadata,
            media,
            fields: 'id',
        });
        console.log(`Uploaded ${fileName} to Google Drive with ID: ${response.data.id}`);
    } catch (err) {
        console.error(`Failed to upload ${fileName}:`, err.message);
    }
}

module.exports = { authenticate, uploadFile };
