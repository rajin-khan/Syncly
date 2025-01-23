const { splitFile } = require('./filehandler');
const { authenticate, uploadFile } = require('./googleDrive');
const path = require('path');
const fs = require('fs');

(async () => {
    const filePath = 'large_video.mp4';
    const chunkSize = 1024 * 1024 * 10; // 10 MB

    // Split the file
    splitFile(filePath, chunkSize);

    // Simulate delay to ensure file splitting is complete
    setTimeout(async () => {
        const auth = await authenticate();

        // Upload each chunk to Google Drive
        let chunkIndex = 0;
        while (true) {
            const chunkFileName = `${filePath}.part${chunkIndex}`;
            if (fs.existsSync(chunkFileName)) {
                await uploadFile(auth, chunkFileName, path.basename(chunkFileName));
                chunkIndex++;
            } else {
                break;
            }
        }

        console.log('All chunks uploaded to Google Drive.');
    }, 5000);
})();
