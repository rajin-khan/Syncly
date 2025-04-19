function getQueryParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

document.getElementById('registerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    // Check for link_id in the current URL
    const linkId = getQueryParam('link_id');

    try { // Added try...catch for fetch
        const response = await fetch('/register', { // Relative path is fine here
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, email, password }),
        });

        const result = await response.json(); // Attempt to parse JSON for potential error detail

        if (response.ok) {
            alert('Registration successful! Proceeding to login...');
            // Construct login URL, appending link_id if it exists
            let loginUrl = '/static/login.html';
            if (linkId) {
                loginUrl += '?link_id=' + encodeURIComponent(linkId);
                console.log("Redirecting to login with link_id:", linkId);
            } else {
                 console.log("Redirecting to login without link_id.");
            }
            window.location.href = loginUrl; // Redirect to login page (potentially with link_id)
        } else {
            alert(result.detail || 'Registration failed');
        }
    } catch (error) {
        console.error("Error during registration fetch:", error);
        alert("An error occurred during registration. Please try again.");
    }
});