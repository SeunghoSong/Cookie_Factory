from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "ok", "service": "C2 Preprocessing"}

@app.post("/preprocess")
async def preprocess(payload: dict):
    # TODO: 영상 프레임 전처리 및 과자 영역 분할 로직 작성
    return {"status": "ok", "message": "Preprocessed successfully"}

@app.websocket("/ws/preprocess")
async def ws_preprocess(websocket: WebSocket):
    # C1 Gateway가 릴레이하는 프레임 수신 엔드포인트: {frame_id, timestamp, image(Base64 JPEG)}
    await websocket.accept()
    try:
        while True:
            frame = await websocket.receive_json()
            # TODO: 리사이즈/정규화 + box prompt 생성(§2-1) 후 C3로 전달
            print(f"[C2] frame received: frame_id={frame.get('frame_id')}")
    except WebSocketDisconnect:
        print("[C2] C1 gateway disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)
