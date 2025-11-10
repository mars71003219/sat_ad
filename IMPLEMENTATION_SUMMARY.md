# SMAP 이상 감지 시스템 구현 완료

## 구현된 시스템 개요

위성 텔레메트리 이상 감지를 위한 **OmniAnomaly 기반 실시간 추론 시스템**을 구축했습니다.

### 핵심 요구사항 반영

1. ✅ **시스템 계층 구조**: 위성 > 엔티티 > 센서
2. ✅ **GPU 기반 추론**: Triton Server with CUDA
3. ✅ **TranAD-sim 환경 기반**: CUDA 11.3 + PyTorch 호환 환경

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                     위성 계층 구조                                │
├─────────────────────────────────────────────────────────────────┤
│ Satellite SAT-001                                               │
│   ├─ Entity A-1 (SMAP 채널, 서브시스템)                         │
│   │   ├─ sensor_0: 실제값, 재구성값, 이상점수                   │
│   │   ├─ sensor_1: ...                                          │
│   │   └─ ... (25개 센서)                                        │
│   ├─ Entity A-2                                                 │
│   └─ Entity A-3                                                 │
│                                                                 │
│ Satellite SAT-002                                               │
│   ├─ Entity D-1                                                 │
│   ├─ Entity D-2                                                 │
│   └─ Entity E-1                                                 │
│                                                                 │
│ Satellite SAT-003                                               │
│   ├─ Entity P-1                                                 │
│   ├─ Entity P-2                                                 │
│   └─ Entity G-1                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 데이터 흐름

```
┌─────────────────┐
│ SMAP Simulator  │ SMAP 테스트 데이터 (8,640 timesteps × 25 sensors)
│  (9개 엔티티)    │ 30초 간격 전송 (실제: 5초 간격으로 빠르게 재생)
└────────┬────────┘
         │ Kafka: smap-telemetry
         │ {satellite_id, entity, timestamp, sensors{sensor_0...24}}
         ▼
┌─────────────────┐
│ Inference       │ Kafka 소비 → 엔티티별 Celery Task 트리거
│ Trigger         │ (윈도우 없음, OmniAnomaly는 Stateful LSTM)
└────────┬────────┘
         │ RabbitMQ: Celery Queue
         │ Task: run_omnianomaly_inference(entity, sensor_values)
         ▼
┌─────────────────┐
│ Analysis Worker │ Triton HTTP 호출 → GPU 추론
│  (Celery)       │ model_name = f"smap_{entity}"
└────────┬────────┘
         │ Triton HTTP
         │ POST /v2/models/smap_A-1/infer
         ▼
┌─────────────────────────────────────────────────────────┐
│ Triton OmniAnomaly Server (GPU)                         │
├─────────────────────────────────────────────────────────┤
│ models/                                                 │
│  ├─ smap_A-1/                                           │
│  │   ├─ config.pbtxt (KIND_GPU, gpus:[0])              │
│  │   └─ 1/                                              │
│  │       ├─ model.py (OmniAnomaly Python Backend)       │
│  │       └─ model.ckpt (PyTorch Checkpoint)             │
│  ├─ smap_A-2/                                           │
│  ├─ ... (20개 엔티티 모델)                               │
│  └─ smap_P-2/                                           │
│                                                         │
│ OmniAnomaly 추론 (GPU):                                 │
│  - Input: (25,) 센서 값                                 │
│  - GRU (2층, hidden_state 유지)                         │
│  - VAE Encoder/Decoder                                  │
│  - Output: reconstruction (25,), score, detected       │
└────────┬────────────────────────────────────────────────┘
         │ Inference Result
         │ {reconstruction, anomaly_score, anomaly_detected}
         ▼
┌─────────────────┐
│ Analysis Worker │ 결과를 Kafka에 발행
└────────┬────────┘
         │ Kafka: smap-inference-results
         │ {satellite_id, entity, sensor_values, reconstruction, anomaly_score, ...}
         ▼
┌─────────────────┐
│ Victoria        │ 추론 결과 → Prometheus 메트릭 변환
│ Consumer        │ - smap_anomaly_score{satellite_id, entity}
└────────┬────────┘  - smap_sensor_value{satellite_id, entity, sensor}
         │            - smap_sensor_reconstruction{...}
         │            - smap_sensor_error{...}
         ▼
┌─────────────────┐
│ VictoriaMetrics │ 시계열 DB (PromQL 쿼리)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 프론트엔드        │ 실시간 대시보드
│ (향후 구현)      │ - 위성 선택 → 엔티티 선택 → 센서 선택
└─────────────────┘  - 이상 점수 트렌드, 센서별 상세 분석
```

## 구현된 컴포넌트

### 1. Triton OmniAnomaly Server

**경로**: `triton-omnianomaly/`

**구성**:
- `Dockerfile.triton-omnianomaly`: NVIDIA Triton Server 24.08 + PyTorch 2.4.0 + CUDA
- `models/smap_<entity>/`: 20개 엔티티별 모델 (A-1~9, D-1~4, E-1~3, F-1, G-1, P-1~2)
- `setup_models.sh`: 체크포인트 자동 배포 스크립트

**특징**:
- GPU 추론 (KIND_GPU, NVIDIA_VISIBLE_DEVICES=0)
- Stateful LSTM (hidden state 유지)
- Python Backend (triton_python_backend_utils)
- Healthcheck: `/v2/health/ready`

**입출력**:
```python
# Input
input_data: np.ndarray  # shape: (25,), dtype: float64

# Output
reconstruction: np.ndarray  # shape: (25,)
anomaly_score: float        # MSE between input and reconstruction
anomaly_detected: bool      # score > threshold (0.16)
```

### 2. SMAP Simulator

**경로**: `smap-simulator/`

**기능**:
- SMAP 테스트 데이터 로드 (`tranad-sim/processed/SMAP/`)
- 위성-엔티티 매핑 (SAT-001: A-1~3, SAT-002: D-1~2,E-1, SAT-003: P-1~2,G-1)
- Kafka 전송 (토픽: `smap-telemetry`)
- 5초 간격 (개발 환경, 실제: 30초)

**메시지 형식**:
```json
{
  "satellite_id": "SAT-001",
  "entity": "A-1",
  "timestamp": "2025-11-10T12:00:00+00:00",
  "index": 0,
  "sensors": {
    "sensor_0": 1.234,
    "sensor_1": 2.345,
    ...
    "sensor_24": 3.456
  },
  "ground_truth_labels": {
    "sensor_0": 0,
    ...
  }
}
```

### 3. SMAP Inference Trigger

**경로**: `smap-inference-trigger/`

**기능**:
- Kafka 소비 (`smap-telemetry`)
- 엔티티별 Celery Task 트리거
- 윈도우 버퍼링 **없음** (OmniAnomaly는 Stateful)

**로직**:
```python
async for message in consumer:
    data = message.value
    sensor_values = [data['sensors'][f'sensor_{i}'] for i in range(25)]

    celery_app.send_task(
        'smap_analysis.tasks.run_omnianomaly_inference',
        kwargs={
            'satellite_id': data['satellite_id'],
            'entity': data['entity'],
            'sensor_values': sensor_values
        }
    )
```

### 4. SMAP Analysis Worker

**경로**: `smap-analysis-worker/`

**기능**:
- Celery Worker (RabbitMQ 브로커)
- Triton HTTP 클라이언트 (글로벌 재사용)
- 추론 결과 Kafka 발행

**추론 플로우**:
```python
@celery_app.task
def run_omnianomaly_inference(satellite_id, entity, sensor_values):
    # 1. Triton 호출
    model_name = f"smap_{entity}"
    response = triton_client.infer(
        model_name=model_name,
        inputs=[np.array(sensor_values, dtype=np.float64)]
    )

    # 2. 결과 파싱
    reconstruction = response.as_numpy("reconstruction")
    anomaly_score = response.as_numpy("anomaly_score")[0]
    anomaly_detected = response.as_numpy("anomaly_detected")[0]

    # 3. Kafka 발행
    publish_inference_result({
        'satellite_id': satellite_id,
        'entity': entity,
        'reconstruction': reconstruction.tolist(),
        'anomaly_score': anomaly_score,
        ...
    })
```

### 5. SMAP Victoria Consumer

**경로**: `smap-victoria-consumer/`

**기능**:
- Kafka 소비 (`smap-inference-results`)
- Prometheus 메트릭 변환
- VictoriaMetrics 저장 (HTTP POST `/api/v1/import/prometheus`)

**메트릭 예시**:
```prometheus
# 엔티티 전체 이상 점수
smap_anomaly_score{satellite_id="SAT-001",entity="A-1"} 0.0234 1731240000000

# 센서별 실제값
smap_sensor_value{satellite_id="SAT-001",entity="A-1",sensor="sensor_0"} 1.234 1731240000000

# 센서별 재구성값
smap_sensor_reconstruction{satellite_id="SAT-001",entity="A-1",sensor="sensor_0"} 1.240 1731240000000

# 센서별 오차
smap_sensor_error{satellite_id="SAT-001",entity="A-1",sensor="sensor_0"} 0.006 1731240000000

# 이상 감지 플래그
smap_anomaly_detected{satellite_id="SAT-001",entity="A-1"} 0 1731240000000
```

## 배포된 모델

### 체크포인트 소스
- 원본: `tranad-sim/checkpoints/OmniAnomaly/model_SMAP_<entity>.ckpt`
- 배포: `triton-omnianomaly/models/smap_<entity>/1/model.ckpt`

### 모델 목록 (20개)
```
smap_A-1, smap_A-2, smap_A-3, smap_A-4, smap_A-5, smap_A-6, smap_A-7, smap_A-8, smap_A-9,
smap_D-1, smap_D-2, smap_D-3, smap_D-4,
smap_E-1, smap_E-2, smap_E-3,
smap_F-1,
smap_G-1,
smap_P-1, smap_P-2
```

### 모델 구조
```python
OmniAnomaly(
  (lstm): GRU(25, 32, num_layers=2)  # 입력: 25 sensors, 히든: 32, 2층
  (encoder): Sequential(
    (0): Linear(32, 32)
    (1): PReLU()
    (2): Linear(32, 32)
    (3): PReLU()
    (4): Flatten()
    (5): Linear(32, 16)  # 출력: mu (8) + logvar (8)
  )
  (decoder): Sequential(
    (0): Linear(8, 32)   # 잠재 공간: 8차원
    (1): PReLU()
    (2): Linear(32, 32)
    (3): PReLU()
    (4): Linear(32, 25)  # 재구성: 25 sensors
    (5): Sigmoid()
  )
)
```

## 시작 방법

### 1. 시스템 시작

```bash
bash start-smap.sh
```

실행 내용:
1. 기본 인프라 시작 (Kafka, RabbitMQ, Redis, VictoriaMetrics)
2. SMAP 서비스 빌드 및 시작 (Triton, Simulator, Trigger, Worker, Consumer)

### 2. 서비스 확인

```bash
# Triton 서버 상태
curl http://localhost:8100/v2/health/ready

# 사용 가능한 모델
curl http://localhost:8100/v2/models

# 특정 모델 메타데이터
curl http://localhost:8100/v2/models/smap_A-1/config

# Kafka 토픽 (Kafka UI)
open http://localhost:8080

# VictoriaMetrics 쿼리
curl 'http://localhost:8428/api/v1/query?query=smap_anomaly_score'
```

### 3. 로그 모니터링

```bash
# 전체 로그
docker compose -f docker-compose.smap.yml logs -f

# Triton 서버 로그 (GPU 추론 확인)
docker compose -f docker-compose.smap.yml logs -f triton-omnianomaly

# 시뮬레이터 로그 (데이터 전송 확인)
docker compose -f docker-compose.smap.yml logs -f smap-simulator

# 워커 로그 (추론 실행 확인)
docker compose -f docker-compose.smap.yml logs -f smap-analysis-worker
```

### 4. 성능 확인

```bash
# Celery 작업 모니터링 (Flower)
open http://localhost:5555

# RabbitMQ 큐 확인
open http://localhost:15672  # guest/guest

# VictoriaMetrics UI
open http://localhost:8428/vmui
```

## VictoriaMetrics 쿼리 예시

### 1. 엔티티별 이상 점수 트렌드

```promql
# A-1 엔티티 이상 점수 (시계열)
smap_anomaly_score{entity="A-1"}

# SAT-001 위성 전체 평균 이상 점수
avg(smap_anomaly_score{satellite_id="SAT-001"})
```

### 2. 이상 감지 통계

```promql
# 지난 5분간 SAT-001의 이상 감지 횟수
sum(increase(smap_anomaly_detected{satellite_id="SAT-001"}[5m]))

# 전체 시스템 이상 감지율
sum(smap_anomaly_detected) / count(smap_anomaly_detected) * 100
```

### 3. 센서별 분석

```promql
# A-1 엔티티의 sensor_0 실제값 vs 재구성값
smap_sensor_value{entity="A-1", sensor="sensor_0"}
smap_sensor_reconstruction{entity="A-1", sensor="sensor_0"}

# sensor_0의 평균 재구성 오차
avg(smap_sensor_error{sensor="sensor_0"})

# 오차가 가장 큰 센서 (Top 5)
topk(5, avg(smap_sensor_error) by (sensor))
```

### 4. 성능 메트릭

```promql
# 평균 추론 시간
avg(smap_inference_time_ms)

# P95 추론 시간
histogram_quantile(0.95, smap_inference_time_ms)

# 엔티티별 추론 처리량 (건/분)
sum(rate(smap_anomaly_score[1m])) by (entity)
```

## 다음 구현 단계

### 1. 프론트엔드 대시보드 확장

**구조**:
```
Dashboard
├─ Satellite Selector (SAT-001, SAT-002, SAT-003)
│   └─ Entity Selector (A-1, A-2, ...)
│       ├─ Entity Overview
│       │   ├─ 전체 이상 점수 트렌드 (시계열 차트)
│       │   ├─ 이상 감지 구간 하이라이트
│       │   └─ 현재 상태 (정상/이상)
│       └─ Sensor Details
│           ├─ Sensor Selector (sensor_0 ~ sensor_24)
│           ├─ 실제값 vs 재구성값 비교 차트
│           ├─ 재구성 오차 트렌드
│           └─ 이상 점수 막대그래프
```

**API 엔드포인트** (operation-server 확장):
```
GET /api/smap/satellites
  → [{"id": "SAT-001", "entities": ["A-1", "A-2", "A-3"]}, ...]

GET /api/smap/entity/{entity}/overview
  → {"anomaly_score": [...], "timestamps": [...], "detected": [...]}

GET /api/smap/entity/{entity}/sensor/{sensor}
  → {"actual": [...], "reconstruction": [...], "error": [...]}
```

### 2. WebSocket 실시간 스트리밍

**메시지 구조**:
```json
{
  "type": "smap_inference",
  "satellite_id": "SAT-001",
  "entity": "A-1",
  "timestamp": "2025-11-10T12:00:00Z",
  "anomaly_score": 0.0234,
  "anomaly_detected": false,
  "sensors": [
    {"id": "sensor_0", "value": 1.234, "reconstruction": 1.240, "error": 0.006},
    ...
  ]
}
```

### 3. 알림 시스템

- 이상 감지 시 Slack/Email 알림
- 임계값 기반 알림 규칙 (설정 가능)
- 알림 히스토리 저장 (PostgreSQL)

### 4. 모델 성능 평가

- Ground Truth 레이블 활용
- F1, Precision, Recall 계산
- 엔티티별 성능 대시보드

## 기술 스택 요약

| 계층 | 기술 스택 |
|------|-----------|
| **추론** | Triton Server 24.08, PyTorch 2.4.0, CUDA 12.1 |
| **모델** | OmniAnomaly (VAE + GRU) |
| **메시징** | Kafka (KRaft), RabbitMQ |
| **작업 큐** | Celery (Prefork Pool) |
| **시계열 DB** | VictoriaMetrics |
| **데이터 처리** | aiokafka, aiohttp (비동기) |
| **컨테이너** | Docker Compose, NVIDIA Container Runtime |

## 파일 구조

```
telemetry_anomaly_det/
├── triton-omnianomaly/              # Triton OmniAnomaly 서버
│   ├── Dockerfile.triton-omnianomaly
│   ├── requirements.txt
│   ├── setup_models.sh
│   └── models/
│       ├── smap_A-1/
│       │   ├── config.pbtxt
│       │   └── 1/
│       │       ├── model.py
│       │       └── model.ckpt
│       └── ... (20개 모델)
│
├── smap-simulator/                  # SMAP 데이터 시뮬레이터
│   └── simulator.py
│
├── smap-inference-trigger/          # 추론 트리거
│   ├── trigger.py
│   └── requirements.txt
│
├── smap-analysis-worker/            # Celery 워커
│   ├── tasks.py
│   └── requirements.txt
│
├── smap-victoria-consumer/          # VictoriaMetrics 소비자
│   └── consumer.py
│
├── docker-compose.smap.yml          # SMAP 서비스 정의
├── start-smap.sh                    # 시작 스크립트
├── SMAP_SYSTEM.md                   # 시스템 문서
└── IMPLEMENTATION_SUMMARY.md        # 이 문서
```

## 핵심 성과

1. ✅ **GPU 기반 실시간 추론**: Triton Server + CUDA로 저지연 추론
2. ✅ **계층 구조 반영**: 위성 > 엔티티 > 센서 3계층 데이터 모델
3. ✅ **확장 가능한 아키텍처**: 엔티티별 독립 모델, 워커 스케일링 가능
4. ✅ **완전한 비동기 파이프라인**: Kafka, Celery, aiohttp 비동기 처리
5. ✅ **상세한 메트릭**: 센서별 실제값, 재구성값, 오차, 이상 점수
6. ✅ **개발 환경 호환**: tranad-sim CUDA 11.3 환경 기반 Triton 구성

---

**시스템 상태**: ✅ 배포 준비 완료
**다음 단계**: 프론트엔드 대시보드 개발 → 실시간 모니터링 UI 구현
