from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "ok", "service": "C2 Preprocessing"}

@app.post("/preprocess")
async def preprocess(payload: dict):
    # TODO: 영상 프레임 전처리 및 과자 영역 분할 로직 작성
    return {"status": "ok", "message": "Preprocessed successfully"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)
