# C1 Gateway

모바일 카메라 스트리밍 수신 및 최종 판정 결과 표출을 담당하는 게이트웨이 컨테이너.

## 역할

1. QR 코드 발급 → 모바일 브라우저 접속 유도 (Zero-Install)
2. 모바일 브라우저에서 카메라 프레임을 받아 C2(Preprocessing)로 릴레이
3. C4(Visualizer)가 보내는 마킹된 결과 프레임을 모바일 화면에 실시간 표출
4. 카메라/연결 종료 시 모바일 화면에 "NO SIG" 표시

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 헬스 체크 |
| GET | `/qr` | 모바일 접속용 QR 코드 페이지 |
| GET | `/mobile` | 모바일 카메라 스트리밍 페이지 (`public/mobile.html`) |
| WS | `/ws/stream` | 모바일 ↔ C1 실시간 채널 (프레임 업로드 / 결과 다운로드) |
| POST | `/stream-result` | C4로부터 판정·마킹 결과 수신 |

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

### C1 → C2 (아웃바운드 WebSocket, `PREPROCESSOR_WS_URL`)

프레임을 그대로 릴레이:

```json
{ "frame_id": "...", "timestamp": 1732500000000, "image": "<Base64 JPEG>" }
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

### C1 → 모바일 (`/ws/stream`, 결과 브로드캐스트)

```json
{ "type": "result", "frame_id": "...", "image": "...", "status": "FAIL", "is_defective": true, "circularity": 0.62 }
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `8000` | HTTP/WS 리스닝 포트 |
| `PUBLIC_URL` | `http://localhost:8000` | QR 코드에 인코딩할 외부 접속 주소 (ngrok HTTPS 주소로 교체 필요) |
| `PREPROCESSOR_WS_URL` | `ws://c2-preprocessor:5001/ws/preprocess` | C2로 프레임을 릴레이할 WebSocket 주소 |

## 로컬 실행

```bash
cd c1_gateway
npm install
PORT=8000 PUBLIC_URL=http://localhost:8000 npm start
```

브라우저에서 `http://localhost:8000/qr` 접속 → QR 스캔 (또는 같은 네트워크의 모바일에서 `/mobile` 직접 접속).

> 카메라 권한은 HTTPS(또는 `localhost`) 컨텍스트에서만 허용됨. 실기기 테스트 시 ngrok으로 HTTPS 터널을 열고 `PUBLIC_URL`을 해당 주소로 설정할 것.

## 알려진 제약

- 현재 버전은 단일 모바일 스트림을 전제로 하며(POC 스코프), 다중 클라이언트 접속 시 모든 클라이언트에게 결과가 동일하게 브로드캐스트됨.
- C2 연결이 끊긴 동안 수신한 프레임은 버려지며, 모바일 클라이언트에는 `status` 메시지로만 통지됨(재전송 큐 없음).
