#!/bin/bash

# Kafka 클러스터 ID 생성 스크립트

ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
    echo ".env 파일이 이미 존재합니다."
    echo "기존 설정을 사용합니다:"
    cat $ENV_FILE
else
    echo "Kafka 클러스터 ID 생성 중..."
    CLUSTER_ID=$(docker run --rm confluentinc/cp-kafka:latest kafka-storage random-uuid)
    echo "KAFKA_CLUSTER_ID=$CLUSTER_ID" > $ENV_FILE
    echo ".env 파일 생성 완료:"
    cat $ENV_FILE
fi
