#!/bin/bash

# 배치 시뮬레이터 실행 스크립트

set -e

echo "=========================================="
echo "배치 시뮬레이터 실행"
echo "=========================================="

# 파라미터 설정
SATELLITES=${1:-3}
BATCH_DURATION=${2:-32400}

echo ""
echo " 설정:"
echo "  - 위성 개수: $SATELLITES"
echo "  - 배치 시간: $BATCH_DURATION 초 ($(($BATCH_DURATION / 3600)) 시간)"
echo ""

# Docker 컨테이너로 시뮬레이터 실행
docker compose run --rm batch-simulator \
  python simulator.py \
  --kafka kafka:9092 \
  --satellites $SATELLITES \
  --batch-duration $BATCH_DURATION

echo ""
echo " 시뮬레이터 종료"
echo ""
