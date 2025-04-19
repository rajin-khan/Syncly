document.getElementById('registerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    const response = await fetch('/register', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, email, password }),
    });

    const result = await response.json();
    if (response.ok) {
        alert('Registration successful!');
        window.location.href = '/static/login.html';
    } else {
        alert(result.detail || 'Registration failed');
    }
});