# C4 Visualizer

C3의 판정 결과를 원본 프레임 위에 시각적으로 마킹하고, 완성된 프레임을 C1로 역전송하는 컨테이너.

## 역할

1. C3 판정 결과(`bbox`/`contour`/`status`/`roundness`) 수신
2. 원본 프레임에 불량 영역 오버레이 (박스 + 컨투어 + 라벨 텍스트, 상태에 따라 색상 구분)
3. 마킹된 프레임을 C1(`GATEWAY_URL`)로 HTTP POST 전송
4. (부가) 마킹 결과를 `/app/output_json`, `/app/captures`에 로컬 파일로 저장 (디버깅/데모용, DB 아님)

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 헬스 체크 |
| POST | `/visualize` | C3로부터 판정 결과 수신 → 마킹 → C1로 전달 |

## 메시지 스키마

### C3 → C4 (`POST /visualize`)

실제 C3(`inspector.py`) 구현 기준 스키마:

```json
{
  "image": "<Base64 JPEG, 원본 프레임>",
  "objects": [
    {
      "bbox": [120, 85, 80, 90],
      "lane": "LINE 01",
      "area": 4523.0,
      "contour": [[120, 85], [130, 90], "..."],
      "status": "NG",
      "roundness": 0.60,
      "defect_type": "WEDGE"
    }
  ],
  "total_obj": 1,
  "ng_count": 1,
  "ts": 1732500000000,
  "frame_id": "1732500000000-42",
  "prep_latency_ms": 12.3,
  "infer_latency_ms": 4.1,
  "socketId": ""
}
```

- **`bbox`는 `[x, y, width, height]`** 형식 (OpenCV `cv2.boundingRect()` 기준, `[x1,y1,x2,y2]` 아님). C4가 내부적으로 `x2 = x+w, y2 = y+h`로 변환해서 그림
- 시각 그리기·판정에 실제로 쓰는 필드는 `bbox`/`status`/`roundness`/`contour`뿐이고, `lane`/`area`/`defect_type`/`total_obj`/`ng_count`/`prep_latency_ms`/`infer_latency_ms`/`socketId`는 현재 C4가 사용하지 않고 무시함 (필요 시 대시보드 표시용으로 확장 가능)
- 타임스탬프 키는 `timestamp`가 아니라 **`ts`** (C4가 `ts` 우선, 없으면 `timestamp` 순으로 찾음)
- `status`가 `"NG"`(대소문자 무관, `FAIL`/`DEFECTIVE`도 동일 취급)면 빨간색, 그 외는 초록색으로 마킹
- `objects`가 비어 있으면 결과 상태를 `NO_OBJECT`로 처리
- `objects`가 여러 개면 그중 불량(NG) 객체를 대표(primary)로 선택해 C1에 전달할 단일 `circularity`/`bbox`/`mask_polygon` 값을 구성 (없으면 첫 번째 객체)
- `frame_id`는 C1→C2→C3→C4 전 구간에 걸쳐 실제로 전달되도록 확인·연결 완료 (2026-08-25 통합 테스트로 검증). 없을 경우에만 C4가 임시 ID(`c4-xxxxx`)를 생성함

### C4 → C1 (`POST /stream-result`, `GATEWAY_URL` 환경변수)

```json
{
  "frame_id": "...",
  "timestamp": 1732500000000,
  "image": "<Base64 JPEG, 마킹된 프레임>",
  "status": "OK | FAIL | NO_OBJECT",
  "is_defective": true,
  "circularity": 0.60,
  "bbox": [120, 85, 200, 200],
  "mask_polygon": [[120, 85], "..."]
}
```

C1(`c1_gateway`)이 이 스키마를 그대로 파싱해 모바일 화면에 브로드캐스트하므로 필드명을 변경하지 말 것.

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `GATEWAY_URL` | `http://c1-gateway:8000/stream-result` | 마킹 결과를 전송할 C1 엔드포인트 |

포트/네트워크 등 도커 관련 설정은 루트 `README.md` 및 `docker-compose.yml` 참고.

## 로컬 실행

```bash
cd c4_visualizer
pip install -r requirements.txt
GATEWAY_URL=http://localhost:8000/stream-result python visualizer.py
```

## 알려진 제약

- C1으로의 전송은 단발 POST이며 재시도 큐가 없음. C1이 다운된 경우 결과는 로그만 남고 유실됨
- 디버그 아카이브(`/app/output_json`, `/app/captures`)는 POC 편의 기능이며 용량 관리(rotation) 로직 없음
- `objects`에 여러 후보가 동시에 검출되는 경우(3라인 컨베이어 동시 검출 등) C4는 그중 하나만 대표로 골라 C1에 단일 판정을 전달함 — 여러 라인을 동시에 대시보드에 표시하려면 C1/대시보드 쪽에 다중 객체 지원 추가 필요
