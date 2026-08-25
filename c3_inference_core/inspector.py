from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "ok", "service": "C3 SAM 2 Inference"}

@app.post("/infer")
async def infer(payload: dict):
    # TODO: SAM 2 마스크 추출 및 원형도 불량 판정 로직 작성
    return {"status": "ok", "message": "Inference completed"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5002)
