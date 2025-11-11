#!/usr/bin/env python3
"""
스케줄링 서비스 Consumer (예시)

공용 토픽을 구독하여 자원 스케줄링 수행

구독 토픽:
  - telemetry.public.eps  (전력 예측)
  - telemetry.public.aocs (자세 계획)

Consumer Group: scheduling-group (이상탐지와 독립)
"""

import json
import logging
import signal
from collections import deque, defaultdict
from typing import Dict, Any

from confluent_kafka import Consumer, KafkaError

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('scheduling')

# Global
running = True


def signal_handler(signum, frame):
    global running
    running = False


class SchedulingConsumer:
    """
    스케줄링 서비스 Consumer

    특징:
      - 같은 telemetry.public.eps 토픽을 구독 (이상탐지와 동일)
      - 다른 Consumer Group (scheduling-group)
      - 독립적인 처리 로직 (전력 예측, 자세 계획)
    """

    def __init__(self):
        consumer_conf = {
            'bootstrap.servers': 'kafka:9092',
            'group.id': 'scheduling-group',  # 독립 그룹!
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True
        }
        self.consumer = Consumer(consumer_conf)

        # 스케줄링은 EPS와 AOCS만 필요
        self.consumer.subscribe([
            'telemetry.public.eps',
            'telemetry.public.aocs'
        ])

        # 버퍼 (스케줄링은 더 긴 윈도우 사용 가능)
        self.windows = defaultdict(lambda: deque(maxlen=100))

        # 통계
        self.stats = defaultdict(int)

        logger.info("=" * 80)
        logger.info("Scheduling Consumer Started")
        logger.info("=" * 80)
        logger.info("Subscribed Topics: telemetry.public.eps, telemetry.public.aocs")
        logger.info("Consumer Group: scheduling-group")
        logger.info("Window Size: 100 (스케줄링 전용)")
        logger.info("=" * 80)

    def process_message(self, message: Dict[str, Any]):
        """메시지 처리"""
        try:
            satellite_id = message.get('satellite_id')
            subsystem = message.get('subsystem')
            features = message.get('features')

            if not all([satellite_id, subsystem, features]):
                return

            # 스케줄링 로직
            key = (satellite_id, subsystem)
            self.windows[key].append(features)

            self.stats['received'] += 1

            # 스케줄링 전용 로직 (예: 100개마다 자원 최적화)
            if len(self.windows[key]) >= 100:
                if (self.stats['received'] % 50) == 0:
                    self.optimize_resources(satellite_id, subsystem)

        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)

    def optimize_resources(self, satellite_id: str, subsystem: str):
        """자원 최적화 (스케줄링 로직)"""
        logger.info(f"[{satellite_id}/{subsystem}] Running resource optimization...")

        # 여기에 스케줄링 알고리즘 구현
        # - 전력 예측
        # - 자세 계획
        # - 통신 윈도우 최적화
        # etc.

        self.stats['optimizations'] += 1

    def run(self):
        """메인 루프"""
        global running

        logger.info("Scheduling Consumer ready...")

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

        except KeyboardInterrupt:
            logger.info("Interrupted")

        finally:
            logger.info(f"Stats: {dict(self.stats)}")
            self.consumer.close()


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    consumer = SchedulingConsumer()
    consumer.run()


if __name__ == '__main__':
    main()
