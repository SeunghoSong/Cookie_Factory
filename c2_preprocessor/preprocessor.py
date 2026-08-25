# -*- coding: utf-8 -*-
import os
import base64
import time
import httpx
import cv2
import numpy as np
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INFERENCE_URL = os.getenv("INFERENCE_URL", "http://localhost:5002/infer")

class FrameInput(BaseModel):
    image: str
    ts: int
    socketId: str = ""

def extract_cookie_candidates(frame):
    """
    3개 라인 컨베이어에서 황토색 쿠키 후보군 검출 및 BBox 추출
    """
    h, w = frame.shape[:2]
    # ★ 추가: 모니터 모아레 패턴 및 픽셀 노이즈 제거를 위한 가우시안 블러
    frame_blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(frame_blurred, cv2.COLOR_BGR2HSV)

    # 1. 조명 보정을 위한 V 채널 CLAHE 적용
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    hsv[:, :, 2] = clahe.apply(hsv[:, :, 2])

    # 2. 쿠키 황토색 범위 마스크 (Hue 8~38, Sat 50~255, Val 50~255)
    lower_cookie = np.array([8, 50, 50])
    upper_cookie = np.array([38, 255, 255])
    mask = cv2.inRange(hsv, lower_cookie, upper_cookie)

    # 3. 모폴로지 닫힘 연산으로 내부 초코칩 점 및 노이즈 메우기
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask_closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        # 1. 면적 필터링: 너무 작은 노이즈나 거대한 피부/화면 영역 제외 (1000 ~ 40000 픽셀)
        if 500 < area < 40000:
            x, y, bw, bh = cv2.boundingRect(cnt)
            
            # 2. 종횡비(Aspect Ratio) 필터링: 선이나 길쭉한 형태 제외 (쿠키는 둥근 형태)
            # 2. Border Rejection (경계선 무시): 화면 테두리에 걸친 과자 무시
            margin = 10
            if x < margin or y < margin or (x + bw) > w - margin or (y + bh) > h - margin:
                continue

            aspect_ratio = float(bw) / bh
            if 0.25 <= aspect_ratio <= 4.0:
                # 3개 라인 판정 (Y좌표 기준)
                lane_idx = int(y / (h / 3.0)) + 1
                lane_name = f"LINE {min(3, max(1, lane_idx)):02d}"

                candidates.append({
                    "bbox": [int(x), int(y), int(bw), int(bh)],
                    "lane": lane_name,
                    "area": float(area),
                    "contour": cnt.tolist()
                })

    return candidates

@app.post("/preprocess")
async def preprocess_endpoint(payload: FrameInput):
    start_t = time.time()
    try:
        img_str = payload.image
        if "," in img_str:
            img_str = img_str.split(",")[1]
        img_bytes = base64.b64decode(img_str)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return {"status": "error", "message": "Decode failed"}

        # 과자 후보군 추출
        candidates = extract_cookie_candidates(frame)
        prep_latency = round((time.time() - start_t) * 1000, 1)

        # C3 Inference Core로 고속 전달
        async with httpx.AsyncClient() as client:
            await client.post(
                INFERENCE_URL,
                json={
                    "image": payload.image,
                    "candidates": candidates,
                    "ts": payload.ts,
                    "prep_latency_ms": prep_latency,
                    "socketId": payload.socketId
                },
                timeout=5.0
            )

        return {"status": "ok", "candidates_count": len(candidates), "latency_ms": prep_latency}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
def health():
    return {"status": "ok", "service": "C2 Preprocessor", "port": 5001}

if __name__ == "__main__":
    print("🚀 [C2 Preprocessor] Running on http://0.0.0.0:5001")
    uvicorn.run(app, host="0.0.0.0", port=5001)
