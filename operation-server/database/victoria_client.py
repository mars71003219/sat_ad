"""
VictoriaMetrics 클라이언트
시계열 데이터 및 추론 결과 조회
"""
import os
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class VictoriaMetricsClient:
    """VictoriaMetrics 클라이언트"""

    def __init__(self):
        self.base_url = os.getenv('VICTORIA_METRICS_URL', 'http://victoria-metrics:8428')
        self.query_url = f"{self.base_url}/api/v1/query"
        self.range_query_url = f"{self.base_url}/api/v1/query_range"

    def query(self, query: str, time: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """PromQL 쿼리 실행"""
        try:
            params = {"query": query}
            if time:
                params["time"] = time

            response = requests.get(self.query_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            if data.get("status") == "success":
                return data.get("data", {})
            else:
                logger.error(f"Query failed: {data.get('error')}")
                return None

        except Exception as e:
            logger.error(f"Error querying VictoriaMetrics: {e}")
            return None

    def get_recent_inference_results(self, limit: int = 20, satellite_id: str = None) -> List[Dict[str, Any]]:
        """최근 추론 결과 조회"""
        try:
            if satellite_id:
                query = f'inference_anomaly_score{{satellite_id="{satellite_id}"}}'
            else:
                query = 'inference_anomaly_score'

            result = self.query(query)
            if not result or not result.get('result'):
                return []

            results = []
            for item in result['result'][:limit]:
                metric = item.get('metric', {})
                value = item.get('value', [])

                results.append({
                    'satellite_id': metric.get('satellite_id'),
                    'subsystem': metric.get('subsystem'),
                    'batch_id': metric.get('batch_id'),
                    'anomaly_score': float(value[1]) if len(value) > 1 else 0.0,
                    'timestamp': value[0] if len(value) > 0 else None
                })

            return results

        except Exception as e:
            logger.error(f"Error getting recent inferences: {e}")
            return []

    def get_inference_statistics(self) -> Dict[str, Any]:
        """추론 통계 조회"""
        try:
            # 전체 추론 수
            total_query = 'count(inference_anomaly_score)'
            total_result = self.query(total_query)

            # 이상 감지 수
            anomaly_query = 'count(inference_anomaly_score > 0.7)'
            anomaly_result = self.query(anomaly_query)

            total_count = 0
            anomaly_count = 0

            if total_result and total_result.get('result'):
                value = total_result['result'][0].get('value', [])
                total_count = int(float(value[1])) if len(value) > 1 else 0

            if anomaly_result and anomaly_result.get('result'):
                value = anomaly_result['result'][0].get('value', [])
                anomaly_count = int(float(value[1])) if len(value) > 1 else 0

            return {
                'total_inferences': total_count,
                'anomalies_detected': anomaly_count,
                'anomaly_rate': (anomaly_count / total_count * 100) if total_count > 0 else 0.0
            }

        except Exception as e:
            logger.error(f"Error getting inference statistics: {e}")
            return {
                'total_inferences': 0,
                'anomalies_detected': 0,
                'anomaly_rate': 0.0
            }

    def get_anomaly_trend(self, hours: int = 24) -> List[Dict[str, Any]]:
        """이상 감지 트렌드 조회"""
        try:
            end_time = int(datetime.now().timestamp())
            start_time = end_time - (hours * 3600)

            query = 'inference_anomaly_score > 0.7'

            params = {
                "query": query,
                "start": start_time,
                "end": end_time,
                "step": "1h"
            }

            response = requests.get(self.range_query_url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            if data.get("status") != "success":
                return []

            result = data.get("data", {}).get("result", [])
            trend = []

            for item in result:
                metric = item.get('metric', {})
                values = item.get('values', [])

                for value in values:
                    trend.append({
                        'satellite_id': metric.get('satellite_id'),
                        'subsystem': metric.get('subsystem'),
                        'timestamp': value[0],
                        'anomaly_score': float(value[1])
                    })

            return trend

        except Exception as e:
            logger.error(f"Error getting anomaly trend: {e}")
            return []


# 싱글톤 인스턴스
victoria_client = VictoriaMetricsClient()
