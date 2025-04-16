async function loadStorageInfo() {
    const jwt = localStorage.getItem('jwt');
    const errorMessage = document.getElementById('error-message');

    if (!jwt) {
        errorMessage.textContent = 'Please log in first.';
        errorMessage.style.display = 'block';
        window.location.href = '/static/login.html';
        return;
    }

    try {
        const response = await fetch('http://127.0.0.1:8000/storage', {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${jwt}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            if (response.status === 401) {
                localStorage.removeItem('jwt');
                window.location.href = '/static/login.html';
                return;
            }
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const data = await response.json();
        console.log("Storage info response:", data);

        document.getElementById('total-storage').textContent = data.total_storage_gb || '0';
        document.getElementById('used-space').textContent = data.used_storage_gb || '0';
        document.getElementById('free-space').textContent = data.free_storage_gb || '0';
    } catch (error) {
        console.error('Error fetching storage info:', error);
        errorMessage.textContent = `Failed to load storage info: ${error.message}`;
        errorMessage.style.display = 'block';
    }
}

function toggleForm(formId) {
    const forms = ['upload-form', 'download-form', 'bucket-form'];
    forms.forEach(id => {
        const form = document.getElementById(id);
        form.style.display = id === formId ? 'block' : 'none';
    });
}

async function uploadFile() {
    const jwt = localStorage.getItem('jwt');
    const fileInput = document.getElementById('upload-file');
    const errorMessage = document.getElementById('error-message');

    if (!fileInput.files[0]) {
        errorMessage.textContent = 'Please select a file.';
        errorMessage.style.display = 'block';
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const response = await fetch('http://127.0.0.1:8000/files/upload', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${jwt}`
            },
            body: formData
        });

        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const result = await response.json();
        alert(result.message);
        fileInput.value = '';
        toggleForm('upload-form');
    } catch (error) {
        console.error('Error uploading file:', error);
        errorMessage.textContent = `Upload failed: ${error.message}`;
        errorMessage.style.display = 'block';
    }
}

async function downloadFile() {
    const jwt = localStorage.getItem('jwt');
    const fileName = document.getElementById('download-file-name').value.trim();
    const errorMessage = document.getElementById('error-message');

    if (!fileName) {
        errorMessage.textContent = 'Please enter a file name.';
        errorMessage.style.display = 'block';
        return;
    }

    try {
        const response = await fetch(`http://127.0.0.1:8000/files/download?file_name=${encodeURIComponent(fileName)}`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${jwt}`
            }
        });

        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        document.getElementById('download-file-name').value = '';
        toggleForm('download-form');
    } catch (error) {
        console.error('Error downloading file:', error);
        errorMessage.textContent = `Download failed: ${error.message}`;
        errorMessage.style.display = 'block';
    }
}

async function addBucket() {
    const jwt = localStorage.getItem('jwt');
    const bucketType = document.getElementById('bucket-type').value;
    const errorMessage = document.getElementById('error-message');

    if (!jwt) {
        errorMessage.textContent = 'Please log in first.';
        errorMessage.style.display = 'block';
        window.location.href = '/static/login.html';
        return;
    }

    try {
        console.log(`Adding ${bucketType} bucket with JWT:`, jwt);
        const response = await fetch('http://127.0.0.1:8000/drives', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${jwt}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ drive_type: bucketType })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! Status: ${response.status}, Response: ${errorText}`);
        }

        const result = await response.json();
        console.log("Add bucket response:", result);
        alert(result.message);
        toggleForm('bucket-form');
        loadStorageInfo();
    } catch (error) {
        console.error('Error adding bucket:', error);
        errorMessage.textContent = `Failed to add bucket: ${error.message}`;
        errorMessage.style.display = 'block';
    }
}

function logout() {
    localStorage.removeItem('jwt');
    window.location.href = '/static/login.html';
}

window.onload = () => {
    loadStorageInfo();
};