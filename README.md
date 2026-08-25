# 🍪 과자 불량 검출 시스템 (4단계 마이크로서비스)

## 📌 파이프라인 아키텍처
1. **C1 Gateway (포트 8000)**: 스마트폰 스트리밍 수신 및 최종 결과 표출 라우팅
2. **C2 Preprocessor (포트 5001)**: HSV 색상 기반 쿠키 후보 검출(3라인 컨베이어) 및 bbox/컨투어 추출
3. **C3 Inference Core (포트 5002)**: 컨투어 기반 원형도(r_min/r_max) 계산 및 OK/NG 판정
4. **C4 Visualizer (포트 5003)**: BBox/마스크 오버레이 렌더링 & C1 역전송

> ℹ️ C2/C3는 초기 계획(SAM 2 제로샷 세그멘테이션)과 달리, 실제로는 **HSV 색상 검출 + 기하학적 원형도 계산** 방식으로 구현되어 있음(SAM 2 미사용). `doc/POC_PLAN.md`는 초기 설계 문서이며 최신 구현과 다를 수 있음.

## 🚀 실행 방법
```bash
docker compose up --build
```

## 컨테이너별 안내

| 컨테이너 | 설명 | 사용 방법 | 상세 문서 |
|---|---|---|---|
| C1 Gateway | QR 스캔으로 모바일에서 카메라 스트리밍 시작(`/mobile`), 판정 결과는 별도 대시보드(`/dashboard`)에서 실시간 확인 | `docker compose up` 후 스마트폰은 `http://localhost:8000/qr` 스캔, 확인용 PC는 `http://localhost:8000/dashboard` 접속 (실기기는 ngrok HTTPS 필요) | [c1_gateway/README_c1.md](./c1_gateway/README_c1.md) |
| C2 Preprocessor | 프레임에서 HSV 색상 마스킹(황토색)으로 쿠키 후보를 검출하고, 3개 컨베이어 라인(`LINE 01~03`)별 bbox·컨투어를 뽑아 C3로 전달 | C1이 HTTP POST(`/preprocess`)로 자동 호출, 별도 조작 불필요. 헬스체크: `http://localhost:5001/` | [c2_preprocessor/README_c2.md](./c2_preprocessor/README_c2.md) |
| C3 Inference Core | 후보 컨투어의 원형도(`c = r_min/r_max`)를 계산해 `c < 0.71`이면 NG 판정, 결손 정도에 따라 `HALF/WEDGE/CUT/BITE`로 결함 유형 분류 | C2가 HTTP POST(`/infer`)로 자동 호출, 별도 조작 불필요. 헬스체크: `http://localhost:5002/` | [c3_inference_core/README_c3.md](./c3_inference_core/README_c3.md) |
| C4 Visualizer | 판정 결과를 원본 프레임에 박스/컨투어로 오버레이하고 C1로 역전송 | C3가 자동 호출, 별도 조작 불필요 | [c4_visualizer/README_c4.md](./c4_visualizer/README_c4.md) |
