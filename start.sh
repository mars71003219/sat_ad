#!/bin/bash

# 위성 텔레메트리 이상 감지 시스템 시작 스크립트

set -e

echo "=========================================="
echo "위성 텔레메트리 이상 감지 시스템 시작"
echo "=========================================="

# Kafka 클러스터 ID 확인
if [ ! -f .env ]; then
    echo "️  Kafka 클러스터 ID가 없습니다. 초기화를 실행합니다..."
    bash init-kafka.sh
fi

# Docker Compose 실행
echo ""
echo " Docker 컨테이너 시작 중..."
docker-compose up -d

echo ""
echo " 서비스 초기화 대기 중..."
sleep 10

# 서비스 상태 확인
echo ""
echo " 서비스 상태 확인..."
docker-compose ps

echo ""
echo "=========================================="
echo " 시스템이 성공적으로 시작되었습니다!"
echo "=========================================="
echo ""
echo " 서비스 접속 정보:"
echo "  - Dashboard:           http://localhost"
echo "  - API Server:          http://localhost/api"
echo "  - Kafka UI:            http://localhost:8080"
echo "  - RabbitMQ Management: http://localhost:15672 (guest/guest)"
echo "  - Flower (Celery):     http://localhost:5555"
echo "  - VictoriaMetrics:     http://localhost:8428"
echo ""
echo " 로그 확인:"
echo "  docker-compose logs -f [service_name]"
echo ""
echo " 시스템 종료:"
echo "  docker-compose down"
echo ""
