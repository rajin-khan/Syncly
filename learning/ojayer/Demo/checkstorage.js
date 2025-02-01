const { google } = require('googleapis');
const fs = require('fs');
const readline = require('readline');
const path = require('path');

// Load or create .env file
const envPath = path.join(__dirname, '.env');
if (!fs.existsSync(envPath)) {
  fs.writeFileSync(envPath, ''); // Create empty .env if missing
}
const credentials = JSON.parse(fs.readFileSync('credentials.json', 'utf8')).web;
// Configure OAuth2 client
const oauth2Client = new google.auth.OAuth2(
    credentials.client_id,
    credentials.client_secret,
    credentials.redirect_uris[0],
);

const SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly'];
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});


// Check storage using saved tokens
async function checkAllStorage() {
    require('dotenv').config(); // Load .env tokens
    const accounts = [
        { name: 'Account 1', refresh_token: process.env.ACCOUNT_1_REFRESH_TOKEN },
        { name: 'Account 2', refresh_token: process.env.ACCOUNT_2_REFRESH_TOKEN },
        { name: 'Account 3', refresh_token: process.env.ACCOUNT_3_REFRESH_TOKEN },
    ];

    let total_Storage = 0;
    let total_Used = 0;
    for (const account of accounts) {
    try {
      oauth2Client.setCredentials({ refresh_token: account.refresh_token });
      const drive = google.drive({ version: 'v3', auth: oauth2Client });
      const res = await drive.about.get({ fields: 'storageQuota' });

      const limit = parseInt(res.data.storageQuota.limit);
      const usage = parseInt(res.data.storageQuota.usage);
      total_Storage += limit;
      total_Used += usage;
      console.log(`\n--- ${account.name} ---`);
      console.log(`Total: ${Math.round(limit / (1024**3))} GB`);
      console.log(`Used: ${Math.round(usage / (1024**3))} GB`);
    } catch (error) {
      console.error(`Error for ${account.name}:`, error.message);
    }
  }
    console.log(`\n--- Storage details ---`);
    console.log(`Total Storage: ${Math.round(total_Storage / (1024**3))} GB`);
    console.log(`Total Used: ${Math.round(total_Used / (1024**3))} GB`);
    console.log(`Total Free: ${Math.round((total_Storage - total_Used) / (1024**3))} GB`);

    return;
}

// Start authorization for Account 1
//authorizeAndSaveToken(1);
checkAllStorage().catch(console.error);