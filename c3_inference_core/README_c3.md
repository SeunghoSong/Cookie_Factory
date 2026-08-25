# C3 Inference Core

C2가 검출한 쿠키 후보의 컨투어를 분석해 원형도를 계산하고 OK/NG를 판정하는 코어 컨테이너.

> ℹ️ 초기 계획 문서(`doc/POC_PLAN.md`)에는 "SAM 2 제로샷 세그멘테이션"으로 되어 있지만, 실제로는 SAM 2를 쓰지 않고 **C2가 뽑은 컨투어로 기하학적 원형도를 계산**하는 방식으로 구현되어 있음. 코드/디렉터리명(`inspector.py`, `c3_inference_core`)은 유지되었으나 내부 알고리즘은 SAM 2 기반이 아님.

## 역할

1. C2로부터 후보 목록(`candidates`: bbox/lane/area/contour) 수신
2. 후보별 컨투어 중심점 대비 최소/최대 반지름 비율로 원형도 계산
3. 원형도 임계값 기준 OK/NG 판정 및 결함 유형 분류
4. 판정 결과를 C4(`VISUALIZER_URL`)로 전달

## 판정 로직 상세 (`analyze_defect_shape`)

1. bbox 중심점 `(cx, cy) = (x + w/2, y + h/2)` 계산
2. 컨투어의 각 외곽점에서 중심까지의 유클리드 거리 계산 → 최소(`r_min`)/최대(`r_max`) 반지름
3. 원형도 `c = r_min / r_max` (완전한 원이면 1.0에 가까움, 한쪽이 뜯기면 값이 작아짐)
4. 판정 기준:

| 원형도(c) 범위 | 판정 | 결함 유형 |
|---|---|---|
| `c ≥ 0.71` | OK | `ROUND` (정상 원형) |
| `0.65 ≤ c < 0.71` | NG | `BITE` (한쪽 파임) |
| `0.55 ≤ c < 0.65` | NG | `CUT` (단면 절단) |
| `0.40 ≤ c < 0.55` | NG | `WEDGE` (조각 결손) |
| `c < 0.40` | NG | `HALF` (반쪽 파손) |

컨투어가 비어 있으면 `{"status": "OK", "roundness": 1.0, "defect_type": "ROUND"}`로 안전 처리.

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 헬스 체크 |
| POST | `/infer` | C2로부터 후보 수신 → 원형도 분석 → C4로 전달 |

## 메시지 스키마

### C2 → C3 (`POST /infer`)

```json
{
  "image": "<Base64 JPEG>",
  "candidates": [
    { "bbox": [120, 85, 80, 90], "lane": "LINE 01", "area": 4523.0, "contour": [[[120,85]], "..."] }
  ],
  "ts": 1732500000000,
  "frame_id": "1732500000000-42",
  "prep_latency_ms": 12.3,
  "socketId": ""
}
```

`image`, `candidates`, `ts`는 필수 (Pydantic `InferenceInput` 모델). `frame_id`/`prep_latency_ms`/`socketId`는 선택값.

### C3 → C4 (`POST`, `VISUALIZER_URL`)

```json
{
  "image": "<Base64 JPEG, 원본 그대로>",
  "objects": [
    {
      "bbox": [120, 85, 80, 90],
      "lane": "LINE 01",
      "area": 4523.0,
      "contour": [[[120,85]], "..."],
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

- `bbox`는 C2와 동일하게 `[x, y, width, height]` 포맷 그대로 전달 (변환 없음)
- C4는 `bbox`/`status`/`roundness`/`contour`만 사용하고 `lane`/`area`/`defect_type`/`total_obj`/`ng_count`/지연시간 필드는 현재 무시함

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `VISUALIZER_URL` | `http://localhost:5003/visualize` | C4로 판정 결과를 전달할 HTTP POST 주소 |

포트/네트워크 등 도커 관련 설정은 루트 `README.md` 및 `docker-compose.yml` 참고 (컨테이너 포트: `5002`).

## 로컬 실행

```bash
cd c3_inference_core
pip install -r requirements.txt
VISUALIZER_URL=http://localhost:5003/visualize python inspector.py
```

## 알려진 제약

- 원형도 임계값(`0.71`)과 결함 유형 구간은 하드코딩되어 있음. POC_PLAN §6-2의 "임계값 사전 캘리브레이션" 계획대로 실제 샘플로 조정이 필요할 수 있음
- 컨투어 포인트가 적거나(예: 아주 작은 후보) 왜곡된 경우 원형도 계산이 부정확할 수 있음 — 별도 최소 포인트 수 검증 없음
- C4 호출은 단발 POST이며 실패해도 별도 재시도가 없음(예외는 잡아서 `{"status":"error"}`로만 응답)
