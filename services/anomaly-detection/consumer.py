#!/usr/bin/env python3
"""
이상탐지 서비스 Consumer

공용 토픽을 구독하여 이상탐지 추론 수행

구독 토픽:
  - telemetry.public.eps
  - telemetry.public.aocs
  - telemetry.public.fsw
  - telemetry.public.thermal
  - telemetry.public.data
  - telemetry.public.struct
  - telemetry.public.propulsion

Consumer Group: anomaly-detection-group
"""

import json
import logging
import signal
import sys
import os
from collections import deque, defaultdict
from typing import Dict, List, Any

sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from confluent_kafka import Consumer, KafkaError
from celery import Celery
from shared.config.settings import settings

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('anomaly-detection')

# Kafka 설정
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')

# 구독할 서브시스템 (7개 전체)
SUBSCRIBED_SUBSYSTEMS = [
    'telemetry.public.eps',
    'telemetry.public.aocs',
    'telemetry.public.fsw',
    'telemetry.public.thermal',
    'telemetry.public.data',
    'telemetry.public.struct',
    'telemetry.public.propulsion'
]

# 슬라이딩 윈도우 설정
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', '30'))
STRIDE = int(os.getenv('STRIDE', '10'))

# Celery
celery_app = Celery(
    "anomaly_detection",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Global
running = True


def signal_handler(signum, frame):
    global running
    running = False


class AnomalyDetectionConsumer:
    """
    이상탐지 서비스 Consumer

    특징:
      - 공용 토픽 구독 (다른 서비스와 독립)
      - 자체 윈도우 로직 (30개 레코드)
      - Celery로 추론 작업 전송
    """

    def __init__(self):
        # Consumer 설정
        consumer_conf = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'group.id': 'anomaly-detection-group',  # 독립 그룹
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True
        }
        self.consumer = Consumer(consumer_conf)
        self.consumer.subscribe(SUBSCRIBED_SUBSYSTEMS)

        # 위성별 × 서브시스템별 윈도우 버퍼
        # {(satellite_id, subsystem): deque([...])}
        self.windows = defaultdict(lambda: deque(maxlen=WINDOW_SIZE + STRIDE))

        # 통계
        self.stats = defaultdict(int)

        logger.info("=" * 80)
        logger.info("Anomaly Detection Consumer Started")
        logger.info("=" * 80)
        logger.info(f"Subscribed Topics: {SUBSCRIBED_SUBSYSTEMS}")
        logger.info(f"Window Size: {WINDOW_SIZE}")
        logger.info(f"Stride: {STRIDE}")
        logger.info(f"Consumer Group: anomaly-detection-group")
        logger.info("=" * 80)

    def process_message(self, message: Dict[str, Any]):
        """메시지 처리"""
        try:
            satellite_id = message.get('satellite_id')
            subsystem = message.get('subsystem')
            features = message.get('features')

            if not all([satellite_id, subsystem, features]):
                return

            # 윈도우 버퍼에 추가
            key = (satellite_id, subsystem)
            record = {
                'timestamp': message.get('timestamp'),
                'features': features
            }
            self.windows[key].append(record)

            self.stats['received'] += 1

            # 슬라이딩 윈도우 체크
            if len(self.windows[key]) >= WINDOW_SIZE:
                if (self.stats['received'] % STRIDE) == 0:
                    self.trigger_inference(satellite_id, subsystem)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            self.stats['errors'] += 1

    def trigger_inference(self, satellite_id: str, subsystem: str):
        """추론 트리거"""
        try:
            key = (satellite_id, subsystem)
            window_records = list(self.windows[key])[:WINDOW_SIZE]

            if len(window_records) < WINDOW_SIZE:
                return

            # 특징 추출
            window_features = [r['features'] for r in window_records]

            # Celery 작업 전송
            task_id = f"{satellite_id}_{subsystem}_{self.stats['inferences']}"

            celery_app.send_task(
                'analysis_worker.tasks.run_inference',
                kwargs={
                    'satellite_id': satellite_id,
                    'subsystem': subsystem,
                    'window_features': window_features,
                    'window_start_time': window_records[0]['timestamp'],
                    'window_end_time': window_records[-1]['timestamp'],
                    'service': 'anomaly-detection'
                },
                task_id=task_id,
                queue='inference'
            )

            self.stats['inferences'] += 1

            if self.stats['inferences'] % 10 == 0:
                logger.info(
                    f"[{satellite_id}/{subsystem}] "
                    f"Triggered {self.stats['inferences']} inferences"
                )

        except Exception as e:
            logger.error(f"Error triggering inference: {e}", exc_info=True)
            self.stats['errors'] += 1

    def run(self):
        """메인 루프"""
        global running

        logger.info("Anomaly Detection Consumer ready, waiting for messages...")

        try:
            while running:
                msg = self.consumer.poll(1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        logger.error(f"Consumer error: {msg.error()}")
                    continue

                try:
                    data = json.loads(msg.value().decode('utf-8'))
                    self.process_message(data)

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    self.stats['errors'] += 1

        except KeyboardInterrupt:
            logger.info("Interrupted by user")

        finally:
            self.shutdown()

    def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down Anomaly Detection Consumer...")

        logger.info("=" * 80)
        logger.info("Final Statistics")
        logger.info("=" * 80)
        logger.info(f"Messages Received:  {self.stats['received']}")
        logger.info(f"Inferences Triggered: {self.stats['inferences']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info("=" * 80)

        self.consumer.close()
        logger.info("Shutdown complete")


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    consumer = AnomalyDetectionConsumer()
    consumer.run()


if __name__ == '__main__':
    main()
