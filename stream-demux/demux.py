#!/usr/bin/env python3
"""
토픽 중심 아키텍처 - 범용 Demultiplexer

역할:
  satellite-telemetry-raw → telemetry.public.{subsystem}

특징:
  - 서비스 무관 (이상탐지, 스케줄링 등을 모름)
  - 데이터 중심 (서브시스템만 분리)
  - 확장성 (새 서비스 추가 시 코드 변경 불필요)
  - 설정 기반 (config.yaml로 라우팅 정의)

아키텍처:
  [Demux] --- telemetry.public.eps ---> [Anomaly(group=anomaly)]
          |                          \-> [Scheduling(group=sched)]
          |                          \-> [Health(group=health)]
          |
          --- telemetry.public.aocs --> [...]
          --- telemetry.public.fsw ----> [...]
"""

import json
import logging
import signal
import sys
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from confluent_kafka import Consumer, Producer, KafkaError

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag
running = True


def signal_handler(signum, frame):
    global running
    logger.info(f"Received signal {signum}, shutting down...")
    running = False


class StreamDemultiplexer:
    """
    범용 Demultiplexer - 서비스 무관, 데이터 중심
    """

    def __init__(self, config_path: str = 'config.yaml'):
        """
        Args:
            config_path: 라우팅 설정 파일 경로
        """
        # 설정 로드
        self.config = self._load_config(config_path)

        # Kafka 설정
        kafka_config = self.config.get('kafka', {})
        self.bootstrap_servers = kafka_config.get('bootstrap_servers', 'kafka:9092')
        self.input_topic = kafka_config.get('input_topic', 'satellite-telemetry-raw')

        # 라우팅 규칙
        self.routing_rules = self.config.get('routing', {})

        # Consumer
        consumer_conf = {
            'bootstrap.servers': self.bootstrap_servers,
            'group.id': 'stream-demux-group',
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True
        }
        self.consumer = Consumer(consumer_conf)
        self.consumer.subscribe([self.input_topic])

        # Producer
        producer_conf = {
            'bootstrap.servers': self.bootstrap_servers,
            'linger.ms': 10,
            'compression.type': 'snappy',
            'acks': 1
        }
        self.producer = Producer(producer_conf)

        # 통계
        self.stats = {
            'received': 0,
            'routed': 0,
            'errors': 0
        }

        logger.info("=" * 80)
        logger.info("Stream Demultiplexer (Topic-Centric Architecture)")
        logger.info("=" * 80)
        logger.info(f"Input Topic:     {self.input_topic}")
        logger.info(f"Routing Rules:   {len(self.routing_rules)} subsystems")
        for subsys, rule in self.routing_rules.items():
            logger.info(f"  {subsys:10s} → {rule['target_topic']}")
        logger.info("=" * 80)

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """설정 파일 로드"""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return self._default_config()

        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def _default_config(self) -> Dict[str, Any]:
        """기본 설정"""
        return {
            'kafka': {
                'bootstrap_servers': 'kafka:9092',
                'input_topic': 'satellite-telemetry-raw'
            },
            'routing': {
                'EPS': {'target_topic': 'telemetry.public.eps'},
                'ACS': {'target_topic': 'telemetry.public.aocs'},
                'FSW': {'target_topic': 'telemetry.public.fsw'},
                'TCS': {'target_topic': 'telemetry.public.thermal'},
                'Data': {'target_topic': 'telemetry.public.data'},
                'SS': {'target_topic': 'telemetry.public.struct'},
                'PS': {'target_topic': 'telemetry.public.propulsion'}
            }
        }

    def process_message(self, message: Dict[str, Any]) -> int:
        """
        메시지 처리 및 라우팅

        Args:
            message: 원시 텔레메트리 메시지

        Returns:
            라우팅된 메시지 수
        """
        try:
            satellite_id = message.get('satellite_id')
            subsystems = message.get('subsystems', {})

            if not satellite_id or not subsystems:
                logger.warning("Invalid message: missing satellite_id or subsystems")
                return 0

            routed_count = 0

            # 각 서브시스템 데이터를 공용 토픽으로 라우팅
            for subsys_name, subsys_data in subsystems.items():
                rule = self.routing_rules.get(subsys_name)
                if not rule:
                    logger.debug(f"No routing rule for subsystem: {subsys_name}")
                    continue

                target_topic = rule['target_topic']

                # 공용 토픽 메시지 (서비스 무관)
                public_message = {
                    # 메타데이터
                    'satellite_id': satellite_id,
                    'timestamp': message.get('timestamp'),
                    'loop': message.get('loop'),
                    'record_index': message.get('record_index'),

                    # 서브시스템 정보
                    'subsystem': subsys_name,
                    'subsystem_code': subsys_data.get('code'),

                    # 데이터 (서비스가 자유롭게 사용)
                    'features': subsys_data.get('features'),
                    'num_features': subsys_data.get('num_features'),

                    # 프로베넌스 (추적용)
                    'source_topic': self.input_topic,
                    'demux_version': '2.0-topic-centric'
                }

                # Kafka 전송 (key=satellite_id로 파티셔닝)
                self.producer.produce(
                    topic=target_topic,
                    key=satellite_id.encode('utf-8'),
                    value=json.dumps(public_message).encode('utf-8'),
                    callback=self._delivery_callback
                )
                routed_count += 1

            self.producer.poll(0)
            return routed_count

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            self.stats['errors'] += 1
            return 0

    def _delivery_callback(self, err, msg):
        """Producer 전송 콜백"""
        if err:
            logger.error(f"Delivery failed: {err}")
            self.stats['errors'] += 1
        else:
            self.stats['routed'] += 1

    def run(self):
        """메인 처리 루프"""
        global running

        logger.info("Stream Demux started, processing messages...")

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
                    self.stats['received'] += 1

                    # 라우팅
                    routed = self.process_message(data)

                    # 주기적 flush (100개마다)
                    if self.stats['received'] % 100 == 0:
                        self.producer.flush()
                        logger.info(
                            f"Processed {self.stats['received']} messages, "
                            f"routed {self.stats['routed']} subsystem messages"
                        )

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    self.stats['errors'] += 1

        except KeyboardInterrupt:
            logger.info("Interrupted by user")

        finally:
            self.shutdown()

    def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down Stream Demux...")

        # 통계
        logger.info("=" * 80)
        logger.info("Final Statistics")
        logger.info("=" * 80)
        logger.info(f"Messages Received:  {self.stats['received']}")
        logger.info(f"Messages Routed:    {self.stats['routed']}")
        logger.info(f"Routing Ratio:      {self.stats['routed'] / max(1, self.stats['received']):.1f}x")
        logger.info(f"Errors:             {self.stats['errors']}")
        logger.info("=" * 80)

        # Cleanup
        logger.info("Flushing producer...")
        self.producer.flush(timeout=10)

        logger.info("Closing consumer...")
        self.consumer.close()

        logger.info("Shutdown complete")


def main():
    """메인 엔트리포인트"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 설정 파일 경로
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'config.yaml'

    # Demux 실행
    demux = StreamDemultiplexer(config_path)
    demux.run()


if __name__ == '__main__':
    main()
