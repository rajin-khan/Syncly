const express = require('express');
const authRoutes = require('./auth');


const app = express();
app.use(authRoutes);

app.get('/', (req, res) => {
  res.send('<a href="http://localhost:5500/auth/google">Authenticate User</a>');
});

app.listen(5500, () => {
    console.log('Server running on http://localhost:5500');
});
