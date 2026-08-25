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

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000/stream-result")
CAPTURES_DIR = "captures"
OUTPUT_JSON_DIR = "output_json"
os.makedirs(CAPTURES_DIR, exist_ok=True)
os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)

class VisualizerInput(BaseModel):
    image: str
    objects: list
    total_obj: int
    ng_count: int
    ts: int
    prep_latency_ms: float = 0.0
    infer_latency_ms: float = 0.0
    socketId: str = ""

def render_visualization_overlay(frame, objects, total_obj, ng_count, latency_ms):
    """
    사진과 100% 동일한 빨간 박스, 마스크 테두리, 라벨, 상단 HUD 렌더링
    """
    overlay = frame.copy()
    h, w = frame.shape[:2]

    # 1. 과자별 BBox 및 외곽선 마스크 렌더링
    for obj in objects:
        x, y, bw, bh = obj["bbox"]
        status = obj["status"]
        c_val = obj["roundness"]
        cnt = np.array(obj["contour"], dtype=np.int32)

        if status == "NG":
            # 불량품: 밝은 빨간색 외곽선 마스크 및 바운딩 박스
            color = (43, 55, 235)  # BGR: 선명한 빨간색
            cv2.drawContours(overlay, [cnt], -1, color, 3)
            cv2.rectangle(overlay, (x, y), (x + bw, y + bh), color, 2)

            # 텍스트 뱃지 (NG c=0.60)
            label = f"NG c={c_val:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(overlay, (x, y - th - 8), (x + tw + 6, y), color, -1)
            cv2.putText(overlay, label, (x + 3, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        else:
            # 정상품: 은은한 연초록색 외곽선 마스크
            color = (83, 192, 87)  # BGR: 연한 초록색
            cv2.drawContours(overlay, [cnt], -1, color, 1)

    # 2. 상단 HUD 상태 바 (사진과 100% 동일: OBJ 4  NG 1  52ms  INSPECTOR-ACTIVE)
    cv2.rectangle(overlay, (0, 0), (w, 34), (15, 18, 20), -1)

    hud_text = f"OBJ {total_obj}   NG {ng_count}   {latency_ms:.0f}ms   INSPECTOR-ACTIVE"
    hud_color = (69, 90, 255) if ng_count > 0 else (214, 244, 255)
    cv2.putText(overlay, hud_text, (14, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.60, hud_color, 2)

    return overlay

@app.post("/visualize")
async def visualize_endpoint(payload: VisualizerInput):
    start_t = time.time()
    try:
        img_str = payload.image
        if "," in img_str:
            img_str = img_str.split(",")[1]
        img_bytes = base64.b64decode(img_str)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return {"status": "error"}

        total_latency = payload.prep_latency_ms + payload.infer_latency_ms + round((time.time() - start_t) * 1000, 1)

        # 오버레이 렌더링
        rendered_frame = render_visualization_overlay(
            frame,
            payload.objects,
            payload.total_obj,
            payload.ng_count,
            total_latency
        )

        # 인코딩 후 C1 Gateway로 역전송
        _, buf = cv2.imencode('.jpg', rendered_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        rendered_b64 = "data:image/jpeg;base64," + base64.b64encode(buf).decode('utf-8')

        async with httpx.AsyncClient() as client:
            await client.post(
                GATEWAY_URL,
                json={
                    "rendered_image": rendered_b64,
                    "total_obj": payload.total_obj,
                    "ng_count": payload.ng_count,
                    "latency_ms": total_latency,
                    "objects": payload.objects,
                    "socketId": payload.socketId
                },
                timeout=5.0
            )

        return {"status": "ok", "latency_ms": total_latency}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
def health():
    return {"status": "ok", "service": "C4 Visualizer", "port": 5003}

if __name__ == "__main__":
    print("🚀 [C4 Visualizer Engine] Running on http://0.0.0.0:5003")
    uvicorn.run(app, host="0.0.0.0", port=5003)
