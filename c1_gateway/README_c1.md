# C1 Gateway

모바일 카메라 스트리밍 수신과 최종 판정 결과 표출을 담당하는 게이트웨이 컨테이너.
**카메라 페이지(`/mobile`)와 결과 확인용 대시보드(`/dashboard`)는 서로 분리된 별도 화면이다.**

## 역할

1. QR 코드 발급 → 모바일 브라우저 접속 유도 (Zero-Install)
2. 모바일 브라우저(`/mobile`)에서 카메라 프레임을 받아 C2(Preprocessing)로 릴레이
3. 카메라 연결/종료 상태를 대시보드(`/dashboard`)에 실시간 통지
4. C4(Visualizer)가 보내는 마킹된 결과 프레임을 대시보드 화면에 실시간 표출
5. 모바일 페이지 자체는 카메라 종료/연결 끊김 시 "NO SIG" 표시 (자기 자신의 스트리밍 상태만 표시)

## 화면 구성

| 페이지 | 경로 | 용도 |
|---|---|---|
| 카메라 페이지 | `/mobile` | 스마트폰에서 QR로 접속, 카메라 캡처 후 프레임 전송만 담당. 결과 화면은 표시하지 않음 |
| 대시보드 | `/dashboard` | PC/모니터에서 열어두는 화면. 카메라 연결 상태 배지 + C4가 마킹한 최신 프레임 + 최근 판정 이력을 실시간으로 표시 |

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 헬스 체크 + 두 화면으로의 링크 |
| GET | `/qr` | 모바일 접속용 QR 코드 페이지 |
| GET | `/mobile` | 카메라 스트리밍 페이지 (`public/mobile.html`) |
| GET | `/dashboard` | 판정 결과 확인 대시보드 (`public/dashboard.html`) |
| WS | `/ws/stream` | 모바일 → C1: 카메라 프레임 업로드 전용 |
| WS | `/ws/dashboard` | C1 → 대시보드: 카메라 상태·판정 결과 브로드캐스트 전용 |
| POST | `/stream-result` | C4로부터 판정·마킹 결과 수신 |

> ⚠️ 구현 메모: `ws` 라이브러리는 같은 HTTP 서버에 `{ server, path }` 옵션으로 `WebSocketServer`를 두 개 이상 붙이면 서로의 upgrade 요청을 가로채 400으로 끊어버리는 문제가 있음. 그래서 두 WS 서버 모두 `noServer: true`로 만들고, `server.on('upgrade', ...)`에서 경로를 보고 직접 `handleUpgrade`로 분기하는 방식을 사용함 (`server.js` 하단 참고).

## 메시지 스키마

### 모바일 → C1 (`/ws/stream`, WebSocket, JSON)

```json
{
  "type": "frame",
  "frame_id": "1732500000000-42",
  "timestamp": 1732500000000,
  "image": "<Base64 JPEG>"
}
```

### C1 → C2 (`POST`, `PREPROCESSOR_URL`)

C2의 실제 `FrameInput` 스키마(`image`, `ts` 필수)에 맞춰 필드명을 변환해서 전달 (`timestamp` → `ts`). `frame_id`도 함께 보내며, C2/C3를 거쳐 C4까지 그대로 전달됨(2026-08-25 통합 테스트로 종단 간 확인):

```json
{ "image": "<Base64 JPEG>", "ts": 1732500000000, "frame_id": "1732500000000-42" }
```

### C4 → C1 (`POST /stream-result`)

```json
{
  "frame_id": "1732500000000-42",
  "timestamp": 1732500000000,
  "image": "<Base64 JPEG, 마킹된 프레임>",
  "status": "OK | FAIL | NO_OBJECT",
  "is_defective": true,
  "circularity": 0.62,
  "bbox": [x_min, y_min, x_max, y_max],
  "mask_polygon": [[x, y], ...]
}
```

### C1 → 대시보드 (`/ws/dashboard`, 브로드캐스트)

카메라 연결 상태 (모바일 접속/해제 시, 그리고 대시보드 접속 직후 현재 상태 1회 전송):

```json
{ "type": "camera_status", "connected": true }
```

판정 결과 (C4로부터 수신 즉시 전달):

```json
{ "type": "result", "frame_id": "...", "image": "...", "status": "FAIL", "is_defective": true, "circularity": 0.62, "bbox": [...], "mask_polygon": [...] }
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `8000` | HTTP/WS 리스닝 포트 |
| `PUBLIC_URL` | `http://localhost:8000` | QR 코드에 인코딩할 외부 접속 주소 (ngrok HTTPS 주소로 교체 필요) |
| `PREPROCESSOR_URL` | `http://c2-preprocessor:5001/preprocess` | C2로 프레임을 릴레이할 HTTP POST 주소 |

## 로컬 실행

```bash
cd c1_gateway
npm install
PORT=8000 PUBLIC_URL=http://localhost:8000 npm start
```

- 스마트폰: `http://localhost:8000/qr` 접속 → QR 스캔 (또는 같은 네트워크의 모바일에서 `/mobile` 직접 접속)
- 확인용 PC/모니터: `http://localhost:8000/dashboard` 접속

> 카메라 권한은 HTTPS(또는 `localhost`) 컨텍스트에서만 허용됨. 실기기 테스트 시 ngrok으로 HTTPS 터널을 열고 `PUBLIC_URL`을 해당 주소로 설정할 것.

## 알려진 제약

- 현재 버전은 단일 모바일 스트림을 전제로 하며(POC 스코프), 대시보드를 여러 개 띄워도 모두 동일한 결과를 받음.
- C2로의 HTTP POST가 실패(다운/타임아웃)한 프레임은 버려지며, 모바일 클라이언트에는 `status` 메시지로만 통지됨(재시도/큐잉 없음).
- 카메라 연결 상태(`camera_status`)는 "모바일 WS 소켓이 열려 있는지"만 판단 기준으로 삼음. 실제 `getUserMedia` 권한 거부나 트랙 종료 등 모바일 페이지 내부 사정은 대시보드에 반영되지 않음(모바일 페이지 자체의 "NO SIG" 표시로만 확인 가능).
