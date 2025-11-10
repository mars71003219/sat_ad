#!/usr/bin/env python3
"""
SMAP Inference Trigger

Consumes SMAP telemetry data from Kafka and triggers inference tasks for each entity.
No windowing required - OmniAnomaly uses stateful LSTM hidden states.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any
from aiokafka import AIOKafkaConsumer
from celery import Celery

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Celery configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'amqp://guest:guest@rabbitmq:5672//')
CELERY_BACKEND_URL = os.getenv('CELERY_BACKEND_URL', 'rpc://')

celery_app = Celery('smap_inference', broker=CELERY_BROKER_URL, backend=CELERY_BACKEND_URL)

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
KAFKA_TOPIC_SMAP = os.getenv('KAFKA_TOPIC_SMAP', 'smap-telemetry')
KAFKA_GROUP_ID = os.getenv('KAFKA_GROUP_ID', 'smap-inference-trigger')


async def consume_smap_telemetry():
    """
    Consume SMAP telemetry and trigger inference for each record

    OmniAnomaly uses stateful LSTM, so no windowing needed - just send each timestep
    """
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC_SMAP,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_GROUP_ID,
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )

    await consumer.start()
    logger.info(f"Started consuming from topic: {KAFKA_TOPIC_SMAP}")

    try:
        async for message in consumer:
            data = message.value

            # Extract fields
            satellite_id = data['satellite_id']
            entity = data['entity']
            timestamp = data['timestamp']
            sensors = data['sensors']

            # Convert sensors dict to numpy-compatible list
            sensor_values = [sensors[f'sensor_{i}'] for i in range(25)]

            # Trigger Celery inference task
            celery_app.send_task(
                'smap_analysis.tasks.run_omnianomaly_inference',
                kwargs={
                    'satellite_id': satellite_id,
                    'entity': entity,
                    'timestamp': timestamp,
                    'sensor_values': sensor_values,
                    'index': data.get('index', 0)
                }
            )

            logger.debug(f"Triggered inference for {satellite_id}/{entity} at {timestamp}")

    except Exception as e:
        logger.error(f"Error in consumer: {e}", exc_info=True)
    finally:
        await consumer.stop()
        logger.info("Consumer stopped")


async def main():
    """Main entry point"""
    logger.info("SMAP Inference Trigger starting...")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"  Topic: {KAFKA_TOPIC_SMAP}")
    logger.info(f"  Celery Broker: {CELERY_BROKER_URL}")

    await consume_smap_telemetry()


if __name__ == '__main__':
    asyncio.run(main())
