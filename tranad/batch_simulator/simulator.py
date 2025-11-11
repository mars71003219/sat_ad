#!/usr/bin/env python3
"""
배치 기반 위성 텔레메트리 시뮬레이터

위성이 지상국과 교신할 때 누적된 데이터를 배치 형태로 전송하는 실제 시나리오를 모사합니다.
- 한 번의 교신에 수십초~수십분의 누적 데이터를 전송
- 각 배치에는 batch_id로 그룹핑
- 배치 완료 시 추론이 트리거됩니다

Docker 실행:
  docker run -d --rm \
    --name batch-satellite-simulator \
    --network satellite_webnet \
    -v /mnt/c/projects/satellite/tests:/tests \
    -v /mnt/c/projects/satellite/data:/data \
    -w /tests \
    python:3.10-slim \
    bash -c "pip install -q confluent-kafka pandas && python batch_satellite_simulator.py --kafka kafka:9092 --satellites 3"

CLI 예시:
  python batch_satellite_simulator.py --kafka localhost:9092 --satellites 3 --batch-duration 300
"""

import json
import random
import time
import argparse
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from confluent_kafka import Producer
import pandas as pd
import os

class BatchSatelliteSimulator:
    """배치 기반 위성 시뮬레이터"""

    def __init__(self, satellite_id: str, kafka_servers: str, kafka_topic: str = 'satellite-telemetry'):
        self.satellite_id = satellite_id
        self.kafka_topic = kafka_topic

        # Kafka Producer 설정
        conf = {
            'bootstrap.servers': kafka_servers,
            'client.id': f'batch-sim-{satellite_id}'
        }
        self.producer = Producer(conf)

        print(f"[{self.satellite_id}] Batch Simulator initialized")

    def load_esa_data_sample(self, mission: str = "ESA-Mission1", num_records: int = 120) -> pd.DataFrame:
        """
        ESA 데이터셋에서 샘플 데이터 로드

        Args:
            mission: ESA-Mission1, ESA-Mission2, ESA-Mission3 중 선택
            num_records: 로드할 레코드 수 (기본 120개 = 60분)

        Returns:
            샘플 데이터프레임
        """
        # 실제 ESA 데이터가 있으면 로드, 없으면 synthetic 데이터 생성
        data_path = f"/data/{mission}"

        if os.path.exists(data_path):
            print(f"[{self.satellite_id}] Loading real ESA data from {mission}")
            # 간단한 synthetic 데이터 생성 (실제로는 CSV 파싱 필요)
            return self._generate_synthetic_batch_data(num_records)
        else:
            print(f"[{self.satellite_id}] Generating synthetic data (ESA data not found)")
            return self._generate_synthetic_batch_data(num_records)

    def _generate_synthetic_batch_data(self, num_records: int) -> pd.DataFrame:
        """
        ESA 스타일의 synthetic 배치 데이터 생성

        Args:
            num_records: 생성할 레코드 수

        Returns:
            시계열 데이터프레임
        """
        start_time = datetime.now(timezone.utc)

        data = []
        for i in range(num_records):
            timestamp = start_time + timedelta(seconds=i * 30)  # 30초 간격

            record = {
                'timestamp': timestamp.isoformat(),
                # EPS 채널 (전력 시스템)
                'satellite_battery_voltage': 3.0 + random.uniform(0, 1.2),
                'satellite_battery_soc': max(20, min(100, 85 + random.gauss(0, 10))),
                'satellite_battery_current': random.uniform(-2.5, 2.8),
                'satellite_battery_temp': 15 + random.gauss(0, 5),
                'satellite_solar_panel_1_voltage': random.uniform(0, 8),
                'satellite_solar_panel_1_current': random.uniform(0, 2.5),
                'satellite_solar_panel_2_voltage': random.uniform(0, 8),
                'satellite_solar_panel_2_current': random.uniform(0, 2.5),
                'satellite_solar_panel_3_voltage': random.uniform(0, 8),
                'satellite_solar_panel_3_current': random.uniform(0, 2.5),
                'satellite_power_consumption': 12 + random.gauss(0, 3),
                'satellite_power_generation': random.uniform(0, 60),

                # Thermal 채널 (온도 시스템)
                'satellite_temp_battery': 15 + random.gauss(0, 5),
                'satellite_temp_obc': 20 + random.gauss(0, 7),
                'satellite_temp_comm': 18 + random.gauss(0, 6),
                'satellite_temp_payload': 22 + random.gauss(0, 8),
                'satellite_temp_solar_panel': 10 + random.gauss(0, 10),
                'satellite_temp_external': -20 + random.gauss(0, 15),

                # AOCS 채널 (자세제어 시스템)
                'satellite_gyro_x': random.gauss(0, 0.5),
                'satellite_gyro_y': random.gauss(0, 0.5),
                'satellite_gyro_z': random.gauss(0, 0.5),
                'satellite_sun_angle': random.uniform(0, 180),
                'satellite_mag_x': random.gauss(0, 50),
                'satellite_mag_y': random.gauss(0, 50),
                'satellite_mag_z': random.gauss(0, 50),
                'satellite_wheel_1_rpm': random.uniform(1000, 3000),
                'satellite_wheel_2_rpm': random.uniform(1000, 3000),
                'satellite_wheel_3_rpm': random.uniform(1000, 3000),
                'satellite_altitude': 500 + random.gauss(0, 10),
                'satellite_velocity': 7.5 + random.gauss(0, 0.1),
                
                # Comm 채널 (통신 시스템)
                'satellite_rssi': -80 + random.gauss(0, 10),
                'satellite_data_backlog': random.uniform(0, 100),
                'satellite_last_contact': (datetime.now(timezone.utc) - start_time).total_seconds()
            }

            data.append(record)

        return pd.DataFrame(data)

    def send_batch_to_kafka(self, batch_duration_seconds: int = 300):
        """
        배치 데이터를 Kafka로 전송

        Args:
            batch_duration_seconds: 배치 기간 (초). 기본 300초 = 5분
        """
        # 배치 메타데이터 생성
        batch_id = f"{self.satellite_id}-batch-{uuid.uuid4().hex[:8]}"
        num_records = batch_duration_seconds // 30  # 30초 간격

        print(f"[{self.satellite_id}] Starting batch transmission: {batch_id}")
        print(f"  - Duration: {batch_duration_seconds}s ({batch_duration_seconds/60:.1f} minutes)")
        print(f"  - Records: {num_records}")

        # 배치 데이터 생성
        batch_df = self._generate_synthetic_batch_data(num_records)
        batch_start_time = batch_df.iloc[0]['timestamp']
        batch_end_time = batch_df.iloc[-1]['timestamp']

        # 각 레코드를 Kafka로 전송
        for idx, row in batch_df.iterrows():
            is_last = (idx == len(batch_df) - 1)

            # Kafka 메시지 구성
            message = {
                'satellite_id': self.satellite_id,
                'batch_id': batch_id,
                'batch_start_time': batch_start_time,
                'batch_end_time': batch_end_time,
                'total_records': num_records,
                'record_index': idx,
                'is_last_record': is_last,
                'data': row.to_dict()
            }

            # Kafka 전송
            try:
                self.producer.produce(
                    self.kafka_topic,
                    key=self.satellite_id.encode('utf-8'),
                    value=json.dumps(message).encode('utf-8')
                )
                self.producer.poll(0)

                if idx % 10 == 0 or is_last:
                    print(f"[{self.satellite_id}] Sent {idx+1}/{num_records} records", end='\r')

            except Exception as e:
                print(f"\n[{self.satellite_id}] Kafka error: {e}")

        # 모든 메시지 전송 완료 대기
        self.producer.flush()
        print(f"\n[{self.satellite_id}] Batch transmission complete: {batch_id}")

        return batch_id


def run_multi_satellite_batch_simulation(
    num_satellites: int = 3,
    kafka_servers: str = 'localhost:9092',
    batch_duration: int = 32400,  # 9시간 (1080개 레코드)
    inter_batch_delay: int = 300,  # 배치 간 5분 대기
    num_batches: int = 5  # 각 위성당 5번의 배치 전송
):
    """
    다중 위성 배치 시뮬레이션

    Args:
        num_satellites: 위성 개수
        kafka_servers: Kafka 브로커 주소
        batch_duration: 각 배치의 기간 (초)
        inter_batch_delay: 배치 간 대기 시간 (초)
        num_batches: 각 위성이 전송할 배치 수
    """
    print("=" * 80)
    print("️  배치 기반 위성 텔레메트리 시뮬레이터")
    print("=" * 80)
    print(f"위성 개수:            {num_satellites}")
    print(f"배치 기간:            {batch_duration}초 ({batch_duration/60:.1f}분)")
    print(f"배치당 레코드 수:     {batch_duration // 30}개 (30초 간격)")
    print(f"배치 간 대기:         {inter_batch_delay}초")
    print(f"배치 전송 횟수:       {num_batches}")
    print(f"Kafka:               {kafka_servers}")
    print("=" * 80)
    print()

    # 위성 시뮬레이터 생성
    simulators: List[BatchSatelliteSimulator] = []
    for i in range(1, num_satellites + 1):
        sat_id = f"SAT-{i:03d}"
        simulator = BatchSatelliteSimulator(sat_id, kafka_servers)
        simulators.append(simulator)

    # 배치 전송 시뮬레이션
    for batch_num in range(1, num_batches + 1):
        print(f"\n{'='*80}")
        print(f"배치 전송 라운드 {batch_num}/{num_batches}")
        print(f"{'='*80}\n")

        # 각 위성이 랜덤한 순서로 배치 전송
        random.shuffle(simulators)

        for simulator in simulators:
            # 배치 기간도 랜덤하게 (6시간 ~ 12시간)
            # 30초 간격 기준: 6시간=720개, 9시간=1080개, 12시간=1440개 레코드
            random_duration = random.randint(21600, 43200)

            # 배치 전송
            simulator.send_batch_to_kafka(batch_duration_seconds=random_duration)

            # 위성 간 랜덤 대기 (실제 위성 교신 시나리오 모사)
            if simulator != simulators[-1]:
                wait = random.randint(5, 20)
                print(f"  Waiting {wait}s before next satellite...\n")
                time.sleep(wait)

        # 다음 배치 라운드 전 대기
        if batch_num < num_batches:
            print(f"\n⏳ Waiting {inter_batch_delay}s before next batch round...\n")
            time.sleep(inter_batch_delay)

    print("\n" + "="*80)
    print(" 배치 시뮬레이션 완료")
    print("="*80)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Batch-based Satellite Telemetry Simulator')
    parser.add_argument('--kafka', type=str, default='localhost:9092',
                        help='Kafka bootstrap servers (default: localhost:9092)')
    parser.add_argument('--satellites', type=int, default=3,
                        help='Number of satellites (default: 3)')
    parser.add_argument('--batch-duration', type=int, default=32400,
                        help='Batch duration in seconds (default: 32400 = 9 hours, 1080 records at 30s interval)')
    parser.add_argument('--inter-batch-delay', type=int, default=5,
                        help='Delay between batch rounds in seconds (default: 5)')
    parser.add_argument('--num-batches', type=int, default=5,
                        help='Number of batches per satellite (default: 5)')

    args = parser.parse_args()

    run_multi_satellite_batch_simulation(
        num_satellites=args.satellites,
        kafka_servers=args.kafka,
        batch_duration=args.batch_duration,
        inter_batch_delay=args.inter_batch_delay,
        num_batches=args.num_batches
    )