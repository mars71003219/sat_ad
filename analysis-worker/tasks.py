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

from celery import Celery
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
        # Triton 클라이언트 생성
        triton_client = httpclient.InferenceServerClient(url=TRITON_URL)

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

        # Triton 서버로 추론 요청
        logger.info(f"Calling Triton server: {TRITON_URL}/{model_name}")
        response = triton_client.infer(
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
    """Kafka로 추론 결과 발행"""
    producer = None
    try:
        topic = 'inference-results'
        job_id = result.get('job_id', 'unknown')
        logger.info(f"Publishing result to Kafka topic '{topic}': {job_id}")

        # 각 작업마다 새로운 Producer 생성 (Celery fork 문제 회피)
        kafka_conf = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'client.id': job_id
        }
        producer = Producer(kafka_conf)

        message = json.dumps(result)

        def delivery_report(err, msg):
            if err is not None:
                logger.error(f"Kafka delivery failed for {job_id}: {err}")
            else:
                logger.info(f"Successfully published result to Kafka: {job_id} (partition {msg.partition()}, offset {msg.offset()})")

        producer.produce(
            topic,
            key=job_id.encode('utf-8'),
            value=message.encode('utf-8'),
            callback=delivery_report
        )
        producer.flush(timeout=10)  # 최대 10초 대기
        logger.info(f"Flush completed for {job_id}")

    except Exception as e:
        logger.error(f"Failed to publish result: {e}", exc_info=True)
    finally:
        if producer:
            try:
                producer.flush()
            except:
                pass


if __name__ == '__main__':
    # Celery worker 실행
    celery_app.worker_main([
        'worker',
        '--loglevel=info',
        '--concurrency=2',
        '--queues=inference'
    ])
