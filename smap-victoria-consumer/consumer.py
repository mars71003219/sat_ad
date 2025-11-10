#!/usr/bin/env python3
"""
SMAP Victoria Consumer

Consumes SMAP inference results from Kafka and writes to VictoriaMetrics
"""

import asyncio
import json
import logging
import os
import signal
from typing import Dict, List, Any
from datetime import datetime
from aiokafka import AIOKafkaConsumer
import aiohttp

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
KAFKA_TOPIC_RESULTS = os.getenv('KAFKA_TOPIC_RESULTS', 'smap-inference-results')
KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'smap-victoria-consumer')
VICTORIA_METRICS_URL = os.getenv('VICTORIA_METRICS_URL', 'http://victoria-metrics:8428')
VICTORIA_WRITE_ENDPOINT = f"{VICTORIA_METRICS_URL}/api/v1/import/prometheus"

# Global state
running = True


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    logger.info(f"Received signal {signum}, shutting down...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def create_victoria_metrics(result: Dict[str, Any]) -> List[str]:
    """
    Convert SMAP inference result to VictoriaMetrics Prometheus format

    Args:
        result: Inference result dictionary

    Returns:
        List of metric strings in Prometheus format
    """
    metrics = []

    satellite_id = result.get('satellite_id', 'unknown')
    entity = result.get('entity', 'unknown')
    timestamp = result.get('timestamp')

    # Parse timestamp to milliseconds
    try:
        ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        ts_ms = int(ts.timestamp() * 1000)
    except:
        ts_ms = int(datetime.now().timestamp() * 1000)

    # Common labels
    labels = f'satellite_id="{satellite_id}",entity="{entity}"'

    # Skip error results
    if 'error' in result:
        metrics.append(
            f'smap_inference_error{{{{satellite_id="{satellite_id}",entity="{entity}"}}}} 1 {ts_ms}'
        )
        return metrics

    # Overall anomaly score
    anomaly_score = result.get('anomaly_score', 0.0)
    metrics.append(
        f'smap_anomaly_score{{{labels}}} {anomaly_score} {ts_ms}'
    )

    # Anomaly detected flag
    anomaly_detected = 1 if result.get('anomaly_detected', False) else 0
    metrics.append(
        f'smap_anomaly_detected{{{labels}}} {anomaly_detected} {ts_ms}'
    )

    # Inference time
    inference_time = result.get('inference_time_ms', 0)
    metrics.append(
        f'smap_inference_time_ms{{{labels}}} {inference_time} {ts_ms}'
    )

    # Per-sensor metrics
    sensor_values = result.get('sensor_values', [])
    reconstruction = result.get('reconstruction', [])

    for i in range(min(len(sensor_values), 25)):
        sensor_label = f'{labels},sensor="sensor_{i}"'

        # Actual sensor value
        metrics.append(
            f'smap_sensor_value{{{sensor_label}}} {sensor_values[i]} {ts_ms}'
        )

        # Reconstructed value
        if i < len(reconstruction):
            metrics.append(
                f'smap_sensor_reconstruction{{{sensor_label}}} {reconstruction[i]} {ts_ms}'
            )

            # Per-sensor error
            error = abs(sensor_values[i] - reconstruction[i])
            metrics.append(
                f'smap_sensor_error{{{sensor_label}}} {error} {ts_ms}'
            )

    return metrics


async def write_to_victoria_metrics(
    session: aiohttp.ClientSession,
    metrics: List[str]
) -> None:
    """
    Write metrics to VictoriaMetrics

    Args:
        session: aiohttp session
        metrics: List of metric strings
    """
    if not metrics:
        return

    payload = '\n'.join(metrics)

    try:
        async with session.post(
            VICTORIA_WRITE_ENDPOINT,
            data=payload,
            headers={'Content-Type': 'text/plain'},
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            if response.status == 204:
                logger.debug(f"Wrote {len(metrics)} metrics to VictoriaMetrics")
            else:
                text = await response.text()
                logger.error(f"Victoria write error [{response.status}]: {text}")

    except Exception as e:
        logger.error(f"Failed to write to VictoriaMetrics: {e}")


async def consume_inference_results():
    """Main consumer loop"""
    consumer = None
    session = None

    try:
        # Create aiohttp session
        session = aiohttp.ClientSession()

        # Create Kafka consumer
        consumer = AIOKafkaConsumer(
            KAFKA_TOPIC_RESULTS,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=KAFKA_GROUP_ID,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )

        await consumer.start()
        logger.info(f"Started consuming from topic: {KAFKA_TOPIC_RESULTS}")

        # Consume messages
        async for message in consumer:
            if not running:
                break

            result = message.value

            # Convert to VictoriaMetrics format
            metrics = create_victoria_metrics(result)

            # Write to VictoriaMetrics
            await write_to_victoria_metrics(session, metrics)

            logger.info(
                f"Processed inference result: "
                f"{result.get('satellite_id')}/{result.get('entity')} "
                f"score={result.get('anomaly_score', 0):.4f}"
            )

    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)

    finally:
        if consumer:
            await consumer.stop()
            logger.info("Consumer stopped")

        if session:
            await session.close()
            logger.info("HTTP session closed")


async def main():
    """Main entry point"""
    logger.info("SMAP Victoria Consumer starting...")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"  Topic: {KAFKA_TOPIC_RESULTS}")
    logger.info(f"  VictoriaMetrics: {VICTORIA_METRICS_URL}")

    await consume_inference_results()

    logger.info("SMAP Victoria Consumer stopped")


if __name__ == '__main__':
    asyncio.run(main())
