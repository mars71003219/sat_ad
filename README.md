# 위성 텔레메트리 이상 감지 시스템

이벤트 기반 배치 처리 아키텍처를 사용하는 위성 텔레메트리 이상 감지 시스템입니다.

## 시스템 개요

이 시스템은 복수의 위성에서 배치 형태로 전송되는 텔레메트리 데이터를 실시간으로 수집하고, 배치 전송이 완료되면 자동으로 추론을 트리거하여 이상을 감지합니다.

### 주요 특징

- 이벤트 기반 배치 처리 (폴링 방식 없음)
- 9시간 배치 데이터 (1,080개 레코드)
- 슬라이딩 윈도우 추론 (윈도우 크기: 30, 스트라이드: 10)
- 4개 서브시스템 지원 (EPS, Thermal, AOCS, Comm)
- 분산 추론 처리 (Celery)
- 실시간 대시보드

## 아키텍처

### 데이터 흐름

```
위성 → Kafka → VictoriaMetrics
         ↓
   Batch Trigger → Celery → Analysis Worker → Kafka
                                                ↓
                                         VictoriaMetrics
                                                ↓
                                         Dashboard
```

### 서비스 구성

1. **Kafka**: 메시지 버스 (텔레메트리 데이터, 추론 결과)
2. **RabbitMQ**: Celery 브로커 (추론 작업 큐)
3. **VictoriaMetrics**: 시계열 데이터베이스
4. **PostgreSQL**: 시스템 설정 저장소
5. **Triton Server**: AI 추론 서버 (Mock)
6. **Batch Simulator**: 위성 데이터 시뮬레이터
7. **Victoria Consumer**: Kafka → VictoriaMetrics 데이터 파이프라인
8. **Batch Inference Trigger**: 배치 완료 감지 및 추론 트리거
9. **Analysis Worker**: 분산 추론 작업자
10. **Operation Server**: REST API 서버
11. **Frontend**: React 대시보드
12. **Nginx**: 리버스 프록시

## 배치 처리 메커니즘

### 배치 데이터 구조

각 텔레메트리 메시지는 다음 메타데이터를 포함합니다:

- `batch_id`: 배치 고유 식별자
- `record_index`: 배치 내 레코드 순번
- `is_last_record`: 배치 마지막 레코드 여부

### 배치 완료 감지

Batch Inference Trigger는 Kafka에서 텔레메트리 메시지를 실시간으로 컨슘하며, `is_last_record=true`를 감지하면 배치 전송이 완료된 것으로 판단합니다.

### 슬라이딩 윈도우 추론

배치 완료 후 다음 파라미터로 슬라이딩 윈도우를 생성합니다:

- **배치 크기**: 1,080개 레코드 (9시간 × 120 레코드/시간)
- **윈도우 크기**: 30개 레코드 (15분)
- **스트라이드**: 10개 레코드 (5분)
- **윈도우 개수**: (1,080 - 30) / 10 + 1 = 106개
- **추론 작업 수**: 106 × 4 서브시스템 = 424개

## 빠른 시작

### 사전 요구사항

- Docker 및 Docker Compose
- 최소 8GB RAM
- 10GB 디스크 공간

### 설치 및 실행

1. 프로젝트 클론

```bash
cd /mnt/c/projects/telemetry_anomaly_det
```

2. Kafka 클러스터 ID 생성

```bash
bash init-kafka.sh
```

3. 전체 시스템 실행

```bash
docker-compose up -d
```

4. 시뮬레이터 실행 (별도 터미널)

```bash
docker-compose run --rm batch-simulator
```

### 서비스 접속

- **Dashboard**: http://localhost
- **Operation Server API**: http://localhost/api
- **Kafka UI**: http://localhost:8080
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)
- **Flower (Celery)**: http://localhost:5555
- **VictoriaMetrics**: http://localhost:8428

## API 엔드포인트

### Dashboard API

- `GET /api/dashboard/stats`: 전체 통계
- `GET /api/dashboard/anomalies?hours=24`: 최근 이상 감지 결과

### Configuration API

- `GET /api/config/system`: 시스템 설정
- `GET /api/config/models`: 모델 설정
- `GET /api/config/satellites`: 위성 설정

### Inference API

- `GET /api/inference/recent?limit=100`: 최근 추론 결과
- `GET /api/inference/statistics`: 추론 통계

## 디렉토리 구조

```
telemetry_anomaly_det/
├── batch-simulator/         # 위성 데이터 시뮬레이터
├── inference-trigger/        # 배치 추론 트리거
├── analysis-worker/          # 추론 작업자
├── victoria-consumer/        # Kafka → VictoriaMetrics
├── operation-server/         # REST API 서버
├── frontend/                 # React 대시보드
├── nginx/                    # Nginx 설정
├── database/                 # PostgreSQL 스키마
├── triton-models/            # Triton 모델 리포지토리
├── shared/                   # 공유 코드
├── docker-compose.yml        # Docker Compose 설정
└── init-kafka.sh             # Kafka 초기화 스크립트
```

## 모니터링

### Kafka 메시지 확인

Kafka UI (http://localhost:8080)에서 다음 토픽을 모니터링할 수 있습니다:

- `satellite-telemetry`: 위성 텔레메트리 데이터
- `inference-results`: 추론 결과

### Celery 작업 모니터링

Flower (http://localhost:5555)에서 추론 작업 상태를 실시간으로 확인할 수 있습니다.

### VictoriaMetrics 쿼리

VictoriaMetrics (http://localhost:8428)에서 PromQL 쿼리를 실행할 수 있습니다:

```promql
# 위성별 텔레메트리 데이터
satellite_telemetry{satellite_id="SAT-001"}

# 이상 감지 결과
inference_anomaly_score{subsystem="eps"}
```

## 개발

### 로컬 개발 환경

각 서비스는 독립적으로 개발할 수 있습니다:

```bash
# Operation Server
cd operation-server
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm start
```

### 로그 확인

```bash
# 전체 서비스 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f batch-inference-trigger
docker-compose logs -f analysis-worker
```

## 설정

### 배치 파라미터 조정

`docker-compose.yml`에서 환경 변수를 수정하여 배치 파라미터를 조정할 수 있습니다:

```yaml
environment:
  - WINDOW_SIZE=30        # 윈도우 크기 (레코드 수)
  - STRIDE=10             # 스트라이드 (레코드 수)
  - FORECAST_HORIZON=10   # 예측 범위 (레코드 수)
```

### PostgreSQL 설정

`database/init.sql`에서 초기 시스템 설정을 수정할 수 있습니다.

## 서브시스템 상세

### EPS (전력 시스템)

12개 특징: 전압, 전류, 배터리 상태 등

### Thermal (온도 시스템)

6개 특징: 각종 센서 온도

### AOCS (자세제어 시스템)

12개 특징: 자이로스코프, 가속도계, 자기장 센서 등

### Comm (통신 시스템)

3개 특징: 신호 강도, 데이터 전송률 등

## 문제 해결

### Kafka 초기화 오류

Kafka 클러스터 ID가 없으면 초기화에 실패합니다. 다음 명령으로 재생성하세요:

```bash
rm .env
bash init-kafka.sh
docker-compose up -d kafka
```

### PostgreSQL 연결 오류

PostgreSQL이 완전히 시작되지 않은 상태에서 다른 서비스가 시작되면 연결 오류가 발생할 수 있습니다:

```bash
docker-compose restart operation-server
```

### 추론 작업이 실행되지 않음

RabbitMQ와 Analysis Worker 상태를 확인하세요:

```bash
docker-compose logs rabbitmq
docker-compose logs analysis-worker
```

## 라이선스

MIT License
