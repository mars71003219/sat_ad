#!/bin/bash
# 토픽 중심 아키텍처 시작 스크립트

set -e

echo "=========================================="
echo "Starting Topic-Centric Architecture"
echo "=========================================="

# Step 1: 공용 토픽 생성
echo ""
echo "Step 1: Creating public topics..."
bash scripts/create_public_topics.sh

# Step 2: 서비스 시작
echo ""
echo "Step 2: Starting services..."
echo ""

# 기본 인프라
echo "Starting infrastructure..."
docker-compose -f docker-compose.topic-centric.yml up -d \
  kafka rabbitmq victoria-metrics

# Kafka 준비 대기
echo "Waiting for Kafka..."
sleep 10

# Demux (범용, 서비스 무관)
echo "Starting Stream Demux (서비스 무관, 범용)..."
docker-compose -f docker-compose.topic-centric.yml up -d stream-demux

# 서비스 1: 이상탐지
echo "Starting Anomaly Detection Service..."
docker-compose -f docker-compose.topic-centric.yml up -d \
  anomaly-detection analysis-worker

# VictoriaMetrics Consumer
echo "Starting VictoriaMetrics Consumer..."
docker-compose -f docker-compose.topic-centric.yml up -d victoria-consumer

# 모니터링
echo "Starting monitoring..."
docker-compose -f docker-compose.topic-centric.yml up -d kafka-ui flower

# 서비스 2: 스케줄링 (옵션)
read -p "Start Scheduling service? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Starting Scheduling Service..."
    docker-compose -f docker-compose.topic-centric.yml --profile scheduling up -d scheduling
fi

# SMAP 시뮬레이터 (옵션)
read -p "Start SMAP simulator? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Starting SMAP Simulator..."
    docker-compose -f docker-compose.topic-centric.yml --profile smap up -d smap-simulator
fi

echo ""
echo "=========================================="
echo "Topic-Centric Architecture Started!"
echo "=========================================="
echo ""
echo "Architecture:"
echo "  Simulator → raw topic → Demux (범용)"
echo "                       ↓"
echo "              public topics (공용)"
echo "                       ↓"
echo "            [Anomaly, Scheduling, ...] (독립 Consumer)"
echo ""
echo "Services:"
echo "  - Stream Demux: 범용 (서비스 모름)"
echo "  - Anomaly Detection: group=anomaly-detection-group"
echo "  - Scheduling: group=scheduling-group (옵션)"
echo ""
echo "Monitoring:"
echo "  - Kafka UI: http://localhost:8080"
echo "  - Flower: http://localhost:5555"
echo ""
echo "Logs:"
echo "  docker-compose -f docker-compose.topic-centric.yml logs -f stream-demux"
echo "  docker-compose -f docker-compose.topic-centric.yml logs -f anomaly-detection"
echo "  docker-compose -f docker-compose.topic-centric.yml logs -f scheduling"
echo ""
echo "=========================================="
echo "확장성 테스트:"
echo "  새 서비스 추가 → Demux 수정 불필요!"
echo "  같은 토픽을 여러 서비스가 구독 가능!"
echo "=========================================="
