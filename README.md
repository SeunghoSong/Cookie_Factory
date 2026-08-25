# 🍪 과자 불량 검출 시스템 (4단계 마이크로서비스)

## 📌 파이프라인 아키텍처
1. **C1 Gateway (포트 8000)**: 스마트폰 스트리밍 수신 및 최종 결과 표출 라우팅
2. **C2 Preprocessor (포트 5001)**: 영상 프레임 전처리 및 과자 영역 분할
3. **C3 SAM 2 Inference (포트 5002)**: SAM 2 마스크 추출 및 원형도 불량 판정
4. **C4 Visualizer (포트 5003)**: BBox/마스크 오버레이 렌더링 & C1 역전송

## 🚀 실행 방법
```bash
docker compose up --build
```

## 컨테이너별 안내

| 컨테이너 | 설명 | 사용 방법 | 상세 문서 |
|---|---|---|---|
| C1 Gateway | QR 스캔으로 모바일 브라우저에서 카메라 스트리밍을 시작하고, 최종 판정 결과를 실시간으로 화면에 표출 | `docker compose up` 후 `http://localhost:8000/qr` 접속 → QR 스캔 (실기기는 ngrok HTTPS 필요) | [c1_gateway/README.md](./c1_gateway/README.md) |
| C2 Preprocessor | 수신 프레임 전처리 및 SAM 2용 box prompt 자동 생성 | C1이 WebSocket으로 자동 연결, 별도 조작 불필요 | (작성 예정) |
| C3 SAM 2 Inference | 제로샷 세그멘테이션 및 원형도 기반 Pass/Fail 판정 | C2가 자동 호출, 별도 조작 불필요 | (작성 예정) |
| C4 Visualizer | 판정 결과를 원본 프레임에 오버레이 후 C1로 역전송 | C3가 자동 호출, 별도 조작 불필요 | (작성 예정) |
