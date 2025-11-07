"""
Operation Server - FastAPI
시스템 관리 및 모니터링 API
"""
import logging
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add operation-server to Python path
sys.path.insert(0, str(Path(__file__).parent))

from api.routes import dashboard, config, websocket

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI App
app = FastAPI(
    title="Telemetry Anomaly Detection API",
    description="위성 텔레메트리 이상 탐지 시스템 API",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(dashboard.router)
app.include_router(config.router)
app.include_router(websocket.router)


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "service": "Telemetry Anomaly Detection API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """헬스 체크"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
