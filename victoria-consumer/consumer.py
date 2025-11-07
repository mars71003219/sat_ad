#!/usr/bin/env python3
"""
VictoriaMetrics Kafka Consumer
Consumes satellite telemetry data from Kafka and writes to VictoriaMetrics
"""

import json
import logging
import signal
import sys
import time
from datetime import datetime
from typing import Dict, Any

import requests
from confluent_kafka import Consumer, KafkaError, KafkaException
from dateutil import parser as date_parser

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = 'kafka:9092'
KAFKA_TOPIC_TELEMETRY = 'satellite-telemetry'
KAFKA_TOPIC_INFERENCE = 'inference-results'
KAFKA_GROUP_ID = 'victoria-consumer-group-v3'
VICTORIA_METRICS_URL = 'http://victoria-metrics:8428'
VICTORIA_WRITE_ENDPOINT = f'{VICTORIA_METRICS_URL}/api/v1/import/prometheus'

# Global flag for graceful shutdown
running = True


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global running
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    running = False


def create_kafka_consumer() -> Consumer:
    """Create and configure Kafka consumer"""
    conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'group.id': KAFKA_GROUP_ID,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': True,
        'session.timeout.ms': 6000,
        'max.poll.interval.ms': 300000
    }

    consumer = Consumer(conf)
    # Subscribe to both telemetry and inference results topics
    consumer.subscribe([KAFKA_TOPIC_TELEMETRY, KAFKA_TOPIC_INFERENCE])
    logger.info(f"Kafka consumer created, subscribed to topics: {KAFKA_TOPIC_TELEMETRY}, {KAFKA_TOPIC_INFERENCE}")
    return consumer


def parse_telemetry_message(msg_value: bytes) -> Dict[str, Any]:
    """Parse Kafka message containing satellite telemetry data"""
    try:
        data = json.loads(msg_value.decode('utf-8'))
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse message as JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Error parsing message: {e}")
        raise


def format_prometheus_metric(metric_name: str, value: float, labels: Dict[str, str], timestamp_ms: int) -> str:
    """
    Format a single metric in Prometheus exposition format
    
    Example: satellite_temperature{satellite_id="SAT-001"} 23.5 1634308800000
    """
    label_str = ','.join([f'{k}="{v}"' for k, v in labels.items()])
    return f"{metric_name}{{{label_str}}} {value} {timestamp_ms}"


def write_to_victoria_metrics(metrics: list):
    """Write metrics to VictoriaMetrics using Prometheus format"""
    if not metrics:
        return

    # Join all metrics with newlines
    payload = '\n'.join(metrics)

    try:
        response = requests.post(
            VICTORIA_WRITE_ENDPOINT,
            data=payload,
            headers={'Content-Type': 'text/plain'},
            timeout=5
        )

        if response.status_code == 204:
            logger.debug(f"Successfully wrote {len(metrics)} metrics to VictoriaMetrics")
        else:
            logger.warning(f"Unexpected response from VictoriaMetrics: {response.status_code}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error writing to VictoriaMetrics: {e}")


def flatten_dict(d: dict, parent_key: str = '', sep: str = '_') -> dict:
    """Flatten nested dictionary"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, (int, float)):
            items.append((new_key, v))
        elif isinstance(v, bool):
            items.append((new_key, 1 if v else 0))
    return dict(items)


def process_inference_result(data: Dict[str, Any]):
    """Convert inference result data to VictoriaMetrics metrics"""
    try:
        # Parse timestamp
        timestamp_str = data.get('timestamp')
        if timestamp_str:
            dt = date_parser.isoparse(timestamp_str)
            timestamp_ms = int(dt.timestamp() * 1000)
        else:
            timestamp_ms = int(time.time() * 1000)

        job_id = data.get('job_id', 'UNKNOWN')
        status = data.get('status', 'unknown')

        metrics = []

        # ==========================================
        # Process subsystem inference results
        # ==========================================
        # Analysis Worker sends status='success' for completed inferences
        if status == 'success':
            subsystem = data.get('subsystem', 'unknown')
            model_name = data.get('model_name', 'unknown')
            satellite_id = data.get('satellite_id', 'UNKNOWN')

            # Common labels
            labels = {
                'satellite_id': satellite_id,
                'subsystem': subsystem,
                'model_name': model_name,
                'job_id': job_id
            }

            # Anomaly metrics
            if 'anomaly_score' in data:
                metrics.append(format_prometheus_metric(
                    'inference_anomaly_score',
                    data['anomaly_score'],
                    labels,
                    timestamp_ms
                ))

            if 'is_anomaly' in data:
                metrics.append(format_prometheus_metric(
                    'inference_anomaly_detected',
                    1 if data['is_anomaly'] else 0,
                    labels,
                    timestamp_ms
                ))

            # Inference time
            if 'inference_time_ms' in data:
                metrics.append(format_prometheus_metric(
                    'inference_time_ms',
                    data['inference_time_ms'],
                    labels,
                    timestamp_ms
                ))

            # Predictions - 각 예측 스텝을 개별 타임스탬프로 저장
            predictions = data.get('predictions', [])
            window_index = data.get('window_index', 0)
            batch_id = data.get('batch_id', '')

            if predictions and isinstance(predictions, list) and len(predictions) > 0:
                import numpy as np
                pred_array = np.array(predictions)

                # 예측값 통계 (전체)
                metrics.append(format_prometheus_metric(
                    'inference_prediction_mean',
                    float(np.mean(pred_array)),
                    labels,
                    timestamp_ms
                ))

                metrics.append(format_prometheus_metric(
                    'inference_prediction_std',
                    float(np.std(pred_array)),
                    labels,
                    timestamp_ms
                ))

                metrics.append(format_prometheus_metric(
                    'inference_prediction_min',
                    float(np.min(pred_array)),
                    labels,
                    timestamp_ms
                ))

                metrics.append(format_prometheus_metric(
                    'inference_prediction_max',
                    float(np.max(pred_array)),
                    labels,
                    timestamp_ms
                ))

                # 각 예측 스텝을 개별 타임스탬프로 저장
                # window_index: 윈도우 시작 인덱스
                # predictions: [forecast_steps, features] - 10개 스텝, 각 스텝마다 여러 특징
                # 각 레코드는 30초 간격이므로, 예측 시작 시간 = 현재 시간 + (step_idx * 30초)

                subsystem = labels.get('subsystem')
                logger.info(f"Storing {len(predictions)} prediction steps for {labels.get('satellite_id')}/{subsystem}")

                for step_idx, pred_values in enumerate(predictions):
                    # 예측 대상 시간 계산: 윈도우 끝 시간 + 스텝 간격
                    pred_timestamp_ms = timestamp_ms + (step_idx * 30 * 1000)  # 30초 간격

                    if isinstance(pred_values, (list, np.ndarray)):
                        # 1. 각 특징별로 개별 메트릭 저장
                        for feature_idx, feature_value in enumerate(pred_values):
                            feature_labels = labels.copy()
                            feature_labels['forecast_step'] = str(step_idx)
                            feature_labels['feature_index'] = str(feature_idx)

                            metrics.append(format_prometheus_metric(
                                'inference_prediction_feature',
                                float(feature_value),
                                feature_labels,
                                pred_timestamp_ms
                            ))

                        # 2. 종합 예측값 (모든 특징의 평균) 저장
                        avg_value = float(np.mean(pred_values))
                        avg_labels = labels.copy()
                        avg_labels['forecast_step'] = str(step_idx)

                        metrics.append(format_prometheus_metric(
                            'inference_prediction_mean',
                            avg_value,
                            avg_labels,
                            pred_timestamp_ms
                        ))
                    else:
                        # 단일 값인 경우
                        pred_labels = labels.copy()
                        pred_labels['forecast_step'] = str(step_idx)

                        metrics.append(format_prometheus_metric(
                            'inference_prediction_mean',
                            float(pred_values),
                            pred_labels,
                            pred_timestamp_ms
                        ))

                total_metrics = len([m for m in metrics if 'inference_prediction' in m])
                logger.debug(f"Created {total_metrics} prediction metrics for {subsystem}")

            # Confidence statistics
            confidence = data.get('confidence')
            if confidence:
                if isinstance(confidence, list) and len(confidence) > 0:
                    import numpy as np
                    conf_array = np.array(confidence)
                    metrics.append(format_prometheus_metric(
                        'inference_confidence_mean',
                        float(np.mean(conf_array)),
                        labels,
                        timestamp_ms
                    ))
                elif isinstance(confidence, (int, float)):
                    metrics.append(format_prometheus_metric(
                        'inference_confidence',
                        float(confidence),
                        labels,
                        timestamp_ms
                    ))

        # ==========================================
        # Process general inference complete events
        # ==========================================
        elif event_type == 'inference_complete':
            model_name = data.get('model_name', 'unknown')

            labels = {
                'model_name': model_name,
                'job_id': job_id,
                'status': 'completed'
            }

            # Inference metrics
            metrics_data = data.get('metrics', {})
            if 'inference_time' in metrics_data:
                metrics.append(format_prometheus_metric(
                    'inference_duration_seconds',
                    metrics_data['inference_time'],
                    labels,
                    timestamp_ms
                ))

        # ==========================================
        # Process inference status events
        # ==========================================
        elif event_type in ['inference_start', 'subsystem_start']:
            status_labels = {
                'job_id': job_id,
                'status': 'started'
            }
            if 'subsystem' in data:
                status_labels['subsystem'] = data['subsystem']
            if 'model_name' in data:
                status_labels['model_name'] = data['model_name']

            metrics.append(format_prometheus_metric(
                'inference_job_status',
                1,
                status_labels,
                timestamp_ms
            ))

        elif event_type in ['inference_failed', 'subsystem_failed']:
            status_labels = {
                'job_id': job_id,
                'status': 'failed'
            }
            if 'subsystem' in data:
                status_labels['subsystem'] = data['subsystem']
            if 'model_name' in data:
                status_labels['model_name'] = data['model_name']

            metrics.append(format_prometheus_metric(
                'inference_job_status',
                0,
                status_labels,
                timestamp_ms
            ))

        # Write to VictoriaMetrics
        if metrics:
            write_to_victoria_metrics(metrics)
            logger.info(f"Processed inference result: {status}, job {job_id}: {len(metrics)} metrics")
        else:
            logger.warning(f"No metrics extracted from inference result: {status}, job {job_id}")

    except Exception as e:
        logger.error(f"Error processing inference result: {e}", exc_info=True)


def process_telemetry_data(data: Dict[str, Any]):
    """Convert comprehensive satellite telemetry data to VictoriaMetrics metrics"""
    try:
        # Extract satellite ID from top level
        satellite_id = data.get('satellite_id', 'UNKNOWN')

        # Check if data is nested under 'data' key (batch simulator format)
        if 'data' in data and isinstance(data['data'], dict):
            telemetry_data = data['data']
        else:
            telemetry_data = data

        # Parse timestamp
        timestamp_str = telemetry_data.get('timestamp')
        if timestamp_str:
            dt = date_parser.isoparse(timestamp_str)
            timestamp_ms = int(dt.timestamp() * 1000)
        else:
            timestamp_ms = int(time.time() * 1000)

        # Common labels for all metrics
        base_labels = {'satellite_id': satellite_id}

        # Build metrics list
        metrics = []

        # ==========================================
        # Process flat telemetry data (batch simulator format)
        # ==========================================

        # Extract all numeric fields directly
        for key, value in telemetry_data.items():
            if key == 'timestamp':
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                # Use the field name as metric name (already prefixed with satellite_)
                metrics.append(format_prometheus_metric(key, value, base_labels, timestamp_ms))

        # ==========================================
        # Process 6 Major Subsystems (nested format)
        # ==========================================

        # 1. Beacon & OBC
        beacon = telemetry_data.get('beacon', {})
        if beacon:
            beacon_flat = flatten_dict(beacon, 'satellite_beacon')
            for key, value in beacon_flat.items():
                if isinstance(value, (int, float)):
                    metrics.append(format_prometheus_metric(key, value, base_labels, timestamp_ms))

        obc = data.get('obc', {})
        if obc:
            obc_flat = flatten_dict(obc, 'satellite_obc')
            for key, value in obc_flat.items():
                if isinstance(value, (int, float)):
                    metrics.append(format_prometheus_metric(key, value, base_labels, timestamp_ms))

        # 2. EPS (전력 시스템) - 핵심 메트릭
        eps = data.get('eps', {})
        if eps:
            # 배터리
            if 'battery_soc_percent' in eps:
                metrics.append(format_prometheus_metric('satellite_battery_soc', eps['battery_soc_percent'], base_labels, timestamp_ms))
            if 'battery_voltage' in eps:
                metrics.append(format_prometheus_metric('satellite_battery_voltage', eps['battery_voltage'], base_labels, timestamp_ms))
            if 'battery_current' in eps:
                metrics.append(format_prometheus_metric('satellite_battery_current', eps['battery_current'], base_labels, timestamp_ms))
            if 'battery_temperature' in eps:
                metrics.append(format_prometheus_metric('satellite_battery_temp', eps['battery_temperature'], base_labels, timestamp_ms))

            # 태양 전지판
            for i in range(1, 4):
                v_key = f'solar_panel_{i}_voltage'
                c_key = f'solar_panel_{i}_current'
                if v_key in eps:
                    metrics.append(format_prometheus_metric(f'satellite_solar_panel_{i}_voltage', eps[v_key], base_labels, timestamp_ms))
                if c_key in eps:
                    metrics.append(format_prometheus_metric(f'satellite_solar_panel_{i}_current', eps[c_key], base_labels, timestamp_ms))

            # 전력 총합
            if 'total_power_consumption' in eps:
                metrics.append(format_prometheus_metric('satellite_power_consumption', eps['total_power_consumption'], base_labels, timestamp_ms))
            if 'total_power_generation' in eps:
                metrics.append(format_prometheus_metric('satellite_power_generation', eps['total_power_generation'], base_labels, timestamp_ms))

        # 3. Thermal (온도)
        thermal = data.get('thermal', {})
        if thermal:
            thermal_mapping = {
                'battery_temp': 'satellite_temp_battery',
                'obc_temp': 'satellite_temp_obc',
                'comm_temp': 'satellite_temp_comm',
                'payload_temp': 'satellite_temp_payload',
                'solar_panel_temp': 'satellite_temp_solar_panel',
                'external_temp': 'satellite_temp_external'
            }
            for key, metric_name in thermal_mapping.items():
                if key in thermal:
                    metrics.append(format_prometheus_metric(metric_name, thermal[key], base_labels, timestamp_ms))

            # 히터/쿨러 상태
            if 'heater_1_on' in thermal:
                metrics.append(format_prometheus_metric('satellite_heater_1_on', 1 if thermal['heater_1_on'] else 0, base_labels, timestamp_ms))
            if 'heater_2_on' in thermal:
                metrics.append(format_prometheus_metric('satellite_heater_2_on', 1 if thermal['heater_2_on'] else 0, base_labels, timestamp_ms))
            if 'cooler_active' in thermal:
                metrics.append(format_prometheus_metric('satellite_cooler_active', 1 if thermal['cooler_active'] else 0, base_labels, timestamp_ms))

        # 4. AOCS (자세 및 궤도)
        aocs = data.get('aocs', {})
        if aocs:
            # 자이로
            if 'gyro_x' in aocs:
                metrics.append(format_prometheus_metric('satellite_gyro_x', aocs['gyro_x'], base_labels, timestamp_ms))
            if 'gyro_y' in aocs:
                metrics.append(format_prometheus_metric('satellite_gyro_y', aocs['gyro_y'], base_labels, timestamp_ms))
            if 'gyro_z' in aocs:
                metrics.append(format_prometheus_metric('satellite_gyro_z', aocs['gyro_z'], base_labels, timestamp_ms))

            # 센서
            if 'sun_sensor_angle' in aocs:
                metrics.append(format_prometheus_metric('satellite_sun_angle', aocs['sun_sensor_angle'], base_labels, timestamp_ms))
            if 'magnetometer_x' in aocs:
                metrics.append(format_prometheus_metric('satellite_mag_x', aocs['magnetometer_x'], base_labels, timestamp_ms))
            if 'magnetometer_y' in aocs:
                metrics.append(format_prometheus_metric('satellite_mag_y', aocs['magnetometer_y'], base_labels, timestamp_ms))
            if 'magnetometer_z' in aocs:
                metrics.append(format_prometheus_metric('satellite_mag_z', aocs['magnetometer_z'], base_labels, timestamp_ms))

            # 리액션 휠
            for i in range(1, 4):
                key = f'reaction_wheel_{i}_rpm'
                if key in aocs:
                    metrics.append(format_prometheus_metric(f'satellite_wheel_{i}_rpm', aocs[key], base_labels, timestamp_ms))

            # 추진체
            if 'thruster_fuel_percent' in aocs:
                metrics.append(format_prometheus_metric('satellite_thruster_fuel', aocs['thruster_fuel_percent'], base_labels, timestamp_ms))
            if 'thruster_pressure_bar' in aocs:
                metrics.append(format_prometheus_metric('satellite_thruster_pressure', aocs['thruster_pressure_bar'], base_labels, timestamp_ms))
            if 'thruster_temperature' in aocs:
                metrics.append(format_prometheus_metric('satellite_thruster_temp', aocs['thruster_temperature'], base_labels, timestamp_ms))
            if 'thruster_active' in aocs:
                metrics.append(format_prometheus_metric('satellite_thruster_active', 1 if aocs['thruster_active'] else 0, base_labels, timestamp_ms))

            # GPS 궤도 정보 (핵심!)
            if 'gps_latitude' in aocs:
                metrics.append(format_prometheus_metric('satellite_latitude', aocs['gps_latitude'], base_labels, timestamp_ms))
            if 'gps_longitude' in aocs:
                metrics.append(format_prometheus_metric('satellite_longitude', aocs['gps_longitude'], base_labels, timestamp_ms))
            if 'gps_altitude_km' in aocs:
                metrics.append(format_prometheus_metric('satellite_altitude', aocs['gps_altitude_km'], base_labels, timestamp_ms))
            if 'gps_velocity_kmps' in aocs:
                metrics.append(format_prometheus_metric('satellite_velocity', aocs['gps_velocity_kmps'], base_labels, timestamp_ms))

        # 5. Comm (통신)
        comm = data.get('comm', {})
        if comm:
            if 'rssi_dbm' in comm:
                metrics.append(format_prometheus_metric('satellite_rssi', comm['rssi_dbm'], base_labels, timestamp_ms))
            if 'tx_active' in comm:
                metrics.append(format_prometheus_metric('satellite_tx_active', 1 if comm['tx_active'] else 0, base_labels, timestamp_ms))
            if 'rx_active' in comm:
                metrics.append(format_prometheus_metric('satellite_rx_active', 1 if comm['rx_active'] else 0, base_labels, timestamp_ms))
            if 'data_backlog_mb' in comm:
                metrics.append(format_prometheus_metric('satellite_data_backlog', comm['data_backlog_mb'], base_labels, timestamp_ms))
            if 'last_contact_seconds_ago' in comm:
                metrics.append(format_prometheus_metric('satellite_last_contact', comm['last_contact_seconds_ago'], base_labels, timestamp_ms))

        # 6. Payload (탑재체)
        payload = data.get('payload', {})
        if payload:
            if 'camera_on' in payload:
                metrics.append(format_prometheus_metric('satellite_camera_on', 1 if payload['camera_on'] else 0, base_labels, timestamp_ms))
            if 'sensor_on' in payload:
                metrics.append(format_prometheus_metric('satellite_sensor_on', 1 if payload['sensor_on'] else 0, base_labels, timestamp_ms))
            if 'payload_temp' in payload:
                metrics.append(format_prometheus_metric('satellite_payload_temp', payload['payload_temp'], base_labels, timestamp_ms))
            if 'payload_power_watts' in payload:
                metrics.append(format_prometheus_metric('satellite_payload_power', payload['payload_power_watts'], base_labels, timestamp_ms))
            if 'images_captured_count' in payload:
                metrics.append(format_prometheus_metric('satellite_images_captured', payload['images_captured_count'], base_labels, timestamp_ms))

        # Write to VictoriaMetrics
        if metrics:
            write_to_victoria_metrics(metrics)
            logger.info(f"Processed telemetry from {satellite_id}: {len(metrics)} metrics")
        else:
            logger.warning(f"No metrics extracted from {satellite_id}")

    except Exception as e:
        logger.error(f"Error processing telemetry data: {e}", exc_info=True)


def consume_messages():
    """Main consumer loop"""
    consumer = None

    try:
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Create consumer
        consumer = create_kafka_consumer()
        logger.info("Starting message consumption...")

        while running:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.debug(f"Reached end of partition {msg.partition()}")
                elif msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    raise KafkaException(msg.error())
                continue

            # Process message based on topic
            try:
                data = parse_telemetry_message(msg.value())

                # Determine message type based on topic
                topic = msg.topic()
                logger.debug(f"Received message from topic: {topic}")

                if topic == KAFKA_TOPIC_TELEMETRY:
                    process_telemetry_data(data)
                elif topic == KAFKA_TOPIC_INFERENCE:
                    logger.info(f"Processing inference result from topic: {topic}")
                    process_inference_result(data)
                else:
                    logger.warning(f"Unknown topic: {topic}")

            except Exception as e:
                logger.error(f"Failed to process message: {e}", exc_info=True)

    except KeyboardInterrupt:
        logger.info("Consumer interrupted by user")
    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)
    finally:
        if consumer:
            logger.info("Closing consumer...")
            consumer.close()
            logger.info("Consumer closed")


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("VictoriaMetrics Kafka Consumer Starting...")
    logger.info("=" * 60)
    consume_messages()
    logger.info("Consumer shutdown complete")
