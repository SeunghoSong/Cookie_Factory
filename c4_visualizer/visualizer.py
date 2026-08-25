from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "ok", "service": "C4 Visualizer"}

@app.post("/visualize")
async def visualize(payload: dict):
    # TODO: 불량 과자 영역 바운딩 박스/마스크 오버레이 렌더링 로직 작성
    return {"status": "ok", "message": "Visualized successfully"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5003)
