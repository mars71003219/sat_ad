#!/bin/bash
# 토픽 중심 아키텍처 - 공용 토픽 생성

set -e

KAFKA_CONTAINER="kafka"
PARTITIONS=5  # 위성 수
REPLICATION=1

echo "=========================================="
echo "Creating Topic-Centric Public Topics"
echo "=========================================="

# Raw 토픽 (시뮬레이터 → Demux)
echo "Creating: satellite-telemetry-raw"
docker exec $KAFKA_CONTAINER kafka-topics \
  --bootstrap-server localhost:9092 \
  --create \
  --topic satellite-telemetry-raw \
  --partitions $PARTITIONS \
  --replication-factor $REPLICATION \
  --if-not-exists \
  --config retention.ms=86400000

# 공용 토픽 (Demux → 모든 서비스)
declare -a PUBLIC_TOPICS=(
  "telemetry.public.eps:Electric Power System"
  "telemetry.public.aocs:Attitude Control System"
  "telemetry.public.fsw:Flight Software"
  "telemetry.public.thermal:Thermal Control System"
  "telemetry.public.data:Data Handling"
  "telemetry.public.struct:Structure System"
  "telemetry.public.propulsion:Propulsion System"
)

for topic_info in "${PUBLIC_TOPICS[@]}"; do
  topic="${topic_info%%:*}"
  desc="${topic_info##*:}"

  echo "Creating: $topic ($desc)"
  docker exec $KAFKA_CONTAINER kafka-topics \
    --bootstrap-server localhost:9092 \
    --create \
    --topic $topic \
    --partitions $PARTITIONS \
    --replication-factor $REPLICATION \
    --if-not-exists \
    --config retention.ms=86400000
done

# Inference Results (기존)
echo "Creating: inference-results"
docker exec $KAFKA_CONTAINER kafka-topics \
  --bootstrap-server localhost:9092 \
  --create \
  --topic inference-results \
  --partitions $PARTITIONS \
  --replication-factor $REPLICATION \
  --if-not-exists \
  --config retention.ms=86400000

echo ""
echo "=========================================="
echo "Topic Creation Complete"
echo "=========================================="
echo ""

# 토픽 리스트
echo "All topics:"
docker exec $KAFKA_CONTAINER kafka-topics \
  --bootstrap-server localhost:9092 \
  --list

echo ""
echo "=========================================="
echo "Architecture Summary"
echo "=========================================="
echo ""
echo "Data Flow:"
echo "  Simulator → satellite-telemetry-raw"
echo "           → Demux (범용, 서비스 무관)"
echo "           → telemetry.public.* (공용 토픽)"
echo "           → [Anomaly, Scheduling, Health, ...] (독립 Consumer)"
echo ""
echo "Extensibility:"
echo "  - 새 서비스 추가: Demux 수정 불필요"
echo "  - 같은 토픽을 여러 서비스가 구독 가능"
echo "  - Consumer Group으로 독립성 보장"
echo ""
echo "=========================================="
