const express = require('express');
const authRoutes = require('./auth');

const app = express();

app.use('/', authRoutes);

app.listen(5500, () => {
    console.log('Server running on http://localhost:5500');
});