const urlParams = new URLSearchParams(window.location.search);
        const loginCode = urlParams.get('code');
        const telegramId = urlParams.get('telegram_id');
        const cliCode = urlParams.get('cli_code');

        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            try {
                console.log('Attempting login with username:', username);
                // Step 1: Get JWT from /token
                const tokenResponse = await fetch('http://127.0.0.1:8000/token', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: new URLSearchParams({
                        'username': username,
                        'password': password
                    }).toString()
                });

                console.log('Token response:', {
                    status: tokenResponse.status,
                    statusText: tokenResponse.statusText
                });

                if (!tokenResponse.ok) {
                    const errorData = await tokenResponse.json().catch(() => ({}));
                    console.error('Token error:', errorData);
                    alert(errorData.detail || `Login failed: ${tokenResponse.statusText}`);
                    return;
                }

                const tokenData = await tokenResponse.json();
                console.log('Token received:', tokenData.access_token);

                // Step 2: Handle login type
                if (loginCode && telegramId) {
                    // Telegram login
                    console.log('Processing Telegram login with code:', loginCode, 'telegram_id:', telegramId);
                    const completeResponse = await fetch(
                        `http://127.0.0.1:8000/complete-login?code=${encodeURIComponent(loginCode)}&telegram_id=${encodeURIComponent(telegramId)}`,
                        {
                            method: 'POST',
                            headers: {
                                'Authorization': `Bearer ${tokenData.access_token}`
                            }
                        }
                    );

                    if (!completeResponse.ok) {
                        const errorData = await completeResponse.json().catch(() => ({}));
                        console.error('Complete login error:', errorData);
                        alert(errorData.detail || 'Failed to complete Telegram login');
                        return;
                    }
                    document.getElementById('success-text').textContent = 
                        'You can now return to Telegram. Authentication will complete automatically.';
                    document.getElementById('loginForm').style.display = 'none';
                    document.getElementById('success-message').style.display = 'block';
                } else if (cliCode) {
                    // CLI login
                    console.log('Sending token for CLI login with cli_code:', cliCode);
                    let attempts = 5;
                    let callbackResponse;
                    while (attempts > 0) {
                        try {
                            callbackResponse = await fetch(
                                `http://localhost:8081/?token=${encodeURIComponent(tokenData.access_token)}`,
                                { method: 'GET', mode: 'no-cors' }
                            );
                            console.log('CLI callback response received');
                            break;
                        } catch (err) {
                            console.warn(`CLI callback attempt ${6 - attempts} failed: ${err.message}`);
                            attempts--;
                            await new Promise(resolve => setTimeout(resolve, 2000));
                        }
                    }
                    if (!callbackResponse) {
                        console.error('CLI callback failed after retries');
                        alert('Failed to complete CLI authentication. Please check the terminal.');
                        return;
                    }
                    document.getElementById('success-text').textContent = 
                        'CLI authentication successful. Return to the terminal.';
                    document.getElementById('loginForm').style.display = 'none';
                    document.getElementById('success-message').style.display = 'block';
                } else {
                    // Direct login
                    console.log('Direct login successful; storing JWT and redirecting to homepage');
                    localStorage.setItem('jwt', tokenData.access_token);
                    window.location.href = '/static/homepage.html';
                }
            } catch (error) {
                console.error('Login error:', {
                    message: error.message,
                    stack: error.stack,
                    name: error.name
                });
                alert(`Login failed: ${error.message}`);
            }
        });