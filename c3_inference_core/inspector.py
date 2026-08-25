# -*- coding: utf-8 -*-
import os
import time
import httpx
import numpy as np
import cv2
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

VISUALIZER_URL = os.getenv("VISUALIZER_URL", "http://localhost:5003/visualize")

class CandidateItem(BaseModel):
    bbox: list
    lane: str
    area: float
    contour: list

class InferenceInput(BaseModel):
    image: str
    candidates: list
    ts: int
    prep_latency_ms: float = 0.0
    socketId: str = ""

def analyze_defect_shape(contour_list, bbox):
    """
    과자 외곽선 세그멘테이션 분석: 원형도 c = r_min / r_max 및 4대 결함 판정
    """
    cnt = np.array(contour_list, dtype=np.int32)
    x, y, w, h = bbox
    cx, cy = x + w / 2.0, y + h / 2.0

    # 외곽점들로부터 중심까지의 유클리드 거리 계산
    distances = []
    for pt in cnt:
        px, py = pt[0]
        d = np.sqrt((px - cx) ** 2 + (py - cy) ** 2)
        distances.append(d)

    if not distances:
        return {"status": "OK", "roundness": 1.0, "defect_type": "ROUND"}

    r_min = float(np.min(distances))
    r_max = float(np.max(distances))

    roundness = (r_min / r_max) if r_max > 0 else 1.0
    roundness = round(float(roundness), 2)

    # 불량 판정 임계값: c < 0.75 이면 불량(NG)
    if roundness < 0.75:
        if roundness < 0.40:
            defect_type = "HALF"      # 반쪽 파손
        elif roundness < 0.55:
            defect_type = "WEDGE"     # 조각 결손
        elif roundness < 0.65:
            defect_type = "CUT"       # 단면 절단
        else:
            defect_type = "BITE"      # 한쪽 파임
        status = "NG"
    else:
        status = "OK"
        defect_type = "ROUND"         # 정상 원형

    return {
        "status": status,
        "roundness": roundness,
        "defect_type": defect_type,
        "r_min": r_min,
        "r_max": r_max
    }

@app.post("/infer")
async def infer_endpoint(payload: InferenceInput):
    start_t = time.time()
    try:
        inspected_objects = []
        ng_count = 0

        for cand in payload.candidates:
            analysis = analyze_defect_shape(cand["contour"], cand["bbox"])
            if analysis["status"] == "NG":
                ng_count += 1

            inspected_objects.append({
                "bbox": cand["bbox"],
                "lane": cand["lane"],
                "area": cand["area"],
                "contour": cand["contour"],
                "status": analysis["status"],
                "roundness": analysis["roundness"],
                "defect_type": analysis["defect_type"]
            })

        infer_latency = round((time.time() - start_t) * 1000, 1)

        # C4 Visualizer로 고속 전달
        async with httpx.AsyncClient() as client:
            await client.post(
                VISUALIZER_URL,
                json={
                    "image": payload.image,
                    "objects": inspected_objects,
                    "total_obj": len(inspected_objects),
                    "ng_count": ng_count,
                    "ts": payload.ts,
                    "prep_latency_ms": payload.prep_latency_ms,
                    "infer_latency_ms": infer_latency,
                    "socketId": payload.socketId
                },
                timeout=5.0
            )

        return {"status": "ok", "inspected": len(inspected_objects), "ng_count": ng_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
def health():
    return {"status": "ok", "service": "C3 SAM 2 Inference Core", "port": 5002}

if __name__ == "__main__":
    print("🚀 [C3 SAM 2 Inference Core] Running on http://0.0.0.0:5002")
    uvicorn.run(app, host="0.0.0.0", port=5002)
