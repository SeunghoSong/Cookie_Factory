const express = require('express');
const http = require('http');
const path = require('path');
const WebSocket = require('ws');
const QRCode = require('qrcode');

const PORT = process.env.PORT || 8000;
const PUBLIC_URL = process.env.PUBLIC_URL || `http://localhost:${PORT}`;

// ★ C2 전처리 서버의 HTTP 엔드포인트 (어댑터 튜닝)
const PREPROCESSOR_URL = process.env.PREPROCESSOR_URL || 'http://c2-preprocessor:5001/preprocess';

const app = express();
app.use(express.json({ limit: '25mb' }));
app.use(express.static(path.join(__dirname, 'public')));

const server = http.createServer(app);

// ---- 모바일 클라이언트(카메라 스트리밍) 연결 목록 ----
const mobileClients = new Set();

// 🚀 C1 -> C2 송신 (Zero-Lag 비동기 래치 + E2E 락)
let latestFrame = null;
let isProcessing = false;
let unlockTimeout = null;

async function processPipelineWorker() {
  while (true) {
    if (latestFrame !== null && !isProcessing) {
      const frameToProcess = latestFrame;
      latestFrame = null;
      isProcessing = true; // 파이프라인 전체(C2->C3->C4) 락 걸기

      // 데드락 방지용 타임아웃 (1초 지나도 결과 안 오면 강제 해제)
      clearTimeout(unlockTimeout);
      unlockTimeout = setTimeout(() => {
        isProcessing = false;
      }, 1000);

      try {
        await fetch(PREPROCESSOR_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            image: frameToProcess.image,
            ts: frameToProcess.timestamp,
            socketId: 'ws_broadcast'
          }),
        });
        // 주의: 여기서 isProcessing을 풀지 않습니다! C4가 결과를 쏴줄 때(/stream-result) 풉니다.
      } catch (err) {
        console.error(`[C1] C2 Fetch Error: ${err.message}`);
        isProcessing = false; // 에러 났을 때만 여기서 락 풀기
      }
    }
    await new Promise((r) => setTimeout(r, 15));
  }
}
processPipelineWorker(); // 워커 실행


// ---- 모바일 클라이언트(웹소켓) 서버 ----
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

    // 항상 최신 프레임만 래치(덮어쓰기)
    latestFrame = {
      frame_id: frame.frame_id,
      timestamp: frame.timestamp,
      image: 'data:image/jpeg;base64,' + frame.image,
    };
  });

  ws.on('close', () => {
    mobileClients.delete(ws);
    console.log(`[C1] Mobile client disconnected (${mobileClients.size} active)`);
  });

  ws.on('error', (err) => {
    console.error(`[C1] Mobile socket error: ${err.message}`);
  });
});

function broadcastResult(payload) {
  const msg = JSON.stringify(payload);
  for (const client of mobileClients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(msg);
    }
  }
}

// ---- C4 Visualizer로부터 들어오는 검사 결과 수신 ----
app.post('/stream-result', (req, res) => {
  const data = req.body;

  // C4로부터 결과를 성공적으로 받았으므로, 다음 프레임을 보낼 수 있도록 파이프라인 락 해제!
  clearTimeout(unlockTimeout);
  isProcessing = false;

  let base64Img = data.rendered_image;
  if (base64Img && base64Img.includes(',')) {
    base64Img = base64Img.split(',')[1];
  }

  // 대표 불량품을 기준으로 circularity 추출 (객체가 여러개일 경우 ng_count 우선)
  let is_defective = data.ng_count > 0;
  let circularity = "N/A";
  if (data.objects && data.objects.length > 0) {
     circularity = data.objects[0].roundness; // 첫번째 객체의 원형도 표시
  }

  // 팀원 UI 규격에 맞게 상태 매핑
  let ui_status = 'PASS';
  if (data.total_obj === 0) ui_status = 'NO_OBJECT';
  else if (is_defective) ui_status = 'FAIL';

  broadcastResult({
    type: 'result',
    image: base64Img,
    status: ui_status,
    circularity: circularity,
    timestamp: Date.now()
  });

  res.json({ status: 'ok' });
});

// ---- URL 라우팅 (스마트폰 송신부 / PC 관제용 분리) ----
app.get('/mobile', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'mobile.html'));
});

app.get('/dashboard', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'dashboard.html'));
});

// QR 코드 발급 / 스마트폰 연결용 mobile 페이지로 안내 (동적 URL)
app.get('/qr', async (req, res) => {
  const host = req.get('host');
  const protocol = req.headers['x-forwarded-proto'] || req.protocol;
  const cameraUrl = `${protocol}://${host}/mobile`;
  
  const qrDataUrl = await QRCode.toDataURL(cameraUrl, { width: 320 });
  res.send(`
    <html>
      <body style="display:flex;flex-direction:column;align-items:center;font-family:sans-serif;background:#111;color:#eee;padding-top:40px;">
        <h2>이 스마트폰으로 스캔하여 카메라 렌즈로 쏘세요</h2>
        <img src="${qrDataUrl}" alt="QR code" style="border-radius:8px;" />
        <p style="margin-top:20px; color:#888; font-size:1.2em;">${cameraUrl}</p>
        <p style="margin-top:10px;"><a href="${cameraUrl}" style="color:#4ade80; text-decoration:none; font-size:1.2em; border: 1px solid #4ade80; padding:10px; border-radius:5px;">스마트폰이라면 여기를 눌러 바로 카메라로 진입하세요</a></p>
      </body>
    </html>
  `);
});

app.get('/', (req, res) => {
  res.send(`
    <html>
      <body style="background:#111;color:#eee;text-align:center;padding:50px;font-family:sans-serif;">
        <h1>🏭 스마트 팩토리 메인 센터</h1>
        <br>
        <a href="/dashboard" style="display:inline-block;padding:20px;background:#4ade80;color:#000;text-decoration:none;font-size:24px;border-radius:10px;font-weight:bold;margin:10px;">💻 PC 관제 대시보드 열기 (보기 전용)</a>
        <br><br>
        <a href="/qr" style="display:inline-block;padding:20px;background:#3b82f6;color:#fff;text-decoration:none;font-size:24px;border-radius:10px;font-weight:bold;margin:10px;">📱 스마트폰 카메라 연결 (QR/쏘기 전용)</a>
      </body>
    </html>
  `);
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 [C1 Gateway (Split Mode)] Running on port ${PORT}`);
});
