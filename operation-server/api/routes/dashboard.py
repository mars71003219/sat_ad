"""
Dashboard API
"""
from fastapi import APIRouter, HTTPException
import sys
from pathlib import Path

# Add operation-server to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.victoria_client import victoria_client
from database.postgres_client import postgres_client

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats():
    """대시보드 통계 (캐싱 최적화)"""
    try:
        # 캐싱된 데이터 사용으로 빠른 응답
        inference_stats = victoria_client.get_inference_statistics()
        satellites = postgres_client.get_all_satellites()

        return {
            "inference_stats": inference_stats,
            "total_satellites": len(satellites),
            "active_satellites": sum(1 for s in satellites if s.get('monitoring_enabled')),
            "satellites": satellites
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/features")
async def get_subsystem_features(subsystem: str):
    """서브시스템의 특징 목록 조회"""
    try:
        features = victoria_client.get_subsystem_features(subsystem)
        return {
            "subsystem": subsystem,
            "features": features
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
