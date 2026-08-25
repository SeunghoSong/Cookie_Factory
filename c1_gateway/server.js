const express = require('express');
const http = require('http');
const path = require('path');
const WebSocket = require('ws');
const QRCode = require('qrcode');

const PORT = process.env.PORT || 8000;
// ngrok 등으로 외부에 노출된 주소. 미설정 시 로컬 접속 주소로 대체.
const PUBLIC_URL = process.env.PUBLIC_URL || `http://localhost:${PORT}`;
const PREPROCESSOR_WS_URL = process.env.PREPROCESSOR_WS_URL || 'ws://c2-preprocessor:5001/ws/preprocess';
const C2_RECONNECT_DELAY_MS = 3000;

const app = express();
app.use(express.json({ limit: '10mb' }));
app.use(express.static(path.join(__dirname, 'public')));

const server = http.createServer(app);

// ---- 모바일 클라이언트(카메라 송출/결과 수신) 연결 목록 ----
const mobileClients = new Set();

// ---- C2 Preprocessor로 프레임을 릴레이하는 아웃바운드 WebSocket ----
let c2Socket = null;
let c2Connected = false;

function connectToC2() {
  const socket = new WebSocket(PREPROCESSOR_WS_URL);

  socket.on('open', () => {
    c2Connected = true;
    console.log(`[C1] Connected to C2 preprocessor (${PREPROCESSOR_WS_URL})`);
  });

  socket.on('close', () => {
    c2Connected = false;
    console.warn('[C1] C2 connection closed. Retrying in 3s...');
    setTimeout(connectToC2, C2_RECONNECT_DELAY_MS);
  });

  socket.on('error', (err) => {
    console.error(`[C1] C2 connection error: ${err.message}`);
  });

  c2Socket = socket;
}
connectToC2();

function relayFrameToC2(frame) {
  if (!c2Connected || !c2Socket || c2Socket.readyState !== WebSocket.OPEN) {
    return false;
  }
  c2Socket.send(JSON.stringify(frame));
  return true;
}

// ---- 모바일 클라이언트용 WebSocket 서버 (프레임 수신 / 결과 송신) ----
const wss = new WebSocket.Server({ server, path: '/ws/stream' });

wss.on('connection', (ws) => {
  mobileClients.add(ws);
  console.log(`[C1] Mobile client connected (${mobileClients.size} active)`);

  ws.on('message', (raw) => {
    let frame;
    try {
      frame = JSON.parse(raw);
    } catch {
      return;
    }
    if (frame.type !== 'frame') return;

    const relayed = relayFrameToC2({
      frame_id: frame.frame_id,
      timestamp: frame.timestamp,
      image: frame.image,
    });

    if (!relayed) {
      ws.send(JSON.stringify({ type: 'status', message: 'C2 preprocessor unavailable' }));
    }
  });

  ws.on('close', () => {
    mobileClients.delete(ws);
    console.log(`[C1] Mobile client disconnected (${mobileClients.size} active)`);
  });

  ws.on('error', (err) => {
    console.error(`[C1] Mobile socket error: ${err.message}`);
  });
});

function broadcastResult(result) {
  const payload = JSON.stringify({ type: 'result', ...result });
  for (const client of mobileClients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(payload);
    }
  }
}

// ---- C4 Visualizer로부터 판정/마킹 결과 수신 (§2 인터페이스 4) ----
app.post('/stream-result', (req, res) => {
  const { frame_id, timestamp, image, status, is_defective, circularity, bbox, mask_polygon } = req.body;

  if (!frame_id) {
    return res.status(400).json({ status: 'error', message: 'frame_id is required' });
  }

  broadcastResult({ frame_id, timestamp, image, status, is_defective, circularity, bbox, mask_polygon });
  res.json({ status: 'ok' });
});

// ---- QR 코드 발급 / 모바일 접속 페이지 ----
app.get('/qr', async (req, res) => {
  const mobileUrl = `${PUBLIC_URL}/mobile`;
  const qrDataUrl = await QRCode.toDataURL(mobileUrl, { width: 320 });
  res.send(`
    <html>
      <body style="display:flex;flex-direction:column;align-items:center;font-family:sans-serif;background:#111;color:#eee;padding-top:40px;">
        <h2>📱 스마트폰으로 QR을 스캔하세요</h2>
        <img src="${qrDataUrl}" alt="QR code" style="border-radius:8px;" />
        <p>${mobileUrl}</p>
      </body>
    </html>
  `);
});

app.get('/mobile', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'mobile.html'));
});

app.get('/', (req, res) => {
  res.send('<h1>[C1 Gateway] Ready for Stream Routing</h1><p><a href="/qr">QR 코드 보기</a></p>');
});

server.listen(PORT, () => {
  console.log(`[C1 Gateway] Running on port ${PORT}`);
});
