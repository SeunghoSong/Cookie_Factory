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

```json
{
  "frame_id": "선택값 — 없으면 C4가 임시로 생성함",
  "timestamp": 1732500000000,
  "image": "<Base64 JPEG, 원본 프레임>",
  "objects": [
    {
      "bbox": [120, 85, 200, 200],
      "status": "NG",
      "roundness": 0.60,
      "contour": [[120, 85], [130, 90], "..."]
    }
  ]
}
```

- `status`가 `"NG"`(대소문자 무관, `FAIL`/`DEFECTIVE`도 동일 취급)면 빨간색, 그 외는 초록색으로 마킹
- `objects`가 비어 있으면 결과 상태를 `NO_OBJECT`로 처리
- `objects`가 여러 개면 그중 불량(NG) 객체를 대표(primary)로 선택해 C1에 전달할 단일 `circularity`/`bbox`/`mask_polygon` 값을 구성 (없으면 첫 번째 객체)

> ⚠️ **확인 필요**: 현재 C3 협의 스키마에는 `frame_id`가 포함되어 있지 않습니다. C4는 없으면 임시 ID(`c4-xxxxx`)를 생성해 파이프라인이 끊기지 않게 처리하지만, 모바일 화면과 원본 프레임을 정확히 매칭하려면 C3가 `frame_id`(및 가능하면 `timestamp`)를 그대로 전달해야 합니다. C3 담당자와 확정할 것.

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

- `frame_id` 누락 시 C4가 생성한 임시 ID를 사용하므로, 여러 프레임이 동시에 처리되는 경우 모바일 화면과 원본 요청 간 매칭이 부정확할 수 있음 (C3 협의 필요, 위 참고)
- C1으로의 전송은 단발 POST이며 재시도 큐가 없음. C1이 다운된 경우 결과는 로그만 남고 유실됨
- 디버그 아카이브(`/app/output_json`, `/app/captures`)는 POC 편의 기능이며 용량 관리(rotation) 로직 없음
