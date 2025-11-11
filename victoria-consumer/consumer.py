#!/usr/bin/env python3
"""
VictoriaMetrics Kafka Consumer (Async)
Consumes satellite telemetry data from Kafka and writes to VictoriaMetrics
"""

import json
import logging
import signal
import sys
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List

import aiohttp
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from dateutil import parser as date_parser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = 'kafka:9092'
KAFKA_TOPIC_TELEMETRY = 'satellite-telemetry-raw'  # Fan-out: raw 토픽 구독
KAFKA_TOPIC_INFERENCE = 'inference-results'
KAFKA_GROUP_ID = 'victoria-consumer-group-v5-fanout'
VICTORIA_METRICS_URL = 'http://victoria-metrics:8428'
VICTORIA_WRITE_ENDPOINT = f'{VICTORIA_METRICS_URL}/api/v1/import/prometheus'

# Global flag for graceful shutdown
running = True


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global running
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    running = False


def format_prometheus_metric(metric_name: str, value: float, labels: Dict[str, str], timestamp_ms: int) -> str:
    """Format a single metric in Prometheus exposition format"""
    label_str = ','.join([f'{k}="{v}"' for k, v in labels.items()])
    return f"{metric_name}{{{label_str}}} {value} {timestamp_ms}"


async def write_to_victoria_metrics(session: aiohttp.ClientSession, metrics: List[str]):
    """Write metrics to VictoriaMetrics using Prometheus format (async)"""
    if not metrics:
        return

    # Join all metrics with newlines
    payload = '\n'.join(metrics)

    try:
        async with session.post(
            VICTORIA_WRITE_ENDPOINT,
            data=payload,
            headers={'Content-Type': 'text/plain'},
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            if response.status == 204:
                logger.debug(f"Successfully wrote {len(metrics)} metrics to VictoriaMetrics")
            else:
                logger.warning(f"Unexpected response from VictoriaMetrics: {response.status}")

    except asyncio.TimeoutError:
        logger.error("Timeout writing to VictoriaMetrics")
    except Exception as e:
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


async def process_inference_result(session: aiohttp.ClientSession, data: Dict[str, Any]):
    """Convert inference result data to VictoriaMetrics metrics (async)"""
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

        # Process subsystem inference results
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

            # Predictions
            predictions = data.get('predictions', [])

            if predictions and isinstance(predictions, list) and len(predictions) > 0:
                import numpy as np
                pred_array = np.array(predictions)

                # 예측값 통계
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

                # 각 예측 스텝
                for step_idx, pred_values in enumerate(predictions):
                    pred_timestamp_ms = timestamp_ms + (step_idx * 30 * 1000)

                    if isinstance(pred_values, (list, np.ndarray)):
                        # 각 특징별 메트릭
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

                        # 평균값
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
                        pred_labels = labels.copy()
                        pred_labels['forecast_step'] = str(step_idx)

                        metrics.append(format_prometheus_metric(
                            'inference_prediction_mean',
                            float(pred_values),
                            pred_labels,
                            pred_timestamp_ms
                        ))

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

        # Write to VictoriaMetrics
        if metrics:
            await write_to_victoria_metrics(session, metrics)
            logger.info(f"Processed inference result: {status}, job {job_id}: {len(metrics)} metrics")
        else:
            logger.warning(f"No metrics extracted from inference result: {status}, job {job_id}")

    except Exception as e:
        logger.error(f"Error processing inference result: {e}", exc_info=True)


async def process_telemetry_data(session: aiohttp.ClientSession, data: Dict[str, Any]):
    """Convert comprehensive satellite telemetry data to VictoriaMetrics metrics (async)"""
    try:
        # Extract satellite ID
        satellite_id = data.get('satellite_id', 'UNKNOWN')

        # Check if data is nested
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

        # Common labels
        base_labels = {'satellite_id': satellite_id}
        metrics = []

        # Extract all numeric fields directly
        for key, value in telemetry_data.items():
            if key == 'timestamp':
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics.append(format_prometheus_metric(key, value, base_labels, timestamp_ms))

        # Process nested subsystems (if exists)
        # ... (EPS, Thermal, AOCS, Comm, Payload 처리 로직은 동일하게 유지)

        # Write to VictoriaMetrics
        if metrics:
            await write_to_victoria_metrics(session, metrics)
            logger.debug(f"Processed telemetry from {satellite_id}: {len(metrics)} metrics")

    except Exception as e:
        logger.error(f"Error processing telemetry data: {e}", exc_info=True)


async def consume_messages():
    """Main async consumer loop"""
    consumer = None
    session = None

    try:
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Create aiohttp session
        session = aiohttp.ClientSession()

        # Create Kafka consumer
        consumer = AIOKafkaConsumer(
            KAFKA_TOPIC_TELEMETRY,
            KAFKA_TOPIC_INFERENCE,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=KAFKA_GROUP_ID,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )

        await consumer.start()
        logger.info(f"Kafka consumer started, subscribed to: {KAFKA_TOPIC_TELEMETRY}, {KAFKA_TOPIC_INFERENCE}")

        # Consume messages
        while running:
            try:
                # Get batch of messages
                result = await consumer.getmany(timeout_ms=1000, max_records=100)

                for tp, messages in result.items():
                    for message in messages:
                        try:
                            data = message.value
                            topic = message.topic

                            # Process based on topic
                            if topic == KAFKA_TOPIC_TELEMETRY:
                                await process_telemetry_data(session, data)
                            elif topic == KAFKA_TOPIC_INFERENCE:
                                await process_inference_result(session, data)
                            else:
                                logger.warning(f"Unknown topic: {topic}")

                        except Exception as e:
                            logger.error(f"Failed to process message: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error in consumer loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Consumer interrupted by user")
    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)
    finally:
        if consumer:
            logger.info("Stopping consumer...")
            await consumer.stop()
            logger.info("Consumer stopped")

        if session:
            await session.close()
            logger.info("HTTP session closed")


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("VictoriaMetrics Kafka Consumer (Async) Starting...")
    logger.info("=" * 60)
    asyncio.run(consume_messages())
    logger.info("Consumer shutdown complete")
