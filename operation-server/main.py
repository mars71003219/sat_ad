"""
Operation Server - FastAPI
시스템 관리 및 모니터링 API
"""
import logging
import sys
from pathlib import Path
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Add operation-server to Python path
sys.path.insert(0, str(Path(__file__).parent))

from api.routes import dashboard, config, websocket
from database.victoria_client import victoria_client
from database.postgres_client import postgres_client

# Logging (환경 변수 기반)
import os

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.info(f"Logging level set to: {LOG_LEVEL}")

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

# 전역 예외 핸들러
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP 예외 핸들러"""
    logger.error(f"HTTP error: {exc.status_code} - {exc.detail} - {request.url}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "path": str(request.url)}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """요청 검증 예외 핸들러"""
    logger.error(f"Validation error: {exc.errors()} - {request.url}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "path": str(request.url)}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """전역 예외 핸들러"""
    logger.error(f"Unhandled exception: {exc} - {request.url}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "path": str(request.url)}
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


@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 이벤트"""
    logger.info("Application startup")


@app.on_event("shutdown")
async def shutdown_event():
    """애플리케이션 종료 이벤트"""
    logger.info("Application shutdown - closing connections")
    await victoria_client.close()
    postgres_client.close_all()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
