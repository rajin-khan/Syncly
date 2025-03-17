document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    const response = await fetch('/token', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `username=${username}&password=${password}`,
    });

    const result = await response.json();
    console.log("Login response:", result);  // Log the response for debugging

    if (response.ok) {
        // Display the JWT
        document.getElementById('jwt-token').textContent = result.access_token;
        document.getElementById('token-display').style.display = 'block';
    } else {
        alert(result.detail || 'Login failed');
    }
});