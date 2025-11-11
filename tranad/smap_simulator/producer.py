# -*- coding: utf-8 -*-
"""
SMAP 데이터셋을 Kafka로 스트리밍하는 시뮬레이터

지정된 SMAP 채널의 test.npy 데이터를 읽어 Kafka 토픽으로 전송합니다.
사용자는 위성(토픽), 채널 ID(메시지 키), 반복 횟수를 지정할 수 있습니다.

CLI 예시:
  python smap_simulator/producer.py --kafka localhost:9092 --satellite SMAP --chan-id P-1 --repetitions 3
"""
import argparse
import json
import time
import uuid
from datetime import datetime
import numpy as np
from confluent_kafka import Producer
import os

class SmapKafkaSimulator:
    """SMAP 데이터셋 Kafka 스트리밍 시뮬레이터"""

    def __init__(self, kafka_servers: str):
        """
        시뮬레이터를 초기화하고 Kafka Producer를 설정합니다.

        Args:
            kafka_servers (str): 접속할 Kafka 브로커 서버 목록.
        """
        self.kafka_conf = {
            'bootstrap.servers': kafka_servers,
            'client.id': f'smap-sim-{uuid.uuid4().hex[:6]}'
        }
        self.producer = Producer(self.kafka_conf)
        print(f"[*] Kafka Producer initialized for servers: {kafka_servers}")

    def load_data(self, chan_id: str) -> np.ndarray:
        """
        전처리된 SMAP 테스트 데이터를 로드합니다.

        Args:
            chan_id (str): 로드할 채널 ID (e.g., 'P-1').

        Returns:
            np.ndarray: 로드된 테스트 데이터. 데이터가 없으면 None을 반환합니다.
        """
        data_path = os.path.join('processed', 'SMAP', f'{chan_id}_test.npy')
        print(f"[*] Loading data from: {data_path}")
        if not os.path.exists(data_path):
            print(f"[ERROR] Data file not found: {data_path}")
            return None
        
        try:
            data = np.load(data_path)
            print(f"[*] Data loaded successfully. Shape: {data.shape}")
            return data
        except Exception as e:
            print(f"[ERROR] Failed to load numpy file: {e}")
            return None

    def stream_data(self, satellite_topic: str, chan_id: str, data: np.ndarray, repetitions: int, delay: float):
        """
        로드된 데이터를 Kafka로 스트리밍합니다.

        Args:
            satellite_topic (str): 데이터를 전송할 Kafka 토픽.
            chan_id (str): 메시지 키로 사용될 채널 ID.
            data (np.ndarray): 전송할 데이터.
            repetitions (int): 전체 데이터셋 전송을 반복할 횟수.
            delay (float): 각 메시지 전송 사이의 대기 시간 (초).
        """
        num_records = data.shape[0]
        num_features = data.shape[1]
        print(f"[*] Starting data streaming...")
        print(f"    - Topic: {satellite_topic}")
        print(f"    - Key (Partitioning): {chan_id}")
        print(f"    - Repetitions: {repetitions}")
        print(f"    - Records per repetition: {num_records}")
        print(f"    - Delay between records: {delay}s")

        for rep in range(repetitions):
            print(f"\n--- Repetition {rep + 1}/{repetitions} ---")
            for i, row in enumerate(data):
                message = {
                    'timestamp': datetime.now().isoformat(),
                    'satellite': satellite_topic,
                    'chan_id': chan_id,
                    'repetition': rep + 1,
                    'record_index': i + 1,
                    'total_records': num_records,
                    'values': [float(v) for v in row] # np.float32를 python float으로 변환
                }

                try:
                    self.producer.produce(
                        topic=satellite_topic,
                        key=str(chan_id).encode('utf-8'),
                        value=json.dumps(message).encode('utf-8')
                    )
                    self.producer.poll(0)

                    if (i + 1) % 100 == 0 or (i + 1) == num_records:
                        print(f"    Sent {i + 1}/{num_records} records", end='\r')
                    
                    time.sleep(delay)

                except BufferError:
                    print(f"\n[ERROR] Kafka producer queue is full. Flushing...")
                    self.producer.flush()
                except Exception as e:
                    print(f"\n[ERROR] Kafka error: {e}")

            print(f"\n[*] Flushed Kafka producer for repetition {rep + 1}.")
            self.producer.flush()

        print("\n[SUCCESS] All data streaming repetitions completed.")


def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description='SMAP Dataset Kafka Streaming Simulator')
    parser.add_argument('--kafka', type=str, default='localhost:9092',
                        help='Kafka bootstrap servers (default: localhost:9092)')
    parser.add_argument('--satellite', type=str, default='SMAP',
                        help='Satellite name, used as Kafka Topic (default: SMAP)')
    parser.add_argument('--chan-id', type=str, required=True,
                        help='Channel ID to stream (e.g., P-1, A-4, etc.)')
    parser.add_argument('--repetitions', type=int, default=1,
                        help='Number of times to repeat streaming the entire dataset (default: 1)')
    parser.add_argument('--delay', type=float, default=0.1,
                        help='Delay in seconds between each message (default: 0.1)')
    
    args = parser.parse_args()

    # 시뮬레이터 생성 및 실행
    simulator = SmapKafkaSimulator(kafka_servers=args.kafka)
    smap_data = simulator.load_data(chan_id=args.chan_id)

    if smap_data is not None:
        simulator.stream_data(
            satellite_topic=args.satellite,
            chan_id=args.chan_id,
            data=smap_data,
            repetitions=args.repetitions,
            delay=args.delay
        )

if __name__ == '__main__':
    main()
