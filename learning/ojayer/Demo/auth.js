const express = require('express');
const fs = require('fs');
const { google } = require('googleapis');

const router = express.Router();
const credentials = JSON.parse(fs.readFileSync('credentials.json', 'utf8')).web;

const oauth2Client = new google.auth.OAuth2(
    credentials.client_id,
    credentials.client_secret,
    credentials.redirect_uris[0] // Make sure this is the updated callback URI
);

const SCOPES = ['https://www.googleapis.com/auth/drive'];

// Redirect user to Google OAuth
router.get('/auth/google', (req, res) => {
    const authUrl = oauth2Client.generateAuthUrl({
        access_type: 'offline',
        scope: SCOPES,
        include_granted_scopes: true,
    });
    res.redirect(authUrl);
});

// Handle the callback
router.get('/auth/google/callback', async (req, res) => {
    const code = req.query.code;
    if (!code) {
        return res.status(400).send("Authorization code not found.");
    }

    try {
        const { tokens } = await oauth2Client.getToken(code);
        oauth2Client.setCredentials(tokens);

        // Save tokens for future use (optional)
        fs.writeFileSync('tokens.json', JSON.stringify(tokens));

        res.send("Authentication successful! You can now access your Google Drive.");
    } catch (error) {
        console.error("Error authenticating:", error);
        res.status(500).send("Authentication failed.");
    }
});

module.exports = router;



const authRoutes = require('./auth');

const app = express();
app.use(authRoutes);

app.get('/', (req, res) => {
  res.send('Welcome to the Express server!');
});

app.listen(5500, () => {
    console.log('Server running on http://localhost:5500');
});