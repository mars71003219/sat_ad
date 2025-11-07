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

    # 서브시스템별 특징 매핑
    SUBSYSTEM_FEATURES = {
        'eps': [
            'satellite_battery_voltage', 'satellite_battery_soc', 'satellite_battery_current',
            'satellite_battery_temp', 'satellite_solar_panel_1_voltage', 'satellite_solar_panel_1_current',
            'satellite_solar_panel_2_voltage', 'satellite_solar_panel_2_current', 'satellite_solar_panel_3_voltage',
            'satellite_solar_panel_3_current', 'satellite_power_consumption', 'satellite_power_generation'
        ],
        'thermal': [
            'satellite_temp_battery', 'satellite_temp_obc', 'satellite_temp_comm',
            'satellite_temp_payload', 'satellite_temp_solar_panel', 'satellite_temp_external'
        ],
        'aocs': [
            'satellite_gyro_x', 'satellite_gyro_y', 'satellite_gyro_z', 'satellite_sun_angle',
            'satellite_mag_x', 'satellite_mag_y', 'satellite_mag_z', 'satellite_wheel_1_rpm',
            'satellite_wheel_2_rpm', 'satellite_wheel_3_rpm', 'satellite_altitude', 'satellite_velocity'
        ],
        'comm': [
            'satellite_rssi', 'satellite_data_backlog', 'satellite_last_contact'
        ]
    }

    def __init__(self):
        self.base_url = os.getenv('VICTORIA_METRICS_URL', 'http://victoria-metrics:8428')
        self.query_url = f"{self.base_url}/api/v1/query"
        self.range_query_url = f"{self.base_url}/api/v1/query_range"
        self._stats_cache = None
        self._stats_cache_time = 0

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

    def get_recent_inference_results(
        self,
        limit: int = 10,
        satellite_id: str = None,
        subsystem: str = None,
        feature_index: int = None
    ) -> List[Dict[str, Any]]:
        """최근 추론 결과 조회 (instant query로 최적화)"""
        try:
            # satellite_id와 subsystem은 필수 (없으면 빈 리스트 반환)
            if not satellite_id or not subsystem:
                logger.warning("satellite_id and subsystem are required for recent inference query")
                return []

            # feature_index 결정 (지정되지 않으면 0)
            feature_idx = feature_index if feature_index is not None else 0

            # 최근 5분간의 데이터 조회 (충분한 데이터 포인트)
            end_time = int(datetime.now().timestamp())
            start_time = end_time - 300  # 5분

            # 필수 필터 포함한 쿼리 생성
            score_query = f'inference_anomaly_score{{satellite_id="{satellite_id}",subsystem="{subsystem}"}}'
            pred_query = f'inference_prediction_feature{{satellite_id="{satellite_id}",subsystem="{subsystem}",feature_index="{feature_idx}"}}'

            # 병렬 쿼리 실행 (타임아웃 2초로 단축)
            import concurrent.futures

            def fetch_metric(query_type_query):
                query_type, query = query_type_query
                params = {
                    "query": query,
                    "start": start_time,
                    "end": end_time,
                    "step": "30s"
                }
                try:
                    response = requests.get(self.range_query_url, params=params, timeout=2)
                    if response.ok:
                        data = response.json()
                        if data.get("status") == "success":
                            return query_type, data.get("data", {}).get("result", [])
                except Exception as e:
                    logger.error(f"Query {query_type} failed: {e}")
                return query_type, []

            query_results = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(fetch_metric, ('score', score_query)): 'score',
                    executor.submit(fetch_metric, ('pred', pred_query)): 'pred'
                }
                for future in concurrent.futures.as_completed(futures, timeout=3):
                    try:
                        query_type, data = future.result()
                        query_results[query_type] = data
                    except Exception as e:
                        logger.error(f"Parallel query error: {e}")

            # 타임스탬프별로 데이터 분류
            from collections import defaultdict
            inference_data = defaultdict(lambda: defaultdict(dict))

            # anomaly_score 처리
            for series in query_results.get('score', []):
                metric = series.get('metric', {})
                values = series.get('values', [])
                sat_id = metric.get('satellite_id')
                sub = metric.get('subsystem')
                key = (sat_id, sub)

                for value in values:
                    timestamp = value[0]
                    val = float(value[1]) if len(value) > 1 else 0.0
                    inference_data[key][timestamp]['anomaly_score'] = val
                    inference_data[key][timestamp]['satellite_id'] = sat_id
                    inference_data[key][timestamp]['subsystem'] = sub
                    inference_data[key][timestamp]['timestamp'] = timestamp

            # predicted_value 처리
            for series in query_results.get('pred', []):
                metric = series.get('metric', {})
                values = series.get('values', [])
                sat_id = metric.get('satellite_id')
                sub = metric.get('subsystem')
                key = (sat_id, sub)

                for value in values:
                    timestamp = value[0]
                    val = float(value[1]) if len(value) > 1 else 0.0
                    inference_data[key][timestamp]['predicted_value'] = val
                    inference_data[key][timestamp]['satellite_id'] = sat_id
                    inference_data[key][timestamp]['subsystem'] = sub
                    inference_data[key][timestamp]['timestamp'] = timestamp

            # 모든 타임스탬프를 펼쳐서 리스트로 변환
            all_inferences = []
            for key, timestamps in inference_data.items():
                for ts, data in timestamps.items():
                    all_inferences.append(data)

            # timestamp 기준 역순 정렬하여 최근 N개 선택
            all_inferences.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            recent_inferences = all_inferences[:limit]

            # actual 값 조회 (선택된 추론 결과에 대해서만)
            for inference in recent_inferences:
                sat_id = inference.get('satellite_id')
                sub = inference.get('subsystem')

                if sub in self.SUBSYSTEM_FEATURES:
                    features = self.SUBSYSTEM_FEATURES[sub]
                    if feature_idx < len(features):
                        metric_name = features[feature_idx]
                        actual_query = f'{metric_name}{{satellite_id="{sat_id}"}}'
                        actual_result = self.query(actual_query)

                        if actual_result and actual_result.get('result'):
                            actual_value = actual_result['result'][0].get('value', [])
                            if len(actual_value) > 1:
                                inference['actual_value'] = float(actual_value[1])
                                inference['feature_name'] = metric_name
                        else:
                            inference['actual_value'] = None
                            inference['feature_name'] = metric_name
                    else:
                        inference['actual_value'] = None
                        inference['feature_name'] = 'N/A'
                else:
                    inference['actual_value'] = None
                    inference['feature_name'] = 'N/A'

            # 결과 리스트 생성
            results = []
            for inference in recent_inferences:
                results.append({
                    'satellite_id': inference.get('satellite_id'),
                    'subsystem': inference.get('subsystem'),
                    'feature_index': feature_idx,
                    'feature_name': inference.get('feature_name', 'N/A'),
                    'anomaly_score': inference.get('anomaly_score'),
                    'actual_value': inference.get('actual_value'),
                    'predicted_value': inference.get('predicted_value'),
                    'timestamp': int(inference['timestamp']) if inference.get('timestamp') else None
                })

            return results

        except Exception as e:
            logger.error(f"Error getting recent inferences: {e}")
            return []

    def get_inference_statistics(self) -> Dict[str, Any]:
        """추론 통계 조회 (5초 캐싱)"""
        try:
            import time

            # 5초 캐싱
            current_time = time.time()
            if self._stats_cache and (current_time - self._stats_cache_time) < 5:
                return self._stats_cache

            from datetime import datetime

            # 간단한 통계: 현재 시계열 개수만 카운트 (빠름)
            total_query = 'count(inference_anomaly_score)'
            total_result = self.query(total_query)

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

            result = {
                'total_inferences': total_count,
                'anomalies_detected': anomaly_count,
                'anomaly_rate': (anomaly_count / total_count * 100) if total_count > 0 else 0.0
            }

            # 캐시 업데이트
            self._stats_cache = result
            self._stats_cache_time = current_time

            return result

        except Exception as e:
            logger.error(f"Error getting inference statistics: {e}")
            return {
                'total_inferences': 0,
                'anomalies_detected': 0,
                'anomaly_rate': 0.0
            }

    def get_anomaly_score_trend(
        self,
        satellite_id: str,
        subsystem: str,
        start_time: datetime,
        end_time: datetime,
        feature_index: int = None
    ) -> List[Dict[str, Any]]:
        """특정 위성/서브시스템의 실측값, 예측값, anomaly score 트렌드 조회"""
        try:
            start_ts = int(start_time.timestamp())
            end_ts = int(end_time.timestamp())

            # 시간 범위에 따라 step 조정 (큰 step으로 데이터 포인트 감소)
            duration_seconds = end_ts - start_ts
            if duration_seconds <= 300:  # 5분 이하
                step = "10s"
            elif duration_seconds <= 900:  # 15분 이하
                step = "30s"
            elif duration_seconds <= 3600:  # 1시간 이하
                step = "1m"
            elif duration_seconds <= 21600:  # 6시간 이하
                step = "2m"
            else:  # 6시간 초과
                step = "5m"

            # 특징 인덱스가 지정된 경우 해당 특징만, 아니면 첫 번째 특징 (대표)
            features = self.SUBSYSTEM_FEATURES.get(subsystem, ['satellite_battery_voltage'])
            if feature_index is not None and 0 <= feature_index < len(features):
                metric_name = features[feature_index]
            else:
                metric_name = features[0]  # 대표 특징

            # ★ 병렬 쿼리 최적화: 3개 쿼리를 동시 실행 ★
            import concurrent.futures

            # 예측값 쿼리
            if feature_index is not None:
                pred_query = f'inference_prediction_feature{{satellite_id="{satellite_id}",subsystem="{subsystem}",feature_index="{feature_index}"}}'
            else:
                pred_query = f'inference_prediction_mean{{satellite_id="{satellite_id}",subsystem="{subsystem}"}}'

            # 3개의 독립적인 쿼리
            queries = {
                'actual': f'{metric_name}{{satellite_id="{satellite_id}"}}',
                'predicted': pred_query,
                'anomaly': f'inference_anomaly_score{{satellite_id="{satellite_id}",subsystem="{subsystem}"}}'
            }

            def fetch_metric(query_type_query):
                query_type, query = query_type_query
                params = {
                    "query": query,
                    "start": start_ts,
                    "end": end_ts,
                    "step": step
                }
                try:
                    # 시간 범위에 따라 타임아웃 동적 조정
                    timeout = min(10, max(3, duration_seconds / 3600))  # 3-10초
                    response = requests.get(self.range_query_url, params=params, timeout=timeout)
                    if response.ok:
                        data = response.json()
                        if data.get("status") == "success":
                            return query_type, data.get("data", {}).get("result", [])
                except Exception as e:
                    logger.error(f"Query {query_type} failed: {e}")
                return query_type, []

            # 병렬 실행 (타임아웃 15초로 증가)
            result = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {executor.submit(fetch_metric, (k, v)): k for k, v in queries.items()}
                for future in concurrent.futures.as_completed(futures, timeout=15):
                    try:
                        query_type, data = future.result()
                        result[query_type] = data
                    except Exception as e:
                        logger.error(f"Parallel query error: {e}")

            # 병렬 쿼리 결과 처리
            from collections import defaultdict
            actual_dict = {}
            pred_dict = defaultdict(list)
            score_dict = {}

            # Actual values
            for series in result.get('actual', []):
                for v in series.get('values', []):
                    actual_dict[v[0]] = float(v[1])

            # Predicted values
            for series in result.get('predicted', []):
                for v in series.get('values', []):
                    pred_dict[v[0]].append(float(v[1]))

            # Anomaly scores
            for series in result.get('anomaly', []):
                for v in series.get('values', []):
                    score_dict[v[0]] = float(v[1])

            # 예측값 평균 계산
            pred_avg_dict = {ts: sum(vals)/len(vals) for ts, vals in pred_dict.items()}

            # 데이터 포인트 생성 (actual 기준)
            data_points = []
            for timestamp, actual_value in sorted(actual_dict.items()):
                data_points.append({
                    'timestamp': datetime.fromtimestamp(timestamp).isoformat(),
                    'actual_value': actual_value,
                    'predicted_value': pred_avg_dict.get(timestamp),
                    'anomaly_score': score_dict.get(timestamp)
                })

            logger.info(f"Retrieved {len(data_points)} data points for {satellite_id}/{subsystem} (parallel optimized)")
            return data_points

        except Exception as e:
            logger.error(f"Error getting anomaly score trend: {e}")
            return []

    def get_subsystem_features(self, subsystem: str) -> List[Dict[str, Any]]:
        """서브시스템의 특징 목록 반환"""
        feature_names = {
            'eps': [
                'Battery Voltage', 'Battery SOC', 'Battery Current', 'Battery Temp',
                'Solar Panel 1 Voltage', 'Solar Panel 1 Current', 'Solar Panel 2 Voltage',
                'Solar Panel 2 Current', 'Solar Panel 3 Voltage', 'Solar Panel 3 Current',
                'Power Consumption', 'Power Generation'
            ],
            'thermal': [
                'Battery Temp', 'OBC Temp', 'Comm Temp', 'Payload Temp',
                'Solar Panel Temp', 'External Temp'
            ],
            'aocs': [
                'Gyro X', 'Gyro Y', 'Gyro Z', 'Sun Angle', 'Mag X', 'Mag Y', 'Mag Z',
                'Wheel 1 RPM', 'Wheel 2 RPM', 'Wheel 3 RPM', 'Altitude', 'Velocity'
            ],
            'comm': [
                'RSSI', 'Data Backlog', 'Last Contact'
            ]
        }

        names = feature_names.get(subsystem, [])
        return [{'index': i, 'name': name} for i, name in enumerate(names)]


# 싱글톤 인스턴스
victoria_client = VictoriaMetricsClient()
