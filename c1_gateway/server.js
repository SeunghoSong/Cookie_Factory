const express = require('express');
const http = require('http');
const path = require('path');
const WebSocket = require('ws');
const QRCode = require('qrcode');

const PORT = process.env.PORT || 8000;
// ngrok 등으로 외부에 노출된 주소. 미설정 시 로컬 접속 주소로 대체.
const PUBLIC_URL = process.env.PUBLIC_URL || `http://localhost:${PORT}`;
const PREPROCESSOR_URL = process.env.PREPROCESSOR_URL || 'http://c2-preprocessor:5001/preprocess';

const app = express();
app.use(express.json({ limit: '10mb' }));
app.use(express.static(path.join(__dirname, 'public')));

const server = http.createServer(app);

// ---- 모바일 클라이언트(카메라 송출 전용) 연결 목록 ----
const mobileClients = new Set();
// ---- 대시보드 클라이언트(마킹 결과 확인 전용) 연결 목록 ----
const dashboardClients = new Set();
let cameraConnected = false;

// ---- C2 Preprocessor로 프레임을 릴레이 (HTTP POST) ----
async function relayFrameToC2(frame) {
  try {
    const res = await fetch(PREPROCESSOR_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(frame),
    });
    return res.ok;
  } catch (err) {
    console.error(`[C1] Failed to relay frame to C2: ${err.message}`);
    return false;
  }
}

// ---- 모바일 클라이언트용 WebSocket 서버 (카메라 프레임 업로드 전용) ----
// 두 개의 WebSocket.Server를 { server, path } 옵션으로 동시에 붙이면 ws 라이브러리가
// 서로의 upgrade 요청을 가로채 400으로 끊어버리는 충돌이 있어, noServer + 수동 라우팅 방식 사용.
const wss = new WebSocket.Server({ noServer: true });

function setCameraConnected(connected) {
  cameraConnected = connected;
  broadcastToDashboards({ type: 'camera_status', connected });
}

wss.on('connection', (ws) => {
  mobileClients.add(ws);
  console.log(`[C1] Mobile client connected (${mobileClients.size} active)`);
  setCameraConnected(true);

  ws.on('message', async (raw) => {
    let frame;
    try {
      frame = JSON.parse(raw);
    } catch {
      return;
    }
    if (frame.type !== 'frame') return;

    const relayed = await relayFrameToC2({
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
    if (mobileClients.size === 0) setCameraConnected(false);
  });

  ws.on('error', (err) => {
    console.error(`[C1] Mobile socket error: ${err.message}`);
  });
});

// ---- 대시보드 클라이언트용 WebSocket 서버 (마킹 결과 확인 전용) ----
const wssDashboard = new WebSocket.Server({ noServer: true });

wssDashboard.on('connection', (ws) => {
  dashboardClients.add(ws);
  console.log(`[C1] Dashboard client connected (${dashboardClients.size} active)`);
  ws.send(JSON.stringify({ type: 'camera_status', connected: cameraConnected }));

  ws.on('close', () => {
    dashboardClients.delete(ws);
    console.log(`[C1] Dashboard client disconnected (${dashboardClients.size} active)`);
  });

  ws.on('error', (err) => {
    console.error(`[C1] Dashboard socket error: ${err.message}`);
  });
});

function broadcastToDashboards(payload) {
  const message = JSON.stringify(payload);
  for (const client of dashboardClients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  }
}

function broadcastResult(result) {
  broadcastToDashboards({ type: 'result', ...result });
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

app.get('/dashboard', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'dashboard.html'));
});

app.get('/', (req, res) => {
  res.send(`
    <h1>[C1 Gateway] Ready for Stream Routing</h1>
    <p><a href="/qr">📱 QR 코드 보기 (카메라 접속)</a></p>
    <p><a href="/dashboard">🖥️ 대시보드 (마킹 결과 확인)</a></p>
  `);
});

// ---- 경로별 WebSocket upgrade 수동 라우팅 ----
server.on('upgrade', (req, socket, head) => {
  const { pathname } = new URL(req.url, `http://${req.headers.host}`);

  if (pathname === '/ws/stream') {
    wss.handleUpgrade(req, socket, head, (ws) => wss.emit('connection', ws, req));
  } else if (pathname === '/ws/dashboard') {
    wssDashboard.handleUpgrade(req, socket, head, (ws) => wssDashboard.emit('connection', ws, req));
  } else {
    socket.destroy();
  }
});

server.listen(PORT, () => {
  console.log(`[C1 Gateway] Running on port ${PORT}`);
});
