from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "ok", "service": "C2 Preprocessing"}

@app.post("/preprocess")
async def preprocess(payload: dict):
    # C1 Gateway가 HTTP POST로 전달하는 프레임: {frame_id, timestamp, image(Base64 JPEG)}
    # TODO: 리사이즈/정규화 + box prompt 생성(§2-1) 후 C3로 전달
    return {"status": "ok", "message": "Preprocessed successfully"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)
