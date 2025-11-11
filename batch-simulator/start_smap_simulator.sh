#!/bin/bash
# SMAP 시뮬레이터 실행 스크립트

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 기본 설정
KAFKA_SERVERS="${KAFKA_SERVERS:-kafka:9092}"
NUM_SATELLITES="${NUM_SATELLITES:-5}"
LOOPS="${LOOPS:-1}"
DELAY_MS="${DELAY_MS:-1000}"
DATA_DIR="${DATA_DIR:-./data}"

# 도움말 출력
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    cat <<EOF
SMAP 위성 텔레메트리 시뮬레이터 실행 스크립트

사용법:
  bash start_smap_simulator.sh [옵션]

환경 변수:
  KAFKA_SERVERS     Kafka 서버 주소 (기본값: kafka:9092)
  NUM_SATELLITES    위성 개수 1-5 (기본값: 5)
  LOOPS             반복 재생 횟수 (기본값: 1)
  DELAY_MS          레코드 간 딜레이(ms) (기본값: 1000)
  DATA_DIR          데이터 디렉토리 (기본값: ./data)

예시:
  # 5개 위성, 1회 재생, 1초 간격
  bash start_smap_simulator.sh

  # 3개 위성, 5회 재생, 500ms 간격
  NUM_SATELLITES=3 LOOPS=5 DELAY_MS=500 bash start_smap_simulator.sh

  # Docker 컨테이너에서 실행
  docker run --rm --network satellite_webnet \\
    -v $(pwd)/data:/app/data \\
    -w /app \\
    python:3.10-slim \\
    bash -c "pip install -q confluent-kafka numpy && python smap_simulator.py --kafka kafka:9092 --satellites 5 --loops 1"

EOF
    exit 0
fi

echo "=================================="
echo "SMAP 시뮬레이터 시작"
echo "=================================="
echo "Kafka:       $KAFKA_SERVERS"
echo "위성 개수:   $NUM_SATELLITES"
echo "반복 횟수:   $LOOPS"
echo "레코드 간격: ${DELAY_MS}ms"
echo "데이터 경로: $DATA_DIR"
echo "=================================="
echo ""

# Python 의존성 확인
if ! python3 -c "import confluent_kafka" 2>/dev/null; then
    echo "Installing confluent-kafka..."
    pip install -q confluent-kafka
fi

if ! python3 -c "import numpy" 2>/dev/null; then
    echo "Installing numpy..."
    pip install -q numpy
fi

# 시뮬레이터 실행
python3 smap_simulator.py \
    --kafka "$KAFKA_SERVERS" \
    --satellites "$NUM_SATELLITES" \
    --loops "$LOOPS" \
    --delay "$DELAY_MS" \
    --data-dir "$DATA_DIR"
