const fs = require('fs');

function splitFile(filePath, chunkSize) {
    const fileStream = fs.createReadStream(filePath, { highWaterMark: chunkSize });
    let chunkIndex = 0;

    console.log(`Splitting file: ${filePath} into chunks of ${chunkSize} bytes`);

    fileStream.on('data', (chunk) => {
        const chunkFileName = `${filePath}.part${chunkIndex}`;
        fs.writeFileSync(chunkFileName, chunk);
        console.log(`Created: ${chunkFileName}`);
        chunkIndex++;
    });

    fileStream.on('end', () => {
        console.log(`File split into ${chunkIndex} chunks successfully.`);
    });

    fileStream.on('error', (err) => {
        console.error(`Error while splitting file: ${err.message}`);
    });
}

function mergeFile(outputFile, chunkFiles) {
    const outputStream = fs.createWriteStream(outputFile);

    console.log(`Merging chunks into: ${outputFile}`);

    chunkFiles.forEach((chunkFile, index) => {
        if (fs.existsSync(chunkFile)) {
            const chunkData = fs.readFileSync(chunkFile);
            outputStream.write(chunkData);
            console.log(`Merged: ${chunkFile}`);
        } else {
            console.warn(`Warning: ${chunkFile} does not exist.`);
        }
    });

    outputStream.end(() => {
        console.log(`File merged successfully as: ${outputFile}`);
    });

    outputStream.on('error', (err) => {
        console.error(`Error while merging file: ${err.message}`);
    });
}

module.exports = { splitFile, mergeFile };
