const express = require('express');
const app = express();
const PORT = process.env.PORT || 8000;

app.use(express.json());

app.get('/', (req, res) => {
  res.send('<h1>[C1 Gateway] Ready for Stream Routing</h1>');
});

app.listen(PORT, () => {
  console.log(`[C1 Gateway] Running on port ${PORT}`);
});
