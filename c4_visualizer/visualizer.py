import base64
import json
import os
import time
import uuid

import cv2
import numpy as np
import requests
from fastapi import FastAPI
import uvicorn

app = FastAPI()

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://c1-gateway:8000/stream-result")
OUTPUT_JSON_DIR = "/app/output_json"
CAPTURES_DIR = "/app/captures"

os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)
os.makedirs(CAPTURES_DIR, exist_ok=True)

NG_COLOR = (0, 0, 255)   # BGR: red
OK_COLOR = (0, 200, 0)   # BGR: green


@app.get("/")
def health_check():
    return {"status": "ok", "service": "C4 Visualizer"}


def decode_image(image_b64: str) -> np.ndarray:
    if "," in image_b64 and image_b64.strip().startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]
    raw = base64.b64decode(image_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def encode_image(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", img)
    if not ok:
        raise ValueError("Failed to encode marked image as JPEG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def is_defective(status: str) -> bool:
    return str(status).upper() in ("NG", "FAIL", "DEFECTIVE")


def draw_object(img: np.ndarray, obj: dict) -> None:
    color = NG_COLOR if is_defective(obj.get("status")) else OK_COLOR

    bbox = obj.get("bbox")
    if bbox and len(bbox) == 4:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        roundness = obj.get("roundness")
        label = f"{obj.get('status', '?')}"
        if roundness is not None:
            label += f" c={float(roundness):.2f}"

        label_y = max(y1 - 10, 15)
        cv2.putText(img, label, (x1, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

    contour = obj.get("contour")
    if contour:
        pts = np.array(contour, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [pts], isClosed=True, color=color, thickness=2)


def pick_primary_object(objects: list) -> dict | None:
    if not objects:
        return None
    for obj in objects:
        if is_defective(obj.get("status")):
            return obj
    return objects[0]


@app.post("/visualize")
async def visualize(payload: dict):
    # C3 -> C4 페이로드: {frame_id?, timestamp?, image, objects: [{bbox, status, roundness, contour}]}
    frame_id = payload.get("frame_id")
    if not frame_id:
        # C3 스펙에 frame_id가 아직 명시되지 않아 임시로 생성함. C3 담당자와 확정 필요.
        frame_id = f"c4-{uuid.uuid4().hex[:12]}"
        print(f"[C4] WARNING: payload missing frame_id, generated fallback {frame_id}")

    timestamp = payload.get("timestamp", int(time.time() * 1000))
    objects = payload.get("objects", [])

    img = decode_image(payload["image"])

    for obj in objects:
        draw_object(img, obj)

    marked_image_b64 = encode_image(img)

    primary = pick_primary_object(objects)
    if primary is None:
        status = "NO_OBJECT"
        defective = False
        circularity = None
        bbox = None
        mask_polygon = None
    else:
        defective = is_defective(primary.get("status"))
        status = "FAIL" if defective else "OK"
        circularity = primary.get("roundness")
        bbox = primary.get("bbox")
        mask_polygon = primary.get("contour")

    result = {
        "frame_id": frame_id,
        "timestamp": timestamp,
        "image": marked_image_b64,
        "status": status,
        "is_defective": defective,
        "circularity": circularity,
        "bbox": bbox,
        "mask_polygon": mask_polygon,
    }

    _save_debug_artifacts(frame_id, img, result)
    _forward_to_gateway(result)

    return {"status": "ok", "frame_id": frame_id}


def _save_debug_artifacts(frame_id: str, marked_img: np.ndarray, result: dict) -> None:
    try:
        cv2.imwrite(os.path.join(CAPTURES_DIR, f"{frame_id}.jpg"), marked_img)
        with open(os.path.join(OUTPUT_JSON_DIR, f"{frame_id}.json"), "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in result.items() if k != "image"}, f, ensure_ascii=False)
    except OSError as e:
        print(f"[C4] WARNING: failed to save debug artifacts: {e}")


def _forward_to_gateway(result: dict) -> None:
    try:
        resp = requests.post(GATEWAY_URL, json=result, timeout=3)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[C4] WARNING: failed to forward result to C1 ({GATEWAY_URL}): {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5003)
