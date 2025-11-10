#!/usr/bin/env python3
"""
SMAP Entity-based Telemetry Simulator

Simulates satellite telemetry based on SMAP test dataset:
- Hierarchy: Satellite > Entity > Sensors
- Satellite: SAT-001, SAT-002, SAT-003 (each mapped to SMAP entities)
- Entity: SMAP channels (A-1, A-2, ...) representing subsystems
- Sensors: 25 dimensions per entity

Data Flow:
  SMAP Test Data → Kafka (smap-telemetry topic) → Inference Pipeline
"""

import numpy as np
import json
import time
import argparse
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any
from confluent_kafka import Producer


class SMAPSimulator:
    """
    SMAP Telemetry Simulator

    Loads SMAP test data and sends to Kafka with satellite/entity/sensor hierarchy
    """

    def __init__(
        self,
        kafka_servers: str,
        data_dir: str = '/tranad-data/processed/SMAP',
        topic: str = 'smap-telemetry'
    ):
        """
        Initialize SMAP Simulator

        Args:
            kafka_servers: Kafka bootstrap servers
            data_dir: Path to SMAP processed data directory
            topic: Kafka topic name
        """
        self.kafka_topic = topic
        self.data_dir = data_dir

        # Kafka Producer configuration
        conf = {
            'bootstrap.servers': kafka_servers,
            'client.id': 'smap-simulator',
            'linger.ms': 10,
            'batch.size': 16384
        }
        self.producer = Producer(conf)

        # Satellite to Entity mapping
        # Each satellite can have multiple entities (subsystems)
        self.satellite_entities = {
            'SAT-001': ['A-1', 'A-2', 'A-3'],
            'SAT-002': ['D-1', 'D-2', 'E-1'],
            'SAT-003': ['P-1', 'P-2', 'G-1']
        }

        # Load SMAP test data and labels
        self.entity_data: Dict[str, Dict[str, np.ndarray]] = {}
        self._load_data()

        print(f"[SMAP Simulator] Initialized")
        print(f"  Kafka: {kafka_servers}")
        print(f"  Topic: {topic}")
        print(f"  Satellites: {len(self.satellite_entities)}")
        print(f"  Total Entities: {sum(len(v) for v in self.satellite_entities.values())}")

    def _load_data(self) -> None:
        """Load SMAP test data and labels for all entities"""
        for satellite_id, entities in self.satellite_entities.items():
            for entity in entities:
                test_path = os.path.join(self.data_dir, f'{entity}_test.npy')
                labels_path = os.path.join(self.data_dir, f'{entity}_labels.npy')

                if os.path.exists(test_path) and os.path.exists(labels_path):
                    test_data = np.load(test_path)
                    labels = np.load(labels_path)

                    self.entity_data[entity] = {
                        'test': test_data,
                        'labels': labels,
                        'satellite_id': satellite_id
                    }

                    print(f"[SMAP Simulator] Loaded {entity}: "
                          f"shape={test_data.shape}, "
                          f"satellite={satellite_id}")
                else:
                    print(f"[SMAP Simulator] ✗ Data not found for {entity}")

    def _delivery_report(self, err, msg):
        """Kafka delivery callback"""
        if err is not None:
            print(f'[SMAP Simulator] Message delivery failed: {err}')

    def simulate(
        self,
        interval: int = 30,
        max_records: int = None,
        start_index: int = 0
    ) -> None:
        """
        Run simulation: send SMAP test data to Kafka

        Args:
            interval: Time interval between records (seconds)
            max_records: Maximum number of records to send (None = all)
            start_index: Starting index in the test data
        """
        if not self.entity_data:
            print("[SMAP Simulator] No data loaded, exiting")
            return

        # Find maximum test data length
        max_len = max(len(data['test']) for data in self.entity_data.values())
        if max_records:
            max_len = min(max_len, start_index + max_records)

        print(f"[SMAP Simulator] Starting simulation")
        print(f"  Interval: {interval}s")
        print(f"  Records: {start_index} to {max_len}")
        print(f"  Total timesteps: {max_len - start_index}")

        base_time = datetime.now(timezone.utc)
        records_sent = 0

        try:
            for idx in range(start_index, max_len):
                timestamp = base_time + timedelta(seconds=(idx - start_index) * interval)

                for entity, data_dict in self.entity_data.items():
                    if idx >= len(data_dict['test']):
                        continue

                    satellite_id = data_dict['satellite_id']
                    sensor_values = data_dict['test'][idx]  # shape: (25,)
                    label_values = data_dict['labels'][idx]  # shape: (25,)

                    # Create message with satellite > entity > sensor hierarchy
                    message = {
                        'satellite_id': satellite_id,
                        'entity': entity,
                        'timestamp': timestamp.isoformat(),
                        'index': int(idx),
                        'sensors': {
                            f'sensor_{i}': float(sensor_values[i])
                            for i in range(len(sensor_values))
                        },
                        'ground_truth_labels': {
                            f'sensor_{i}': int(label_values[i])
                            for i in range(len(label_values))
                        }
                    }

                    # Send to Kafka
                    self.producer.produce(
                        self.kafka_topic,
                        key=f"{satellite_id}:{entity}".encode('utf-8'),
                        value=json.dumps(message).encode('utf-8'),
                        callback=self._delivery_report
                    )

                    records_sent += 1

                # Flush every batch
                self.producer.flush()

                if (idx - start_index) % 10 == 0:
                    print(f"[SMAP Simulator] Sent timestep {idx}/{max_len} "
                          f"({records_sent} total records)")

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n[SMAP Simulator] Interrupted by user")
        finally:
            self.producer.flush()
            print(f"[SMAP Simulator] Simulation complete. Total records sent: {records_sent}")

    def simulate_continuous(self, interval: int = 30) -> None:
        """
        Continuous simulation: loop through data infinitely

        Args:
            interval: Time interval between records (seconds)
        """
        while True:
            print("[SMAP Simulator] Starting new data cycle")
            self.simulate(interval=interval)
            print("[SMAP Simulator] Cycle complete, restarting...")
            time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description='SMAP Telemetry Simulator')
    parser.add_argument(
        '--kafka',
        type=str,
        default='kafka:9092',
        help='Kafka bootstrap servers'
    )
    parser.add_argument(
        '--data-dir',
        type=str,
        default='/tranad-data/processed/SMAP',
        help='SMAP processed data directory'
    )
    parser.add_argument(
        '--topic',
        type=str,
        default='smap-telemetry',
        help='Kafka topic name'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=30,
        help='Time interval between records (seconds)'
    )
    parser.add_argument(
        '--max-records',
        type=int,
        default=None,
        help='Maximum number of records to send (default: all)'
    )
    parser.add_argument(
        '--continuous',
        action='store_true',
        help='Run in continuous mode (loop infinitely)'
    )

    args = parser.parse_args()

    # Create simulator
    simulator = SMAPSimulator(
        kafka_servers=args.kafka,
        data_dir=args.data_dir,
        topic=args.topic
    )

    # Run simulation
    if args.continuous:
        simulator.simulate_continuous(interval=args.interval)
    else:
        simulator.simulate(
            interval=args.interval,
            max_records=args.max_records
        )


if __name__ == '__main__':
    main()
