#!/usr/bin/env python3
"""
Analysis Worker - Celery Tasks

실제 Triton Inference Server를 호출하는 워커
"""
import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, List

import numpy as np
import tritonclient.http as httpclient
from tritonclient.utils import InferenceServerException

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from celery import Celery, signals
from confluent_kafka import Producer

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Celery App
celery_app = Celery(
    'analysis_server',
    broker=os.getenv('CELERY_BROKER_URL', 'amqp://guest:guest@rabbitmq:5672//'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'rpc://')
)

# Kafka Producer 설정
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')

# Triton 클라이언트 설정
TRITON_URL = os.getenv('TRITON_SERVER_URL', 'triton-server:8000')

# 전역 클라이언트 (워커 프로세스당 1개)
_triton_client = None
_kafka_producer = None


@signals.worker_process_init.connect
def init_worker_process(**kwargs):
    """워커 프로세스 초기화 시 클라이언트 생성 (재사용)"""
    global _triton_client, _kafka_producer

    logger.info("Initializing worker process clients...")

    # Triton 클라이언트 초기화
    try:
        _triton_client = httpclient.InferenceServerClient(url=TRITON_URL)
        logger.info(f"Triton client initialized: {TRITON_URL}")
    except Exception as e:
        logger.error(f"Failed to initialize Triton client: {e}")
        _triton_client = None

    # Kafka Producer 초기화
    try:
        producer_config = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'linger.ms': 10,
            'batch.size': 16384
        }
        _kafka_producer = Producer(producer_config)
        logger.info(f"Kafka producer initialized: {KAFKA_BOOTSTRAP_SERVERS}")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        _kafka_producer = None


@signals.worker_process_shutdown.connect
def shutdown_worker_process(**kwargs):
    """워커 프로세스 종료 시 클라이언트 정리"""
    global _kafka_producer

    logger.info("Shutting down worker process clients...")

    if _kafka_producer:
        _kafka_producer.flush(timeout=5)
        logger.info("Kafka producer flushed")


@celery_app.task(name='analysis_server.tasks.run_subsystem_inference')
def run_subsystem_inference(
    job_id: str,
    subsystem: str,
    model_name: str,
    input_data: List[List[float]],
    input_features: List[str],
    config: Dict[str, Any],
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    서브시스템 추론 실행 - Triton Inference Server 호출

    Args:
        job_id: 작업 ID
        subsystem: 서브시스템 이름 (eps, thermal, aocs, comm)
        model_name: 모델 이름 (transformer_*)
        input_data: 입력 데이터 [sequence_length, features]
        input_features: 입력 특징 이름들
        config: 추론 설정
        metadata: 메타데이터

    Returns:
        추론 결과
    """
    logger.info(f"Starting inference: {job_id}")
    logger.info(f"  Subsystem: {subsystem}")
    logger.info(f"  Model: {model_name}")
    logger.info(f"  Input features: {len(input_features)}")
    logger.info(f"  Input shape: {np.array(input_data).shape}")

    start_time = time.time()

    try:
        # 전역 Triton 클라이언트 사용 (재사용)
        global _triton_client

        if _triton_client is None:
            # 클라이언트가 없으면 생성 (fallback)
            _triton_client = httpclient.InferenceServerClient(url=TRITON_URL)
            logger.warning("Triton client not initialized, creating new one")

        # 입력 데이터를 NumPy 배열로 변환
        input_array = np.array(input_data, dtype=np.float32)  # [sequence_length, features]

        # Triton 입력 텐서 생성
        inputs = [
            httpclient.InferInput("input_data", input_array.shape, "FP32")
        ]
        inputs[0].set_data_from_numpy(input_array)

        # Triton 출력 텐서 정의
        outputs = [
            httpclient.InferRequestedOutput("predictions"),
            httpclient.InferRequestedOutput("anomaly_score")
        ]

        # Triton 서버로 추론 요청 (재사용된 클라이언트 사용)
        logger.debug(f"Calling Triton server: {TRITON_URL}/{model_name}")
        response = _triton_client.infer(
            model_name=model_name,
            inputs=inputs,
            outputs=outputs
        )

        # 결과 추출
        predictions = response.as_numpy("predictions")  # [forecast_steps, features]
        anomaly_score_array = response.as_numpy("anomaly_score")

        # NumPy 배열을 Python 스칼라로 변환
        if anomaly_score_array.ndim > 0:
            anomaly_score = float(anomaly_score_array.flatten()[0])
        else:
            anomaly_score = float(anomaly_score_array)

        inference_time_ms = (time.time() - start_time) * 1000

        # 이상 여부 판단 (threshold: 0.5)
        is_anomaly = anomaly_score > 0.5

        # 결과 구성
        result = {
            'job_id': job_id,
            'subsystem': subsystem,
            'satellite_id': metadata.get('satellite_id'),
            'batch_id': metadata.get('batch_id'),
            'window_index': metadata.get('window_index'),
            'model_name': model_name,
            'predictions': predictions.tolist(),  # [forecast_steps, features]
            'anomaly_score': anomaly_score,
            'is_anomaly': is_anomaly,
            'inference_time_ms': inference_time_ms,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'success'
        }

        logger.info(f"Inference complete: {job_id}")
        logger.info(f"  Anomaly: {is_anomaly}, Score: {anomaly_score:.3f}")
        logger.info(f"  Inference time: {inference_time_ms:.1f}ms")

        # Kafka로 결과 발행
        publish_inference_result(result)

        return result

    except InferenceServerException as e:
        logger.error(f"Triton inference failed: {job_id} - {e}", exc_info=True)

        error_result = {
            'job_id': job_id,
            'subsystem': subsystem,
            'satellite_id': metadata.get('satellite_id'),
            'batch_id': metadata.get('batch_id'),
            'status': 'failed',
            'error': f"Triton error: {str(e)}",
            'timestamp': datetime.utcnow().isoformat()
        }

        publish_inference_result(error_result)
        return error_result

    except Exception as e:
        logger.error(f"Inference failed: {job_id} - {e}", exc_info=True)

        error_result = {
            'job_id': job_id,
            'subsystem': subsystem,
            'satellite_id': metadata.get('satellite_id'),
            'batch_id': metadata.get('batch_id'),
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }

        publish_inference_result(error_result)
        return error_result


def publish_inference_result(result: Dict[str, Any]):
    """Kafka로 추론 결과 발행 (전역 Producer 재사용)"""
    global _kafka_producer

    try:
        topic = 'inference-results'
        job_id = result.get('job_id', 'unknown')
        logger.debug(f"Publishing result to Kafka topic '{topic}': {job_id}")

        # 전역 Producer 사용 (재사용)
        if _kafka_producer is None:
            # Fallback: Producer가 없으면 생성
            kafka_conf = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'linger.ms': 10,
                'batch.size': 16384
            }
            _kafka_producer = Producer(kafka_conf)
            logger.warning("Kafka producer not initialized, creating new one")

        message = json.dumps(result)

        def delivery_report(err, msg):
            if err is not None:
                logger.error(f"Kafka delivery failed for {job_id}: {err}")
            else:
                logger.debug(f"Successfully published result to Kafka: {job_id}")

        _kafka_producer.produce(
            topic,
            key=job_id.encode('utf-8'),
            value=message.encode('utf-8'),
            callback=delivery_report
        )
        # Poll을 호출하여 delivery callback 실행
        _kafka_producer.poll(0)

    except Exception as e:
        logger.error(f"Failed to publish result: {e}", exc_info=True)


if __name__ == '__main__':
    # Celery worker 실행
    celery_app.worker_main([
        'worker',
        '--loglevel=info',
        '--concurrency=2',
        '--queues=inference'
    ])
