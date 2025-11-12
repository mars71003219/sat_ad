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
        inference_stats = await victoria_client.get_inference_statistics()
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


@router.get("/trends")
async def get_trend_data(
    satellite_id: str,
    subsystem: str,
    feature_index: int,
    start_time: str,
    end_time: str
):
    """실시간 트렌드 데이터 조회 (텔레메트리 + 추론 결과)"""
    try:
        # 텔레메트리 데이터 쿼리
        telemetry_query = f'''
            smap_feature{{
                satellite_id="{satellite_id}",
                subsystem="{subsystem}",
                feature_index="{feature_index}"
            }}
        '''

        # 추론 결과 데이터 쿼리 (reconstruction)
        inference_query = f'''
            inference_reconstruction{{
                satellite_id="{satellite_id}",
                subsystem="{subsystem}",
                feature_index="{feature_index}"
            }}
        '''

        # 이상 점수 쿼리
        anomaly_score_query = f'''
            inference_anomaly_score_mean{{
                satellite_id="{satellite_id}",
                subsystem="{subsystem}"
            }}
        '''

        # 병렬로 쿼리 실행
        telemetry_data = await victoria_client.query_range(
            telemetry_query, start_time, end_time, step='30s'
        )
        inference_data = await victoria_client.query_range(
            inference_query, start_time, end_time, step='30s'
        )
        anomaly_scores = await victoria_client.query_range(
            anomaly_score_query, start_time, end_time, step='30s'
        )

        # 데이터 병합
        data_points = []

        # 텔레메트리 데이터를 기준으로 병합
        if telemetry_data and len(telemetry_data) > 0:
            telemetry_values = telemetry_data[0].get('values', [])
            inference_values = inference_data[0].get('values', []) if inference_data and len(inference_data) > 0 else []
            anomaly_values = anomaly_scores[0].get('values', []) if anomaly_scores and len(anomaly_scores) > 0 else []

            # 딕셔너리로 변환 (빠른 검색)
            inference_dict = {int(v[0]): float(v[1]) for v in inference_values}
            anomaly_dict = {int(v[0]): float(v[1]) for v in anomaly_values}

            for timestamp, value in telemetry_values:
                ts = int(timestamp)
                data_points.append({
                    'timestamp': ts,
                    'actual_value': float(value),
                    'predicted_value': inference_dict.get(ts),
                    'anomaly_score': anomaly_dict.get(ts, 0.0)
                })

        return {
            "satellite_id": satellite_id,
            "subsystem": subsystem,
            "feature_index": feature_index,
            "data_points": data_points
        }

    except Exception as e:
        print(f"Error in get_trend_data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
