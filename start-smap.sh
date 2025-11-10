#!/bin/bash
# Start SMAP Anomaly Detection System

set -e

echo "========================================="
echo "  SMAP Anomaly Detection System Startup"
echo "========================================="
echo ""

# Check if base infrastructure is running
echo "Checking base infrastructure..."
if ! docker network inspect telemetry-net >/dev/null 2>&1; then
    echo "Creating telemetry-net network..."
    docker network create telemetry-net
fi

# Start base services if not running
echo "Starting base services (Kafka, RabbitMQ, VictoriaMetrics)..."
docker compose up -d kafka rabbitmq redis victoria-metrics

# Wait for services to be ready
echo "Waiting for services to be healthy..."
sleep 10

# Start SMAP-specific services
echo "Starting SMAP services..."
docker compose -f docker-compose.smap.yml up -d --build

echo ""
echo "========================================="
echo "  SMAP System Started"
echo "========================================="
echo ""
echo "Services:"
echo "  - Triton OmniAnomaly: http://localhost:8100/v2/health/ready"
echo "  - Kafka UI: http://localhost:8080"
echo "  - VictoriaMetrics: http://localhost:8428"
echo "  - RabbitMQ: http://localhost:15672 (guest/guest)"
echo ""
echo "SMAP Components:"
echo "  - smap-simulator: Sending test data"
echo "  - smap-inference-trigger: Consuming telemetry"
echo "  - smap-analysis-worker: Running OmniAnomaly inference"
echo "  - smap-victoria-consumer: Writing results to VictoriaMetrics"
echo ""
echo "Check logs:"
echo "  docker compose -f docker-compose.smap.yml logs -f"
echo ""
echo "Check specific service:"
echo "  docker compose -f docker-compose.smap.yml logs -f triton-omnianomaly"
echo "  docker compose -f docker-compose.smap.yml logs -f smap-simulator"
echo "  docker compose -f docker-compose.smap.yml logs -f smap-analysis-worker"
echo ""
echo "Stop system:"
echo "  docker compose -f docker-compose.smap.yml down"
echo ""
