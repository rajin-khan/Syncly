let offset = 0;
const limit = 50;

async function loadFiles(append = false) {
    const jwt = localStorage.getItem('jwt');
    const errorMessage = document.getElementById('error-message');
    const filesTableBody = document.getElementById('files-table-body');
    const viewMoreBtn = document.getElementById('view-more-btn');

    if (!jwt) {
        errorMessage.textContent = 'Please log in first.';
        errorMessage.style.display = 'block';
        window.location.href = '/static/login.html';
        return;
    }

    try {
        console.log(`Fetching files with JWT: ${jwt}, offset: ${offset}, limit: ${limit}`);
        const response = await fetch(`http://127.0.0.1:8000/viewfiles?limit=${limit}&offset=${offset}`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${jwt}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! Status: ${response.status}, Response: ${errorText}`);
        }

        const files = await response.json();
        console.log("Files response:", files);

        if (files.length === 0 && offset === 0) {
            filesTableBody.innerHTML = '<tr><td colspan="4">No files found.</td></tr>';
            viewMoreBtn.style.display = 'none';
            return;
        }

        if (!append) {
            filesTableBody.innerHTML = ''; // Clear table only on initial load
        }

        files.forEach(file => {
            const sizeStr = file.size === 'Unknown' ? 'Unknown' : `${(file.size / 1024 / 1024).toFixed(2)} MB`;
            filesTableBody.innerHTML += `
                <tr>
                    <td>${file.name}</td>
                    <td>${file.provider}</td>
                    <td>${sizeStr}</td>
                    <td><a href="${file.path}" target="_blank">View</a></td>
                </tr>
            `;
        });

        // Show "View More" if there might be more files
        if (files.length === limit) {
            viewMoreBtn.style.display = 'block';
        } else {
            viewMoreBtn.style.display = 'none';
        }

    } catch (error) {
        console.error('Error fetching files:', error);
        errorMessage.textContent = `Failed to load files: ${error.message}`;
        errorMessage.style.display = 'block';
    }
}

function viewMore() {
    offset += limit;
    loadFiles(true); // Append new files
}

function logout() {
    localStorage.removeItem('jwt');
    window.location.href = '/static/login.html';
}

window.onload = () => {
    console.log("viewfiles.js loaded");
    loadFiles(false); // Initial load, no append
    document.getElementById('view-more-btn').addEventListener('click', viewMore);
};