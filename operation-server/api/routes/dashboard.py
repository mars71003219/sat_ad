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
    """대시보드 통계"""
    try:
        # 추론 통계
        inference_stats = victoria_client.get_inference_statistics()

        # 위성 수
        satellites = postgres_client.get_all_satellites()

        # 최근 추론 결과
        recent_inferences = victoria_client.get_recent_inference_results(limit=10)

        return {
            "inference_stats": inference_stats,
            "total_satellites": len(satellites),
            "active_satellites": sum(1 for s in satellites if s.get('monitoring_enabled')),
            "recent_inferences": recent_inferences
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/anomalies")
async def get_recent_anomalies(hours: int = 24):
    """최근 이상 감지"""
    try:
        anomalies = victoria_client.get_anomaly_trend(hours=hours)
        return {
            "anomalies": anomalies,
            "count": len(anomalies),
            "hours": hours
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
