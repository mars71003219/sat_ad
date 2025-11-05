#!/usr/bin/env python3
"""
배치 완료 기반 추론 트리거

Kafka에서 위성 배치 데이터를 수신하여:
1. 각 배치의 데이터를 메모리에 누적
2. is_last_record=true 메시지를 받으면 배치 완료로 인식
3. 슬라이딩 윈도우로 추론 트리거 (window_size=30, stride=10)
"""

import os
import sys
import json
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from confluent_kafka import Consumer, KafkaError, KafkaException
from celery import Celery
from shared.config.settings import settings

# Logging 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Celery 설정
celery_app = Celery(
    "inference_trigger",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Kafka 설정
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
KAFKA_TOPIC_TELEMETRY = os.getenv('KAFKA_TOPIC_TELEMETRY', 'satellite-telemetry')

# 추론 설정
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', '30'))  # 슬라이딩 윈도우 크기
STRIDE = int(os.getenv('STRIDE', '10'))  # 슬라이딩 스트라이드
FORECAST_HORIZON = int(os.getenv('FORECAST_HORIZON', '10'))  # 예측 스텝

# 서브시스템별 특징 정의
SUBSYSTEM_FEATURES = {
    'eps': [
        'satellite_battery_voltage',
        'satellite_battery_soc',
        'satellite_battery_current',
        'satellite_battery_temp',
        'satellite_solar_panel_1_voltage',
        'satellite_solar_panel_1_current',
        'satellite_solar_panel_2_voltage',
        'satellite_solar_panel_2_current',
        'satellite_solar_panel_3_voltage',
        'satellite_solar_panel_3_current',
        'satellite_power_consumption',
        'satellite_power_generation'
    ],
    'thermal': [
        'satellite_temp_battery',
        'satellite_temp_obc',
        'satellite_temp_comm',
        'satellite_temp_payload',
        'satellite_temp_solar_panel',
        'satellite_temp_external'
    ],
    'aocs': [
        'satellite_gyro_x',
        'satellite_gyro_y',
        'satellite_gyro_z',
        'satellite_sun_angle',
        'satellite_mag_x',
        'satellite_mag_y',
        'satellite_mag_z',
        'satellite_wheel_1_rpm',
        'satellite_wheel_2_rpm',
        'satellite_wheel_3_rpm',
        'satellite_altitude',
        'satellite_velocity'
    ],
    'comm': [
        'satellite_rssi',
        'satellite_data_backlog',
        'satellite_last_contact'
    ]
}


class BatchInferenceTrigger:
    """배치 완료 기반 추론 트리거"""

    def __init__(self):
        """
        배치 단위로 데이터를 수집하고, 배치 완료 시 슬라이딩 윈도우 추론을 트리거합니다.
        """
        # 배치 버퍼: {batch_id: [record1, record2, ...]}
        self.batch_buffers = defaultdict(list)

        # 배치 메타데이터: {batch_id: metadata}
        self.batch_metadata = {}

        # Kafka Consumer 초기화
        self.consumer = self._create_consumer()

        logger.info(f"Batch Inference Trigger initialized")
        logger.info(f"Kafka: {KAFKA_BOOTSTRAP_SERVERS}, Topic: {KAFKA_TOPIC_TELEMETRY}")
        logger.info(f"Window Size: {WINDOW_SIZE}, Stride: {STRIDE}")

    def _create_consumer(self):
        """Confluent Kafka Consumer 생성"""
        conf = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'group.id': 'batch-inference-trigger-group',
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True,
            'session.timeout.ms': 6000,
            'max.poll.interval.ms': 300000
        }
        consumer = Consumer(conf)
        consumer.subscribe([KAFKA_TOPIC_TELEMETRY])
        return consumer

    def process_message(self, message: Dict[str, Any]):
        """
        Kafka 메시지 처리

        Args:
            message: 배치 텔레메트리 메시지
        """
        try:
            batch_id = message.get('batch_id')
            satellite_id = message.get('satellite_id')
            record_index = message.get('record_index')
            is_last = message.get('is_last_record', False)
            data = message.get('data', {})

            if not batch_id or not satellite_id:
                logger.warning("Missing batch_id or satellite_id in message")
                return

            # 배치 메타데이터 저장 (첫 메시지일 때)
            if batch_id not in self.batch_metadata:
                self.batch_metadata[batch_id] = {
                    'satellite_id': satellite_id,
                    'batch_start_time': message.get('batch_start_time'),
                    'batch_end_time': message.get('batch_end_time'),
                    'total_records': message.get('total_records'),
                    'started_at': datetime.utcnow().isoformat()
                }
                logger.info(f"📦 New batch started: {batch_id} ({satellite_id})")

            # 데이터를 배치 버퍼에 추가
            self.batch_buffers[batch_id].append({
                'index': record_index,
                'data': data
            })

            logger.debug(f"[{batch_id}] Received record {record_index+1}/{message.get('total_records')}")

            # 배치 완료 확인
            if is_last:
                logger.info(f"✅ Batch complete: {batch_id} - {len(self.batch_buffers[batch_id])} records")
                self.on_batch_complete(batch_id)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    def on_batch_complete(self, batch_id: str):
        """
        배치 완료 시 호출 - 슬라이딩 윈도우 추론 트리거

        Args:
            batch_id: 완료된 배치 ID
        """
        try:
            metadata = self.batch_metadata.get(batch_id)
            records = self.batch_buffers.get(batch_id, [])

            if not metadata or not records:
                logger.error(f"Batch data not found: {batch_id}")
                return

            satellite_id = metadata['satellite_id']
            total_records = len(records)

            logger.info(f"🔍 Processing batch {batch_id}")
            logger.info(f"  - Satellite: {satellite_id}")
            logger.info(f"  - Records: {total_records}")

            # 레코드를 인덱스 순으로 정렬
            records.sort(key=lambda r: r['index'])

            # 슬라이딩 윈도우 추론 트리거
            num_windows = self.trigger_sliding_window_inference(batch_id, satellite_id, records)

            logger.info(f"🚀 Triggered {num_windows} inference windows for batch {batch_id}")

            # 메모리 정리
            del self.batch_buffers[batch_id]
            del self.batch_metadata[batch_id]

        except Exception as e:
            logger.error(f"Error on batch complete: {e}", exc_info=True)

    def trigger_sliding_window_inference(
        self,
        batch_id: str,
        satellite_id: str,
        records: List[Dict[str, Any]]
    ) -> int:
        """
        슬라이딩 윈도우로 추론 트리거

        Args:
            batch_id: 배치 ID
            satellite_id: 위성 ID
            records: 정렬된 레코드 리스트

        Returns:
            트리거된 윈도우 수
        """
        total_records = len(records)
        window_count = 0

        # 충분한 데이터가 없으면 스킵
        if total_records < WINDOW_SIZE:
            logger.warning(f"Insufficient data for inference: {total_records} < {WINDOW_SIZE}")
            return 0

        # 슬라이딩 윈도우로 추론 트리거
        # 예: total=120, window=30, stride=10
        # [0:30], [10:40], [20:50], ..., [90:120]
        for start_idx in range(0, total_records - WINDOW_SIZE + 1, STRIDE):
            end_idx = start_idx + WINDOW_SIZE
            window_records = records[start_idx:end_idx]

            # 각 서브시스템에 대해 추론 트리거
            for subsystem in SUBSYSTEM_FEATURES.keys():
                success = self.trigger_subsystem_inference(
                    batch_id=batch_id,
                    satellite_id=satellite_id,
                    subsystem=subsystem,
                    window_records=window_records,
                    window_index=window_count
                )

                if success:
                    window_count += 1

        return window_count

    def trigger_subsystem_inference(
        self,
        batch_id: str,
        satellite_id: str,
        subsystem: str,
        window_records: List[Dict[str, Any]],
        window_index: int
    ) -> bool:
        """
        서브시스템 추론 트리거

        Args:
            batch_id: 배치 ID
            satellite_id: 위성 ID
            subsystem: 서브시스템 이름
            window_records: 윈도우 레코드 리스트
            window_index: 윈도우 인덱스

        Returns:
            성공 여부
        """
        try:
            # 특징 추출 - [sequence_length, features] 형태로 구성
            required_features = SUBSYSTEM_FEATURES.get(subsystem, [])
            input_data = []  # [[feat1_t1, feat2_t1, ...], [feat1_t2, feat2_t2, ...], ...]
            input_features = required_features

            for record in window_records:
                data = record['data']
                record_features = []

                for feature in required_features:
                    value = data.get(feature)
                    if value is None:
                        logger.warning(f"Missing feature {feature} in window")
                        return False
                    record_features.append(value)

                input_data.append(record_features)

            # Celery 태스크 생성
            job_id = f"batch-{batch_id}-{subsystem}-win{window_index}-{int(time.time())}"

            task_params = {
                'job_id': job_id,
                'subsystem': subsystem,
                'model_name': f'transformer_{subsystem}',  # Triton 모델 이름과 일치
                'input_data': input_data,
                'input_features': input_features,
                'config': {
                    'sequence_length': WINDOW_SIZE,
                    'forecast_horizon': FORECAST_HORIZON
                },
                'metadata': {
                    'satellite_id': satellite_id,
                    'batch_id': batch_id,
                    'window_index': window_index,
                    'source': 'batch_trigger',
                    'trigger_reason': 'batch_complete_sliding_window',
                    'created_at': datetime.utcnow().isoformat()
                }
            }

            # Celery 태스크 전송
            celery_app.send_task(
                'analysis_server.tasks.run_subsystem_inference',
                kwargs=task_params,
                queue='inference'
            )

            logger.debug(f"Triggered inference: {job_id}")
            return True

        except Exception as e:
            logger.error(f"Error triggering inference for {subsystem}: {e}", exc_info=True)
            return False

    def run(self):
        """메인 루프: Kafka 메시지 처리"""
        logger.info("=" * 60)
        logger.info("Batch-based Inference Trigger Starting...")
        logger.info("=" * 60)

        retry_count = 0
        max_retries = 10

        while retry_count < max_retries:
            try:
                while True:
                    msg = self.consumer.poll(timeout=1.0)

                    if msg is None:
                        continue

                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            continue
                        else:
                            logger.error(f"Consumer error: {msg.error()}")
                            raise KafkaException(msg.error())

                    try:
                        data = json.loads(msg.value().decode('utf-8'))
                        self.process_message(data)
                        retry_count = 0  # 성공 시 재시도 카운트 리셋

                    except Exception as e:
                        logger.error(f"Error processing Kafka message: {e}", exc_info=True)
                        continue

            except KeyboardInterrupt:
                logger.info("Shutting down gracefully...")
                break
            except Exception as e:
                retry_count += 1
                logger.error(f"Error in main loop (retry {retry_count}/{max_retries}): {e}", exc_info=True)
                if retry_count < max_retries:
                    sleep_time = min(5 * retry_count, 30)  # 최대 30초
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                    # 컨슈머 재생성
                    try:
                        self.consumer.close()
                    except:
                        pass
                    self.consumer = self._create_consumer()
                else:
                    logger.error("Max retries reached, exiting...")
                    break

        try:
            self.consumer.close()
            logger.info("Kafka consumer closed")
        except:
            pass


if __name__ == '__main__':
    trigger = BatchInferenceTrigger()
    trigger.run()
