# C2 Preprocessor

C1이 릴레이한 원본 프레임에서 HSV 색상 기반으로 쿠키 후보를 검출하고, 3개 컨베이어 라인별 bbox·컨투어를 뽑아 C3로 전달하는 전처리 컨테이너.

> ℹ️ 초기 계획 문서(`doc/POC_PLAN.md`)의 "SAM 2용 box prompt 생성"과 달리, 실제로는 SAM 2를 쓰지 않고 **HSV 색상 마스킹 + 컨투어 검출**로 후보를 뽑는 방식으로 구현되어 있음.

## 역할

1. C1으로부터 원본 프레임(Base64 JPEG) 수신
2. 가우시안 블러 → HSV 변환 → CLAHE(명암 보정) → 색상 마스킹 → 모폴로지 닫힘 연산으로 노이즈 제거
3. 컨투어 검출 후 면적/종횡비 필터링으로 쿠키 후보만 추림
4. Y좌표 기준으로 3개 컨베이어 라인(`LINE 01~03`) 중 어디에 속하는지 판정
5. 후보별 `bbox`/`area`/`contour`를 C3(`INFERENCE_URL`)로 전달

## 검출 로직 상세 (`extract_cookie_candidates`)

| 단계 | 내용 |
|---|---|
| 블러 | `cv2.GaussianBlur(frame, (5,5), 0)` — 모니터 촬영 시 모아레 패턴/노이즈 제거 |
| 색상 마스크 | HSV Hue 8~38, Sat 50~255, Val 50~255 (쿠키의 황토/주황색 범위) |
| 조명 보정 | V 채널에 CLAHE(`clipLimit=2.0`) 적용 후 마스킹 |
| 노이즈 제거 | `cv2.MORPH_CLOSE` (9x9 타원 커널)로 초코칩 등 내부 구멍 메움 |
| 후보 필터 | 면적 1000~40000px, 종횡비 0.4~2.5 (너무 작거나 길쭉한 형태 제외) |
| 라인 판정 | `lane_idx = y / (프레임 높이/3) + 1` → `LINE 01/02/03` |

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 헬스 체크 |
| POST | `/preprocess` | C1으로부터 프레임 수신 → 후보 검출 → C3로 전달 |

## 메시지 스키마

### C1 → C2 (`POST /preprocess`)

```json
{ "image": "<Base64 JPEG>", "ts": 1732500000000, "frame_id": "1732500000000-42", "socketId": "" }
```

- `image`, `ts`는 필수 (Pydantic `FrameInput` 모델). 없으면 422 에러
- `frame_id`, `socketId`는 선택값(기본 `""`)이며, 없어도 에러 없이 처리됨

### C2 → C3 (`POST`, `INFERENCE_URL`)

```json
{
  "image": "<Base64 JPEG, 원본 그대로>",
  "candidates": [
    { "bbox": [120, 85, 80, 90], "lane": "LINE 01", "area": 4523.0, "contour": [[[120,85]], "..."] }
  ],
  "ts": 1732500000000,
  "frame_id": "1732500000000-42",
  "prep_latency_ms": 12.3,
  "socketId": ""
}
```

- `bbox`는 `cv2.boundingRect()` 기준 **`[x, y, width, height]`** (좌상단 + 너비/높이, `[x1,y1,x2,y2]` 아님)
- `contour`는 OpenCV 컨투어를 `.tolist()`한 것이라 `[[[x,y]], [[x,y]], ...]` 형태로 한 겹 더 감싸져 있음

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `INFERENCE_URL` | `http://localhost:5002/infer` | C3로 후보 데이터를 전달할 HTTP POST 주소 |

포트/네트워크 등 도커 관련 설정은 루트 `README.md` 및 `docker-compose.yml` 참고 (컨테이너 포트: `5001`).

## 로컬 실행

```bash
cd c2_preprocessor
pip install -r requirements.txt
INFERENCE_URL=http://localhost:5002/infer python preprocessor.py
```

## 알려진 제약

- 색상 기반 검출이라 조명/배경 대비가 부족하면 후보가 아예 안 잡힐 수 있음 (POC_PLAN §6-2 리스크와 동일한 맥락)
- 한 프레임에서 여러 후보(다중 라인 동시 검출)가 나올 수 있는데, C4는 그중 하나만 대표로 골라 C1에 전달하므로 다중 라인을 동시에 대시보드에 표시하려면 C1/C4/대시보드 쪽 확장이 필요
- C3 호출은 단발 POST이며 실패해도 별도 재시도가 없음(예외는 잡아서 `{"status":"error"}`로만 응답)
