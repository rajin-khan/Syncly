const fs = require("fs");
const path = require("path");

// Function to split a file into chunks using streams
function splitFile(filePath, chunkSize, callback) {
  const chunksDir = `${filePath}_chunks`;

  // Ensure a directory exists for the chunks
  if (!fs.existsSync(chunksDir)) {
    fs.mkdirSync(chunksDir);
  }

  const readStream = fs.createReadStream(filePath, { highWaterMark: chunkSize });
  let chunkIndex = 0;

  readStream.on("data", (chunk) => {
    const chunkPath = path.join(chunksDir, `${path.basename(filePath)}.part${chunkIndex}`);
    fs.writeFileSync(chunkPath, chunk);
    chunkIndex++;
  });

  readStream.on("end", () => {
    console.log(`File split successfully into ${chunkIndex} chunks in ${chunksDir}`);
    if (callback) callback(null, chunksDir);
  });

  readStream.on("error", (err) => {
    console.error("Error while splitting file:", err.message);
    if (callback) callback(err);
  });
}


// Example Usage
const filePath = "csv_result-Rice_Cammeo_Osmancik new.csv"; 
const chunkSize = 1024 * 10; // 10 KB

splitFile(filePath, chunkSize, (err, chunksDir) => {
  if (err) {
    console.error("Error during file splitting:", err.message);
    return;
  }
});
