const express = require('express');
const authRoutes = require('./auth');


const app = express();
app.use(authRoutes);

app.get('/', (req, res) => {
  res.send('Welcome to the Express server!');
});

app.listen(5500, () => {
    console.log('Server running on http://localhost:5500');
    console.log('Authenticate using the following link: http://localhost:5500/auth/google');
});
