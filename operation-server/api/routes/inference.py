"""
Inference API
"""
from fastapi import APIRouter, HTTPException
import sys
from pathlib import Path

# Add operation-server to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.victoria_client import victoria_client

router = APIRouter(prefix="/api/inference", tags=["inference"])


@router.get("/recent")
async def get_recent_inferences(limit: int = 20, satellite_id: str = None):
    """최근 추론 결과 조회"""
    try:
        results = victoria_client.get_recent_inference_results(limit=limit, satellite_id=satellite_id)
        return {
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_inference_statistics():
    """추론 통계 조회"""
    try:
        stats = victoria_client.get_inference_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
