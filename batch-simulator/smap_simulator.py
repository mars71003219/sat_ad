#!/usr/bin/env python3
"""
SMAP 기반 위성 텔레메트리 시뮬레이터

실제 NASA SMAP 데이터셋의 test.npy 파일을 사용하여
5개 위성의 7개 서브시스템 데이터를 Kafka로 전송합니다.

사용법:
  python smap_simulator.py --kafka kafka:9092 --satellites 5 --loops 3
"""

import json
import time
import argparse
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
from confluent_kafka import Producer
from typing import Dict, List


class SMAPSatelliteSimulator:
    """SMAP 데이터 기반 위성 시뮬레이터"""

    # 서브시스템 매핑
    SUBSYSTEMS = {
        'E': 'EPS',      # 전력계 (Electric Power System)
        'A': 'ACS',      # 자세제어계 (Attitude Control System)
        'F': 'FSW',      # 비행소프트웨어 (Flight Software)
        'T': 'TCS',      # 열제어계 (Thermal Control System)
        'D': 'Data',     # 원격측정명령계 (Data Handling)
        'S': 'SS',       # 구조계 (Structure System)
        'P': 'PS'        # 추진계 (Propulsion System)
    }

    def __init__(self, satellite_id: str, data_dir: Path, kafka_servers: str, kafka_topic: str = 'satellite-telemetry-raw'):
        self.satellite_id = satellite_id
        self.data_dir = data_dir
        self.kafka_topic = kafka_topic

        # Kafka Producer 설정
        conf = {
            'bootstrap.servers': kafka_servers,
            'client.id': f'smap-sim-{satellite_id}'
        }
        self.producer = Producer(conf)

        # 데이터 로드
        self.subsystem_data = self._load_subsystem_data()

        print(f"[{self.satellite_id}] SMAP Simulator initialized")
        for subsys_code, subsys_name in self.SUBSYSTEMS.items():
            if subsys_code in self.subsystem_data:
                shape = self.subsystem_data[subsys_code].shape
                print(f"  - {subsys_name}({subsys_code}): {shape[0]} records × {shape[1]} features")

    def _load_subsystem_data(self) -> Dict[str, np.ndarray]:
        """서브시스템별 test.npy 파일 로드"""
        subsystem_data = {}

        for subsys_code, subsys_name in self.SUBSYSTEMS.items():
            # SMAP 파일 패턴: A-1_test.npy, E-1_test.npy, ...
            # sat1/A-1_test.npy, sat2/A-2_test.npy 등
            sat_num = self.satellite_id.replace('sat', '')

            # 각 서브시스템별 파일 찾기
            pattern = f"{subsys_code}-{sat_num}_test.npy"
            if subsys_code == 'S':
                # S는 모든 위성이 S-1 공유
                pattern = "S-1_test.npy"

            file_path = self.data_dir / pattern

            # 파일이 없으면 다른 번호 시도 (fallback)
            if not file_path.exists() and subsys_code != 'S':
                # 1부터 7까지 시도
                for fallback_num in range(1, 8):
                    fallback_pattern = f"{subsys_code}-{fallback_num}_test.npy"
                    fallback_path = self.data_dir / fallback_pattern
                    if fallback_path.exists():
                        print(f"[{self.satellite_id}] Using fallback: {fallback_pattern} (original: {pattern})")
                        pattern = fallback_pattern
                        file_path = fallback_path
                        break

            if file_path.exists():
                data = np.load(file_path)
                subsystem_data[subsys_code] = data
                print(f"[{self.satellite_id}] Loaded {pattern}: shape {data.shape}")
            else:
                print(f"[{self.satellite_id}] Warning: {pattern} not found")

        return subsystem_data

    def send_telemetry(self, loops: int = 1, delay_ms: int = 1000):
        """
        텔레메트리 데이터를 Kafka로 전송

        Args:
            loops: 반복 재생 횟수
            delay_ms: 레코드 간 딜레이 (밀리초, 기본값 1000ms = 1초)
        """
        if not self.subsystem_data:
            print(f"[{self.satellite_id}] No data to send")
            return

        # 모든 서브시스템 중 가장 짧은 길이 찾기
        min_length = min(data.shape[0] for data in self.subsystem_data.values())

        print(f"\n[{self.satellite_id}] Starting telemetry transmission")
        print(f"  - Records per loop: {min_length}")
        print(f"  - Loops: {loops}")
        print(f"  - Total records: {min_length * loops}")
        print(f"  - Interval: {delay_ms}ms")
        print(f"  - Duration: ~{min_length * loops * delay_ms / 1000 / 60:.1f} minutes")

        delay_sec = delay_ms / 1000.0
        start_time = datetime.now(timezone.utc)

        for loop in range(loops):
            print(f"\n[{self.satellite_id}] Loop {loop + 1}/{loops}")

            for idx in range(min_length):
                # 현재 타임스탬프 (1초 간격)
                current_time = start_time + timedelta(seconds=(loop * min_length + idx))

                # 모든 서브시스템 데이터 수집
                telemetry = {
                    'satellite_id': self.satellite_id,
                    'timestamp': current_time.isoformat(),
                    'loop': loop + 1,
                    'record_index': idx,
                    'subsystems': {}
                }

                # 각 서브시스템 데이터 추가
                for subsys_code, subsys_name in self.SUBSYSTEMS.items():
                    if subsys_code in self.subsystem_data:
                        # numpy 배열에서 해당 인덱스의 데이터 추출
                        data = self.subsystem_data[subsys_code][idx].tolist()
                        telemetry['subsystems'][subsys_name] = {
                            'code': subsys_code,
                            'features': data,
                            'num_features': len(data)
                        }

                # Kafka 전송
                try:
                    self.producer.produce(
                        self.kafka_topic,
                        key=self.satellite_id.encode('utf-8'),
                        value=json.dumps(telemetry).encode('utf-8')
                    )
                    self.producer.poll(0)

                    # 진행상황 출력 (100개마다)
                    if (idx + 1) % 100 == 0:
                        progress = (loop * min_length + idx + 1) / (loops * min_length) * 100
                        print(f"[{self.satellite_id}] Progress: {progress:.1f}% ({loop * min_length + idx + 1}/{loops * min_length})")

                except Exception as e:
                    print(f"[{self.satellite_id}] Kafka error at record {idx}: {e}")

                # 딜레이
                time.sleep(delay_sec)

        # 모든 메시지 전송 완료 대기
        self.producer.flush()

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        print(f"\n[{self.satellite_id}] Transmission complete")
        print(f"  - Total records sent: {min_length * loops}")
        print(f"  - Elapsed time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")


def run_multi_satellite_simulation(
    num_satellites: int = 5,
    kafka_servers: str = 'localhost:9092',
    loops: int = 1,
    delay_ms: int = 1000,
    data_base_dir: str = './data'
):
    """
    다중 위성 시뮬레이션

    Args:
        num_satellites: 위성 개수 (1~5)
        kafka_servers: Kafka 브로커 주소
        loops: 각 위성의 반복 재생 횟수
        delay_ms: 레코드 간 딜레이 (밀리초)
        data_base_dir: 데이터 베이스 디렉토리
    """
    print("=" * 80)
    print("SMAP 기반 위성 텔레메트리 시뮬레이터")
    print("=" * 80)
    print(f"위성 개수:        {num_satellites}")
    print(f"반복 재생:        {loops}")
    print(f"레코드 간격:      {delay_ms}ms")
    print(f"Kafka:            {kafka_servers}")
    print(f"데이터 디렉토리:  {data_base_dir}")
    print("=" * 80)
    print()

    # 데이터 디렉토리 확인
    base_path = Path(data_base_dir)
    if not base_path.exists():
        print(f"Error: Data directory not found: {data_base_dir}")
        return

    # 위성 시뮬레이터 생성
    simulators = []
    for i in range(1, num_satellites + 1):
        sat_id = f"sat{i}"
        sat_data_dir = base_path / sat_id

        if not sat_data_dir.exists():
            print(f"Warning: Data directory not found for {sat_id}: {sat_data_dir}")
            continue

        simulator = SMAPSatelliteSimulator(sat_id, sat_data_dir, kafka_servers)
        simulators.append(simulator)

    if not simulators:
        print("Error: No valid simulators created")
        return

    print(f"\nInitialized {len(simulators)} satellite simulators\n")

    # 모든 위성 동시 전송 시작
    import threading

    threads = []
    for simulator in simulators:
        thread = threading.Thread(
            target=simulator.send_telemetry,
            args=(loops, delay_ms)
        )
        threads.append(thread)
        thread.start()

    # 모든 스레드 완료 대기
    for thread in threads:
        thread.join()

    print("\n" + "=" * 80)
    print("전체 시뮬레이션 완료")
    print("=" * 80)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SMAP-based Satellite Telemetry Simulator')
    parser.add_argument('--kafka', type=str, default='localhost:9092',
                        help='Kafka bootstrap servers (default: localhost:9092)')
    parser.add_argument('--satellites', type=int, default=5,
                        help='Number of satellites (1-5, default: 5)')
    parser.add_argument('--loops', type=int, default=1,
                        help='Number of loops to replay data (default: 1)')
    parser.add_argument('--delay', type=int, default=1000,
                        help='Delay between records in milliseconds (default: 1000)')
    parser.add_argument('--data-dir', type=str, default='./data',
                        help='Base data directory containing sat1~sat5 folders (default: ./data)')

    args = parser.parse_args()

    # 위성 개수 검증
    if args.satellites < 1 or args.satellites > 5:
        print("Error: Number of satellites must be between 1 and 5")
        exit(1)

    run_multi_satellite_simulation(
        num_satellites=args.satellites,
        kafka_servers=args.kafka,
        loops=args.loops,
        delay_ms=args.delay,
        data_base_dir=args.data_dir
    )
