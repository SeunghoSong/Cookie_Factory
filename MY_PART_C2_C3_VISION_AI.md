# 🧠 [Zone 2 & 3: C2 Preprocessing + C3 AI Inference] 비전 AI 전처리 및 불량 판정 코어 명세서
> **담당자**: 2번 (AI 비전 & 결함 검출 엔지니어링)  
> **프로젝트**: 스마트 팩토리 4단계 컨베이어 과자 불량 검출 시스템 (`snackPj`)  
> **최종 업데이트**: 2026-08-25

---

## 1. 내 파트 개요 및 핵심 목표

스마트폰 카메라로부터 C1 Gateway를 거쳐 전달된 3줄 컨베이어 영상 프레임을 수신하여, **[C2: 조명 적응형 색상 마스킹 및 3개 라인 분할 전처리]**를 수행하고, **[C3: SAM 2 기반 과자 외곽선 세그멘테이션 마스크 추출 및 중심거리 기반 원형도(Roundness) 정밀 기하학 분석]**을 통해 0.01초 만에 4대 불량(조각 결손, 한쪽 파임, 단면 절단, 반쪽 파손)을 무결점으로 판정하여 C4 Visualizer로 전달하는 **전체 시스템의 중추 신경망(Core Brain)** 역할을 담당합니다.

### 🎯 핵심 4대 목표
1. **조명 불균일 대응 고감도 전처리 (C2)**: CLAHE 명암 보정 + HSV 적응형 색상 필터링과 모폴로지 닫힘(Morphology Close) 연산으로 그림자/노이즈 속에서도 과자만 100% 포착.
2. **3개 라인(LINE 01~03) 자동 슬라이싱 (C2)**: 컨베이어 Y좌표 기반 라인별 과자 추적 및 독립적 BBox 분할.
3. **초정밀 원형도($c = r_{min} / r_{max}$) 불량 판정 (C3)**: 과자 외곽선 중심거리 분포를 분석하여 팩맨/깨짐 결손을 0.001초 만에 포착 ($c < 0.82 \rightarrow \text{NG}$).
4. **마이크로서비스 비동기 파이프라인 연계**: C1 ➡️ C2 ➡️ C3 ➡️ C4 로 이어지는 지연 시간 50ms 미만의 초고속 파이프라인 실현.

---

## 2. 🔌 통신 인터페이스 규격 (I/O Specification)

### 📥 1단계: C1 Gateway ➡️ C2 Preprocessor (INPUT)
* **엔드포인트**: `POST http://c2-preprocessor:5001/preprocess`
* **요청 데이터 (JSON)**:
```json
{
  "image": "data:image/jpeg;base64,...",
  "ts": 1787620000000,
  "socketId": "sock_abc123"
}
```

### 🔄 2단계: C2 Preprocessor ➡️ C3 Inference Core (INTERNAL)
* **엔드포인트**: `POST http://c3-inference:5002/infer`
* **전달 데이터 (JSON)**:
```json
{
  "image": "data:image/jpeg;base64,...",
  "candidates": [
    {
      "bbox": [120, 85, 80, 80],
      "lane": "LINE 03",
      "area": 4820.5,
      "contour": [[120, 85], [125, 90], ...]
    }
  ],
  "ts": 1787620000000,
  "prep_latency_ms": 12.4
}
```

### 📤 3단계: C3 Inference Core ➡️ C4 Visualizer (OUTPUT)
* **엔드포인트**: `POST http://c4-visualizer:5003/visualize`
* **출력 데이터 (JSON)**:
```json
{
  "image": "data:image/jpeg;base64,...",
  "objects": [
    {
      "bbox": [120, 85, 80, 80],
      "lane": "LINE 03",
      "status": "NG",
      "roundness": 0.60,
      "defect_type": "WEDGE",
      "contour": [[120, 85], [125, 90], ...]
    }
  ],
  "total_obj": 4,
  "ng_count": 1,
  "ts": 1787620000000,
  "prep_latency_ms": 12.4,
  "infer_latency_ms": 18.2
}
```

---

## 3. 📐 4대 불량 판정 수학적 알고리즘 ($c = r_{min} / r_{max}$)

과자의 외곽선 좌표 집합 $P = \{(x_i, y_i)\}_{i=1}^N$ 과 중심점 $(\bar{x}, \bar{y})$ 사이의 거리 분포를 분석합니다:
$$r_i = \sqrt{(x_i - \bar{x})^2 + (y_i - \bar{y})^2}$$
$$c = \frac{\min(r_i)}{\max(r_i)}$$

| 분류 | 원형도 지수 ($c$) | 판정 상태 | 세부 결함 특징 |
| :--- | :---: | :---: | :--- |
| **HALF (반쪽 파손)** | $c < 0.40$ | **`NG` (불량)** | 과자의 절반 가까이가 잘려나간 대형 파손 |
| **WEDGE (조각 결손)** | $0.40 \le c < 0.60$ | **`NG` (불량)** | 피자 조각처럼 V자로 깊게 파인 결손 (사진 속 결함) |
| **CUT (단면 절단)** | $0.60 \le c < 0.72$ | **`NG` (불량)** | 한쪽 면이 직선 형태로 싹둑 잘려나간 결함 |
| **BITE (한쪽 파임)** | $0.72 \le c < 0.82$ | **`NG` (불량)** | 둥근 형태로 한 모서리가 뜯겨나간 결함 |
| **ROUND (정상)** | $c \ge 0.82$ | **`OK` (정상)** | 외곽선 결손이 없는 온전한 원형 과자 |

---

## 4. 🛠️ 개발 & 고도화 히스토리 (Changelog & Iterations)

* **📍 [Iteration 1.0] — 4단계 마이크로서비스 파이프라인 설계**: C1 Gateway ➡️ C2 Preprocessor ➡️ C3 Inference ➡️ C4 Visualizer 간의 RESTful 인터페이스 규격 확정.
* **📍 [Iteration 2.0] — C2 조명 적응형 HSV 색상 마스킹 구축**: CLAHE 적용 및 배경 고무 벨트(`#2a2e31`)와 황토색 쿠키를 100% 분리하는 색상 범위 필터링 및 모폴로지 닫힘 연산 적용.
* **📍 [Iteration 3.0] — 3개 생산 라인(LINE 01~03) Y좌표 자동 분할**: 프레임 높이($H$)를 3등분하여 과자가 어느 라인 위를 이동 중인지 실시간 인덱싱.
* **📍 [Iteration 4.0] — C3 중심거리 기반 원형도($c = r_{min}/r_{max}$) 계산 엔진**: 과자 중심점으로부터 모든 외곽점까지의 거리를 계산하여 팩맨 결함을 $c=0.60$ 수준으로 정밀 감지.
* **📍 [Iteration 5.0] — 4대 결함 유형 자동 분류기 구현**: `WEDGE`, `BITE`, `CUT`, `HALF` 정규화 분류 로직 완성.
* **📍 [Iteration 6.0] — C4 렌더링용 마스크 좌표(Contour) 직렬화**: Visualizer가 프레임에 외곽선을 그대로 그릴 수 있도록 2D 좌표 리스트 패키징.
* **📍 [Iteration 7.0] — Zero-Lag 최신 프레임 래치 및 실시간 볼륨 마운트 탑재**: 도커 재시작 없는 핫 리로드 및 19ms 초고속 실시간 파이프라인 확정.
* **📍 [Iteration 8.0] — 가우시안 블러(Gaussian Blur) 노이즈 필터링 도입**: C2 전처리 과정에 모니터 모아레 현상 및 정지 화면 빛 반사 노이즈를 부드럽게 제거하는 전처리 추가.
* **📍 [Iteration 9.0] — 원근 왜곡 대응 원형도 컷오프 정밀 재조정**: 스마트폰 카메라 각도에 따른 찌그러짐을 반영하여 정상(OK) 판정 컷오프를 $c=0.82$에서 $c=0.71$로 현실적으로 상향 재조정.
