document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    try {
        const response = await fetch('/token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
        });

        const result = await response.json();
        console.log("Login response:", result);

        if (response.ok) {
            // Store JWT in localStorage for homepage.js
            localStorage.setItem('jwt', result.access_token);

            // Display the JWT
            document.getElementById('jwt-token').textContent = result.access_token;
            document.getElementById('token-display').style.display = 'block';

            // Start countdown and redirect
            let countdown = 10;
            const countdownElement = document.getElementById('countdown');
            countdownElement.textContent = countdown;

            const interval = setInterval(() => {
                countdown -= 1;
                countdownElement.textContent = countdown;
                if (countdown <= 0) {
                    clearInterval(interval);
                    window.location.href = '/static/homepage.html';
                }
            }, 1000);
        } else {
            alert(result.detail || 'Login failed');
        }
    } catch (error) {
        console.error("Error during login:", error);
        alert("An error occurred. Please try again.");
    }
});