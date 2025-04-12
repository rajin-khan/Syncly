// Load storage info on page load
document.addEventListener('DOMContentLoaded', async () => {
    const jwt = localStorage.getItem('jwt');
    if (!jwt) {
        console.error('No JWT found in localStorage');
        showError('Please log in again.');
        window.location.href = '/static/login.html';
        return;
    }

    try {
        console.log('Fetching storage info with JWT:', jwt.substring(0, 20) + '...');
        const response = await fetch('http://127.0.0.1:8000/storage', {
            headers: {
                'Authorization': `Bearer ${jwt}`
            }
        });

        console.log('Storage response:', {
            status: response.status,
            statusText: response.statusText
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            console.error('Storage fetch error:', errorData);
            throw new Error(errorData.detail || `Storage fetch failed: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('Storage data received:', JSON.stringify(data, null, 2));
        if (!data.storages || data.storages.length === 0) {
            console.warn('No storage data returned');
            showError('No drives found. Add a bucket to see storage details.');
        }
        document.getElementById('total-storage').textContent = data.total_storage_gb || 0;
        document.getElementById('used-space').textContent = data.used_storage_gb || 0;
        document.getElementById('free-space').textContent = data.free_storage_gb || 0;
    } catch (error) {
        console.error('Error fetching storage:', error);
        showError(`Failed to load storage info: ${error.message}`);
    }
});

function toggleForm(formId) {
    const forms = ['upload-form', 'download-form', 'bucket-form'];
    forms.forEach(id => {
        document.getElementById(id).style.display = id === formId ? 'block' : 'none';
    });
    document.getElementById('error-message').style.display = 'none';
}

async function uploadFile() {
    const fileInput = document.getElementById('upload-file');
    const jwt = localStorage.getItem('jwt');
    if (!fileInput.files.length) {
        showError('Please select a file.');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        console.log('Uploading file...');
        const response = await fetch('http://127.0.0.1:8000/files/upload', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${jwt}`
            },
            body: formData
        });
        const data = await response.json();
        if (!response.ok) {
            console.error('Upload error:', data);
            throw new Error(data.detail || 'Upload failed');
        }
        alert(data.message);
        fileInput.value = '';
        toggleForm(null);
    } catch (error) {
        console.error('Upload error:', error);
        showError(`Upload failed: ${error.message}`);
    }
}

async function downloadFile() {
    const fileName = document.getElementById('download-file-name').value.trim();
    const jwt = localStorage.getItem('jwt');
    if (!fileName) {
        showError('Please enter a file name.');
        return;
    }

    try {
        console.log('Downloading file:', fileName);
        const response = await fetch(`http://127.0.0.1:8000/files/download?file_name=${encodeURIComponent(fileName)}`, {
            headers: {
                'Authorization': `Bearer ${jwt}`
            }
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            console.error('Download error:', errorData);
            throw new Error(errorData.detail || 'Download failed');
        }
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
        toggleForm(null);
    } catch (error) {
        console.error('Download error:', error);
        showError(`Upload failed: ${error.message}`);
    }
}

async function addBucket() {
    const driveType = document.getElementById('bucket-type').value;
    const jwt = localStorage.getItem('jwt');

    try {
        console.log('Adding bucket:', driveType);
        const response = await fetch('http://127.0.0.1:8000/drives', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${jwt}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ drive_type: driveType })
        });
        const data = await response.json();
        if (!response.ok) {
            console.error('Add bucket error:', data);
            throw new Error(data.detail || 'Failed to add bucket');
        }
        alert(data.message);
        toggleForm(null);
        // Refresh storage info
        document.dispatchEvent(new Event('DOMContentLoaded'));
    } catch (error) {
        console.error('Add bucket error:', error);
        showError(`Failed to add bucket: ${error.message}`);
    }
}

function logout() {
    console.log('Logging out');
    localStorage.removeItem('jwt');
    window.location.href = '/static/login.html';
}

function showError(message) {
    const errorDiv = document.getElementById('error-message');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}