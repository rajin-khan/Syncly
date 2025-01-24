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

// Function to merge chunks into a single file using streams
function mergeFiles(outputFilePath, chunksDir, callback) {
  if (!fs.existsSync(chunksDir)) {
    throw new Error("Chunks directory does not exist");
  }

  const chunkFiles = fs.readdirSync(chunksDir).sort((a, b) => {
    const indexA = parseInt(a.split(".part")[1], 10);
    const indexB = parseInt(b.split(".part")[1], 10);
    return indexA - indexB;
  });

  const outputStream = fs.createWriteStream(outputFilePath);

  function processChunk(index) {
    if (index >= chunkFiles.length) {
      outputStream.end(); // Close the stream after processing all chunks
      console.log(`Files merged successfully into ${outputFilePath}`);
      if (callback) callback(null);
      return;
    }

    const chunkPath = path.join(chunksDir, chunkFiles[index]);
    const readStream = fs.createReadStream(chunkPath);

    readStream.pipe(outputStream, { end: false });

    readStream.on("end", () => {
      console.log(`Processed chunk: ${chunkFiles[index]}`);
      processChunk(index + 1); // Process the next chunk
    });

    readStream.on("error", (err) => {
      console.error(`Error reading chunk ${chunkFiles[index]}:`, err.message);
      outputStream.end();
      if (callback) callback(err);
    });
  }

  processChunk(0);

  outputStream.on("error", (err) => {
    console.error("Error writing to output file:", err.message);
    if (callback) callback(err);
  });
}

// Example Usage
const filePath = "csv_result-Rice_Cammeo_Osmancik new.csv"; // Replace with your file
const chunkSize = 1024 * 10; // 10 KB
const outputFilePath = "output.csv";

splitFile(filePath, chunkSize, (err, chunksDir) => {
  if (err) {
    console.error("Error during file splitting:", err.message);
    return;
  }

  mergeFiles(outputFilePath, chunksDir, (mergeErr) => {
    if (mergeErr) {
      console.error("Error during file merging:", mergeErr.message);
    }
  });
});
