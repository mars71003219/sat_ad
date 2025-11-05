"""
Configuration API
"""
from fastapi import APIRouter, HTTPException
import sys
from pathlib import Path

# Add operation-server to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.postgres_client import postgres_client

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/system")
async def get_system_configs():
    """시스템 설정 조회"""
    try:
        configs = postgres_client.get_all_system_configs()
        return {"configs": configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/satellites")
async def get_satellites():
    """위성 목록 조회"""
    try:
        satellites = postgres_client.get_all_satellites(enabled_only=False)
        return {"satellites": satellites}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subsystems")
async def get_subsystems():
    """서브시스템 목록 조회"""
    try:
        subsystems = postgres_client.get_all_subsystems(enabled_only=False)
        return {"subsystems": subsystems}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
