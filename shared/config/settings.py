"""
공유 설정 모듈
"""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    """시스템 설정"""

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
    KAFKA_TOPIC_TELEMETRY: str = os.getenv('KAFKA_TOPIC_TELEMETRY', 'satellite-telemetry')
    KAFKA_TOPIC_INFERENCE: str = os.getenv('KAFKA_TOPIC_INFERENCE', 'inference-results')

    # Celery
    CELERY_BROKER_URL: str = os.getenv('CELERY_BROKER_URL', 'amqp://guest:guest@rabbitmq:5672//')
    CELERY_RESULT_BACKEND: str = os.getenv('CELERY_RESULT_BACKEND', 'rpc://')

    # VictoriaMetrics
    VICTORIA_METRICS_URL: str = os.getenv('VICTORIA_METRICS_URL', 'http://victoria-metrics:8428')

    # Inference
    WINDOW_SIZE: int = int(os.getenv('WINDOW_SIZE', '30'))
    STRIDE: int = int(os.getenv('STRIDE', '10'))
    FORECAST_HORIZON: int = int(os.getenv('FORECAST_HORIZON', '10'))

    # Triton
    TRITON_SERVER_URL: str = os.getenv('TRITON_SERVER_URL', 'triton-server:8001')


settings = Settings()
