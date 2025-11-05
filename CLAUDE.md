# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

위성 텔레메트리 이상 감지 시스템 - 이벤트 기반 배치 처리 아키텍처를 사용하는 실시간 분석 시스템입니다.

배치 데이터를 Kafka로 수신하여 배치 완료 시 슬라이딩 윈도우로 자동 추론을 트리거하고, 결과를 VictoriaMetrics에 저장하여 대시보드로 실시간 모니터링합니다.

## 핵심 명령어

### 시스템 실행

```bash
# Kafka 클러스터 ID 초기화 (최초 1회)
bash init_kafka.sh

# 전체 시스템 시작
bash start.sh
# 또는
docker-compose up -d

# 시스템 종료
bash stop.sh
# 또는
docker-compose down

# 특정 서비스 재시작
docker-compose restart <service-name>
```

### 시뮬레이터 실행

```bash
# 배치 시뮬레이터 실행 (위성 데이터 생성)
bash run-simulator.sh
# 또는
docker-compose run --rm batch-simulator
```

### 로그 확인

```bash
# 전체 서비스 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f batch-inference-trigger
docker-compose logs -f analysis-worker
docker-compose logs -f victoria-consumer

# 실시간 로그 스트림
docker-compose logs -f --tail=100 <service-name>
```

### 개발 모드 실행

```bash
# Operation Server (FastAPI)
cd operation-server
pip install -r requirements.txt
uvicorn main:app --reload --port 8003

# Frontend (React)
cd frontend
npm install
npm start
```

## 아키텍처

### 데이터 흐름 (배치 기반 이벤트 드리븐)

```
위성 시뮬레이터 (배치 전송)
  → Kafka (satellite-telemetry 토픽)
    → Victoria Consumer → VictoriaMetrics (시계열 저장)
    → Batch Inference Trigger (배치 완료 감지: is_last_record=true)
      → RabbitMQ (Celery 작업 큐)
        → Analysis Worker (슬라이딩 윈도우 추론)
          → Triton Server (Mock GPU 추론)
            → Kafka (inference-results 토픽)
              → VictoriaMetrics (추론 결과 저장)
                → Dashboard (실시간 모니터링)
```

### 배치 처리 메커니즘

- **배치 크기**: 1,080개 레코드 (9시간 × 120 레코드/시간, 30초 간격)
- **윈도우 크기**: 30개 레코드 (15분)
- **스트라이드**: 10개 레코드 (5분)
- **윈도우 개수**: 106개 윈도우/배치
- **추론 작업 수**: 424개 (106 윈도우 × 4 서브시스템)

배치 메시지에는 `batch_id`, `record_index`, `is_last_record` 메타데이터가 포함되며, Batch Inference Trigger는 `is_last_record=true`를 감지하면 배치 완료로 판단하여 슬라이딩 윈도우 추론을 트리거합니다.

### 서비스 구성 요소

**데이터 입력 계층**
- `batch-simulator`: 위성 데이터 시뮬레이터 (배치 전송 모드)

**메시징 계층**
- `kafka`: 이벤트 스트리밍 (KRaft 모드)
- `rabbitmq`: Celery 작업 큐

**저장 계층**
- `victoria-consumer`: Kafka → VictoriaMetrics 데이터 파이프라인
- `victoria-metrics`: 시계열 DB (텔레메트리 + 추론 결과)
- `postgres`: 시스템 설정 DB

**추론 계층**
- `batch-inference-trigger`: 배치 완료 감지 및 슬라이딩 윈도우 추론 트리거
- `analysis-worker`: Celery 워커 (분산 추론 처리)
- `triton-server`: Mock AI 추론 서버

**API/UI 계층**
- `operation-server`: FastAPI REST API (포트 8003)
- `frontend`: React 대시보드
- `nginx`: 리버스 프록시 (포트 80)

**모니터링 계층**
- `kafka-ui`: Kafka 모니터링 (포트 8080)
- `flower`: Celery 모니터링 (포트 5555)

### 서브시스템 및 모델

**4개 서브시스템**:
1. **EPS (전력)**: 12개 특징 - 배터리 전압/SOC/전류/온도, 태양전지판 전압/전류, 전력 소비/생성
2. **Thermal (온도)**: 6개 특징 - 배터리/OBC/통신/페이로드/태양전지판/외부 온도
3. **AOCS (자세제어)**: 12개 특징 - 자이로/태양각/자기장/반작용휠/고도/속도
4. **Comm (통신)**: 3개 특징 - RSSI, 데이터 백로그, 마지막 접촉

**추론 모델**: LSTM Timeseries (Triton Server)
- 입력: 30개 시퀀스 (15분)
- 출력: 10스텝 예측 (5분)

## 데이터베이스 역할

### PostgreSQL (시스템 설정 전용)
- `system_config`: Triton, Kafka, VictoriaMetrics 설정
- `model_config`: 모델별 추론 파라미터
- `satellite_config`: 위성 설정
- `kafka_topic_config`, `victoria_metrics_config`

### VictoriaMetrics (시계열 + 추론 결과)
- 모든 위성 텔레메트리 데이터
- 추론 결과 메트릭: `inference_anomaly_score`, `inference_anomaly_detected`, `inference_time_ms`, `inference_prediction_*`, `inference_confidence_mean`, `inference_job_status`

## 개발 가이드

### 슬라이딩 윈도우 파라미터 변경

`docker-compose.yml`에서 환경 변수 수정:

```yaml
batch-inference-trigger:
  environment:
    - WINDOW_SIZE=30        # 윈도우 크기 (레코드 수)
    - STRIDE=10             # 스트라이드 (레코드 수)
    - FORECAST_HORIZON=10   # 예측 범위 (레코드 수)
```

### 새로운 서브시스템 추가

1. `inference-trigger/trigger.py`의 `SUBSYSTEM_FEATURES`에 특징 추가
2. `triton-models/transformer_<subsystem>/config.pbtxt` 모델 설정 추가
3. `triton-models/transformer_<subsystem>/1/model.py` 모델 로직 추가
4. `database/init.sql`에 모델 설정 추가

### Celery Worker 스케일링

```bash
# Worker 수 증가
docker-compose up -d --scale analysis-worker=4

# Worker 동시성 조정 (docker-compose.yml)
environment:
  - CELERY_CONCURRENCY=4
```

### API 엔드포인트 추가

`operation-server/api/routes/`에 새로운 라우터 추가 후 `main.py`에 등록:

```python
from api.routes import new_route
app.include_router(new_route.router)
```

## 공유 모듈

`shared/config/settings.py`: 모든 서비스에서 사용하는 설정 클래스

주요 환경 변수:
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka 서버 (기본값: kafka:9092)
- `CELERY_BROKER_URL`: RabbitMQ URL
- `VICTORIA_METRICS_URL`: VictoriaMetrics URL
- `TRITON_SERVER_URL`: Triton 서버 URL

## 문제 해결

### Kafka 초기화 실패
```bash
rm .env
bash init_kafka.sh
docker-compose up -d kafka
```

### PostgreSQL 연결 오류
서비스가 너무 빨리 시작되면 연결 실패 가능:
```bash
docker-compose restart operation-server
```

### RabbitMQ 연결 실패
healthcheck 대기 후 재시작:
```bash
docker-compose logs rabbitmq
docker-compose restart batch-inference-trigger analysis-worker
```

### 추론 작업이 실행되지 않음
1. RabbitMQ 상태 확인: http://localhost:15672
2. Celery Worker 로그 확인: `docker-compose logs -f analysis-worker`
3. Flower에서 작업 큐 확인: http://localhost:5555

## 서비스 URL

- Dashboard: http://localhost
- API Server: http://localhost/api
- Kafka UI: http://localhost:8080
- RabbitMQ Management: http://localhost:15672 (guest/guest)
- Flower (Celery): http://localhost:5555
- VictoriaMetrics: http://localhost:8428
