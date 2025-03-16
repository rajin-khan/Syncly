from flask import Flask, request, jsonify
import logging

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/send-otp', methods=['POST'])
def send_otp():
    email = request.json.get('email')
    otp = request.json.get('otp')

    # Render a simple HTML page with EmailJS JavaScript
    html = f"""
    <html>
        <head>
            <script src="https://cdn.jsdelivr.net/npm/emailjs-com@3/dist/email.min.js"></script>
            <script>
                (function() {{
                    emailjs.init('oDBLcZpM-dmzaDFYH');
                    emailjs.send('service_d50t9qq', 'template_fwu8wji', {{
                        to_email: '{email}',
                        otp: '{otp}'
                    }})
                    .then(function(response) {{
                        console.log('OTP sent successfully:', response);
                    }}, function(error) {{
                        console.error('Failed to send OTP:', error);
                    }});
                }})();
            </script>
        </head>
        <body>
            <p>Sending OTP to {email}...</p>
        </body>
    </html>
    """

    return html

if __name__ == "__main__":
    app.run(debug=True)