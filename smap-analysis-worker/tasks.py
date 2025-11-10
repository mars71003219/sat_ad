#!/usr/bin/env python3
"""
SMAP Analysis Worker

Celery worker for OmniAnomaly inference via Triton Server
"""

import os
import json
import logging
import numpy as np
from typing import Dict, List, Any
from datetime import datetime
from celery import Celery, signals
from confluent_kafka import Producer
import tritonclient.http as httpclient

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Celery configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'amqp://guest:guest@rabbitmq:5672//')
CELERY_BACKEND_URL = os.getenv('CELERY_BACKEND_URL', 'rpc://')

celery_app = Celery('smap_analysis', broker=CELERY_BROKER_URL, backend=CELERY_BACKEND_URL)

# Triton Server configuration
TRITON_URL = os.getenv('TRITON_OMNIANOMALY_URL', 'triton-omnianomaly:8000')

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
KAFKA_TOPIC_RESULTS = os.getenv('KAFKA_TOPIC_RESULTS', 'smap-inference-results')

# Global clients (initialized per worker process)
_triton_client = None
_kafka_producer = None


@signals.worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize Triton and Kafka clients when worker process starts"""
    global _triton_client, _kafka_producer

    logger.info("Initializing SMAP worker process clients...")

    # Triton client
    try:
        _triton_client = httpclient.InferenceServerClient(url=TRITON_URL, verbose=False)
        if _triton_client.is_server_ready():
            logger.info(f"✓ Triton client connected: {TRITON_URL}")
        else:
            logger.warning(f"Triton server not ready: {TRITON_URL}")
    except Exception as e:
        logger.error(f"Failed to initialize Triton client: {e}")
        _triton_client = None

    # Kafka producer
    try:
        kafka_conf = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'linger.ms': 10,
            'batch.size': 16384
        }
        _kafka_producer = Producer(kafka_conf)
        logger.info(f"✓ Kafka producer initialized: {KAFKA_BOOTSTRAP_SERVERS}")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        _kafka_producer = None


@signals.worker_process_shutdown.connect
def shutdown_worker_process(**kwargs):
    """Cleanup when worker process shuts down"""
    global _kafka_producer

    logger.info("Shutting down SMAP worker process clients...")

    if _kafka_producer:
        _kafka_producer.flush(timeout=5)
        logger.info("✓ Kafka producer flushed")


@celery_app.task(name='smap_analysis.tasks.run_omnianomaly_inference')
def run_omnianomaly_inference(
    satellite_id: str,
    entity: str,
    timestamp: str,
    sensor_values: List[float],
    index: int = 0
) -> Dict[str, Any]:
    """
    Run OmniAnomaly inference for a single SMAP entity timestep

    Args:
        satellite_id: Satellite identifier (e.g., SAT-001)
        entity: SMAP entity (e.g., A-1)
        timestamp: ISO timestamp
        sensor_values: List of 25 sensor readings
        index: Data index (for debugging)

    Returns:
        Inference result dictionary
    """
    global _triton_client

    start_time = datetime.now()

    try:
        # Validate Triton client
        if _triton_client is None:
            _triton_client = httpclient.InferenceServerClient(url=TRITON_URL, verbose=False)
            logger.warning("Triton client not initialized, creating new one")

        # Model name
        model_name = f"smap_{entity}"

        # Prepare input tensor
        input_data = np.array(sensor_values, dtype=np.float64)  # shape: (25,)

        inputs = [
            httpclient.InferInput("input_data", input_data.shape, "FP64")
        ]
        inputs[0].set_data_from_numpy(input_data)

        # Prepare output
        outputs = [
            httpclient.InferRequestedOutput("reconstruction"),
            httpclient.InferRequestedOutput("anomaly_score"),
            httpclient.InferRequestedOutput("anomaly_detected")
        ]

        # Execute inference
        response = _triton_client.infer(
            model_name=model_name,
            inputs=inputs,
            outputs=outputs
        )

        # Parse results
        reconstruction = response.as_numpy("reconstruction")  # (25,)
        anomaly_score = float(response.as_numpy("anomaly_score")[0])
        anomaly_detected = bool(response.as_numpy("anomaly_detected")[0])

        inference_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Build result
        result = {
            'satellite_id': satellite_id,
            'entity': entity,
            'timestamp': timestamp,
            'index': index,
            'sensor_values': sensor_values,
            'reconstruction': reconstruction.tolist(),
            'anomaly_score': anomaly_score,
            'anomaly_detected': anomaly_detected,
            'inference_time_ms': inference_time_ms,
            'model': 'OmniAnomaly',
            'triton_model': model_name
        }

        # Publish to Kafka
        publish_inference_result(result)

        logger.info(f"Inference complete: {satellite_id}/{entity} "
                   f"score={anomaly_score:.4f} detected={anomaly_detected} "
                   f"time={inference_time_ms:.1f}ms")

        return result

    except Exception as e:
        logger.error(f"Inference failed for {satellite_id}/{entity}: {e}", exc_info=True)

        # Publish error result
        error_result = {
            'satellite_id': satellite_id,
            'entity': entity,
            'timestamp': timestamp,
            'index': index,
            'error': str(e),
            'status': 'failed'
        }
        publish_inference_result(error_result)

        raise


def publish_inference_result(result: Dict[str, Any]) -> None:
    """
    Publish inference result to Kafka

    Args:
        result: Inference result dictionary
    """
    global _kafka_producer

    try:
        if _kafka_producer is None:
            kafka_conf = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'linger.ms': 10,
                'batch.size': 16384
            }
            _kafka_producer = Producer(kafka_conf)
            logger.warning("Kafka producer not initialized, creating new one")

        # Message key: satellite_id:entity
        key = f"{result['satellite_id']}:{result['entity']}"

        # Serialize result
        message = json.dumps(result)

        # Produce to Kafka
        _kafka_producer.produce(
            KAFKA_TOPIC_RESULTS,
            key=key.encode('utf-8'),
            value=message.encode('utf-8')
        )
        _kafka_producer.poll(0)

    except Exception as e:
        logger.error(f"Failed to publish result to Kafka: {e}")
