# 시스템 설계서

## 목차
1. [시스템 개요](#1-시스템-개요)
2. [전체 아키텍처](#2-전체-아키텍처)
3. [기술 스택](#3-기술-스택)
4. [세부 컴포넌트](#4-세부-컴포넌트)
5. [데이터 모델](#5-데이터-모델)
6. [시퀀스 다이어그램](#6-시퀀스-다이어그램)

---

## 1. 시스템 개요

### 1.1 프로젝트 목표

NASA SMAP (Soil Moisture Active Passive) 위성 텔레메트리 데이터를 기반으로 실시간 이상탐지를 수행하는 분산 처리 시스템 구축.

### 1.2 핵심 요구사항

- **실시간 처리**: 1초 간격 텔레메트리 데이터 실시간 수집 및 처리
- **분산 추론**: 슬라이딩 윈도우 기반 병렬 이상탐지 추론
- **확장성**: 위성 수, 서브시스템 수 확장 가능한 아키텍처
- **모니터링**: 전체 파이프라인 상태 및 이상탐지 결과 시각화

### 1.3 시스템 규모

- **위성 수**: 5개 (확장 가능)
- **서브시스템**: 7개 (ACS, Data, EPS, FSW, PS, SS, TCS)
- **특징 수**: 서브시스템당 25개
- **데이터 속도**: 5 records/sec (위성당 1 record/sec)
- **추론 윈도우**: 30 records (30초)
- **추론 주기**: 10 records stride (10초)

---

## 2. 전체 아키텍처

### 2.1 시스템 구성도

```mermaid
graph TB
    subgraph "Data Source Layer"
        SIM[Satellite Simulator<br/>SMAP Data Replay]
    end

    subgraph "Message Queue Layer"
        KAFKA[Kafka<br/>Event Streaming]
        RABBIT[RabbitMQ<br/>Task Queue]
    end

    subgraph "Processing Layer"
        ROUTER[Telemetry Router<br/>Topic Demux]
        SCHEDULER[Inference Scheduler<br/>Sliding Window]
        WORKER[Inference Worker<br/>Celery + Triton Client]
        TRITON[Triton Server<br/>ONNX Runtime GPU]
    end

    subgraph "Storage Layer"
        WRITER[Metrics Writer<br/>Kafka Consumer]
        VM[VictoriaMetrics<br/>Time Series DB]
        PG[PostgreSQL<br/>Config DB]
    end

    subgraph "API/UI Layer"
        API[Operation Server<br/>FastAPI]
        FE[Frontend<br/>React Dashboard]
        NGINX[Nginx<br/>Reverse Proxy]
    end

    SIM -->|telemetry-raw| KAFKA
    KAFKA --> ROUTER
    ROUTER -->|subsystem topics| KAFKA
    KAFKA --> SCHEDULER
    SCHEDULER -->|inference tasks| RABBIT
    RABBIT --> WORKER
    WORKER --> TRITON
    WORKER -->|inference-results| KAFKA
    KAFKA --> WRITER
    WRITER --> VM
    API --> VM
    API --> PG
    FE --> NGINX
    API --> NGINX
    NGINX -->|:80| Users((Users))

    style SIM fill:#e1f5ff
    style KAFKA fill:#ffe1e1
    style RABBIT fill:#ffe1e1
    style TRITON fill:#e1ffe1
    style VM fill:#fff4e1
    style NGINX fill:#f0e1ff
```

### 2.2 계층별 역할

| 계층 | 역할 | 기술 |
|------|------|------|
| **Data Source** | 위성 텔레메트리 데이터 생성 | Python, Kafka Producer |
| **Message Queue** | 이벤트 스트리밍 및 작업 큐 | Kafka, RabbitMQ |
| **Processing** | 데이터 라우팅, 추론 스케줄링, AI 추론 | Python async, Celery, Triton |
| **Storage** | 시계열 데이터 저장 및 쿼리 | VictoriaMetrics, PostgreSQL |
| **API/UI** | REST API 및 사용자 인터페이스 | FastAPI, React, Nginx |

---

## 3. 기술 스택

### 3.1 핵심 기술

```mermaid
graph LR
    subgraph "Backend"
        Python[Python 3.10]
        FastAPI[FastAPI]
        Celery[Celery]
    end

    subgraph "Message/Queue"
        Kafka[Apache Kafka<br/>KRaft Mode]
        RabbitMQ[RabbitMQ]
    end

    subgraph "AI/ML"
        Triton[Triton Inference Server]
        ONNX[ONNX Runtime]
        TranAD[TranAD Model]
    end

    subgraph "Storage"
        VM[VictoriaMetrics]
        PG[PostgreSQL 15]
    end

    subgraph "Frontend"
        React[React 18]
        Nginx[Nginx]
    end

    Python --> FastAPI
    Python --> Celery
    Celery --> RabbitMQ
    Python --> Kafka
    Celery --> Triton
    Triton --> ONNX
    ONNX --> TranAD
    Python --> VM
    Python --> PG
    React --> Nginx
```

### 3.2 기술 선정 이유

#### Apache Kafka (이벤트 스트리밍)
- **선정 이유**:
  - 높은 처리량 (millions messages/sec)
  - 토픽 기반 pub/sub 패턴
  - 데이터 복제 및 내구성
- **사용 사례**:
  - 텔레메트리 데이터 스트리밍
  - 서브시스템별 토픽 라우팅
  - 추론 결과 배포

#### RabbitMQ (작업 큐)
- **선정 이유**:
  - Celery와 완벽한 통합
  - 작업 우선순위 및 재시도 지원
  - 낮은 지연시간
- **사용 사례**:
  - 추론 작업 분산 처리
  - Worker 로드 밸런싱

#### Triton Inference Server (추론 서버)
- **선정 이유**:
  - ONNX 런타임 지원
  - GPU 가속
  - 동적 배치 처리
  - HTTP/gRPC API
- **사용 사례**:
  - 27개 SMAP 모델 서빙
  - 배치 추론 최적화

#### VictoriaMetrics (시계열 DB)
- **선정 이유**:
  - Prometheus 호환 (PromQL)
  - 낮은 메모리 사용량
  - 빠른 쿼리 성능
  - 수평 확장 가능
- **사용 사례**:
  - 텔레메트리 데이터 저장 (875개 시계열)
  - 추론 결과 저장
  - 대시보드 쿼리

#### PostgreSQL (관계형 DB)
- **선정 이유**:
  - ACID 트랜잭션
  - JSON 지원
  - 안정성 및 성숙도
- **사용 사례**:
  - 시스템 설정 저장
  - 모델 메타데이터 관리

---

## 4. 세부 컴포넌트

### 4.1 데이터 소스 계층

#### Satellite Simulator

```mermaid
classDiagram
    class SatelliteSimulator {
        +str kafka_servers
        +int num_satellites
        +int loops
        +int delay_ms
        +load_smap_data()
        +produce_telemetry()
        +replay_loop()
    }

    class SMAPData {
        +str satellite_id
        +datetime timestamp
        +dict subsystems
        +int loop
        +int record_index
    }

    class Subsystem {
        +str code
        +list features
        +int num_features
    }

    SatelliteSimulator --> SMAPData
    SMAPData --> Subsystem
```

**역할**:
- NASA SMAP 데이터셋 로드 및 재생
- Kafka `satellite-telemetry-raw` 토픽으로 전송
- 5개 위성 데이터 동시 전송

**데이터 구조**:
```json
{
  "satellite_id": "sat1",
  "timestamp": "2025-11-12T10:00:00+00:00",
  "loop": 1,
  "record_index": 1080,
  "subsystems": {
    "ACS": {
      "code": "A",
      "features": [10.0, 0.5, ...],
      "num_features": 25
    },
    "EPS": {...},
    ...
  }
}
```

### 4.2 메시지 큐 계층

#### Kafka Topics

```mermaid
graph TD
    subgraph "Input Topics"
        RAW[satellite-telemetry-raw<br/>Partitions: 5]
    end

    subgraph "Subsystem Topics"
        T_ACS[telemetry.ACS.*<br/>35 topics]
        T_DATA[telemetry.Data.*]
        T_EPS[telemetry.EPS.*]
        T_FSW[telemetry.FSW.*]
        T_PS[telemetry.PS.*]
        T_SS[telemetry.SS.*]
        T_TCS[telemetry.TCS.*]
    end

    subgraph "Output Topics"
        RESULT[inference-results]
    end

    RAW --> T_ACS
    RAW --> T_DATA
    RAW --> T_EPS
    RAW --> T_FSW
    RAW --> T_PS
    RAW --> T_SS
    RAW --> T_TCS
```

**토픽 명명 규칙**:
- Raw: `satellite-telemetry-raw`
- Subsystem: `telemetry.{subsystem}.{satellite_id}`
- Results: `inference-results`

### 4.3 처리 계층

#### Telemetry Router

```mermaid
sequenceDiagram
    participant Kafka
    participant Router
    participant SubTopics as Subsystem Topics

    Kafka->>Router: Poll raw topic
    Note over Router: Extract subsystems
    loop For each subsystem
        Router->>Router: Create subsystem message
        Router->>SubTopics: Publish to topic
        Note over SubTopics: telemetry.{sub}.{sat}
    end
```

**기능**:
- Raw 토픽 소비
- 서브시스템별로 메시지 분리
- 7개 서브시스템 × 5개 위성 = 35개 토픽 생성

#### Inference Scheduler

```mermaid
classDiagram
    class InferenceScheduler {
        +int window_size
        +int stride
        +dict buffers
        +consume_subsystem_topic()
        +buffer_telemetry()
        +create_sliding_windows()
        +dispatch_inference_task()
    }

    class WindowBuffer {
        +str satellite_id
        +str subsystem
        +list records
        +bool is_ready()
        +list get_windows()
    }

    class InferenceTask {
        +str job_id
        +str satellite_id
        +str subsystem
        +str model_name
        +ndarray input_data
        +datetime window_start
        +datetime window_end
    }

    InferenceScheduler --> WindowBuffer
    InferenceScheduler --> InferenceTask
```

**슬라이딩 윈도우 로직**:
```
Window Size: 30 records
Stride: 10 records

Records: [0, 1, 2, ..., 99]

Window 1: [0..29]   -> inference
Window 2: [10..39]  -> inference
Window 3: [20..49]  -> inference
...
Window N: [70..99]  -> inference
```

#### Inference Worker

```mermaid
sequenceDiagram
    participant RabbitMQ
    participant Worker
    participant TritonClient
    participant TritonServer

    RabbitMQ->>Worker: Dequeue task
    Worker->>Worker: Preprocess input
    Worker->>TritonClient: Create InferRequest
    TritonClient->>TritonServer: HTTP POST /v2/models/{model}/infer
    TritonServer->>TritonServer: ONNX inference (GPU)
    TritonServer->>TritonClient: InferResponse
    TritonClient->>Worker: Parse output
    Worker->>Worker: Calculate anomaly score
    Worker->>Kafka: Publish result
```

**Celery 설정**:
```python
app = Celery('tasks',
             broker='amqp://rabbitmq:5672',
             backend='rpc://')

@app.task(name='run_inference_task')
def run_inference_task(job_data):
    # Triton 추론 실행
    # 이상점수 계산
    # 결과 Kafka 전송
```

#### Triton Server

```mermaid
graph TB
    subgraph "Triton Server"
        HTTP[HTTP Endpoint<br/>:8000]
        gRPC[gRPC Endpoint<br/>:8001]
        Metrics[Metrics<br/>:8002]

        subgraph "Model Repository"
            M1[SMAP_A-1]
            M2[SMAP_A-2]
            M3[SMAP_E-1]
            MN[... 27 models]
        end

        subgraph "Backend"
            ONNX[ONNX Runtime<br/>GPU Accelerated]
        end
    end

    HTTP --> M1
    HTTP --> M2
    HTTP --> M3
    HTTP --> MN
    M1 --> ONNX
    M2 --> ONNX
    M3 --> ONNX
    MN --> ONNX
```

**모델 구조**:
```
triton-repository/onnx/
├── SMAP_A-1/
│   ├── config.pbtxt
│   └── 1/
│       └── model.onnx
├── SMAP_A-2/
...
├── SMAP_T-5/
```

### 4.4 저장 계층

#### Metrics Writer

```mermaid
classDiagram
    class MetricsWriter {
        +aiohttp.ClientSession session
        +consume_messages()
        +process_telemetry_data()
        +process_inference_result()
        +write_to_victoria_metrics()
    }

    class TelemetryProcessor {
        +extract_subsystem_features()
        +format_prometheus_metric()
    }

    class InferenceProcessor {
        +extract_anomaly_scores()
        +extract_reconstructions()
        +format_prometheus_metric()
    }

    MetricsWriter --> TelemetryProcessor
    MetricsWriter --> InferenceProcessor
```

**메트릭 변환**:
```
Kafka Message → Prometheus Format → VictoriaMetrics

Example:
{
  "satellite_id": "sat1",
  "subsystems": {
    "EPS": {"features": [0.5, 0.3, ...]}
  }
}

→

smap_feature{satellite_id="sat1",subsystem="EPS",feature_index="0"} 0.5 1762922535240
smap_feature{satellite_id="sat1",subsystem="EPS",feature_index="1"} 0.3 1762922535240
```

#### VictoriaMetrics Schema

```mermaid
erDiagram
    SMAP_FEATURE ||--o{ TIME_SERIES : has
    INFERENCE_RESULT ||--o{ TIME_SERIES : has

    SMAP_FEATURE {
        string __name__ "smap_feature"
        string satellite_id "sat1..sat5"
        string subsystem "ACS,Data,EPS,..."
        string feature_index "0..24"
        float value "sensor value"
        timestamp time "unix timestamp ms"
    }

    INFERENCE_RESULT {
        string __name__ "inference_*"
        string satellite_id "sat1..sat5"
        string subsystem "ACS,Data,EPS,..."
        string model_name "SMAP_A-1..."
        string job_id "uuid"
        string timestep "0..29"
        string feature_index "0..24"
        float value "score/reconstruction"
        timestamp time "unix timestamp ms"
    }
```

---

## 5. 데이터 모델

### 5.1 텔레메트리 데이터 모델

```mermaid
classDiagram
    class TelemetryMessage {
        +str satellite_id
        +datetime timestamp
        +int loop
        +int record_index
        +dict subsystems
    }

    class Subsystem {
        +str code
        +list~float~ features
        +int num_features
    }

    class SubsystemType {
        <<enumeration>>
        ACS
        Data
        EPS
        FSW
        PS
        SS
        TCS
    }

    TelemetryMessage "1" --> "7" Subsystem
    Subsystem --> SubsystemType
```

### 5.2 추론 결과 모델

```mermaid
classDiagram
    class InferenceResult {
        +str satellite_id
        +str subsystem
        +str model_name
        +int window_size
        +datetime window_start_time
        +datetime window_end_time
        +float mean_anomaly_score
        +float max_anomaly_score
        +bool is_anomaly
        +list~float~ anomaly_scores
        +list reconstructions
        +float inference_time_ms
        +datetime timestamp
        +str service
        +str status
    }

    class AnomalyScore {
        +int timestep
        +float score
    }

    class Reconstruction {
        +int timestep
        +list~float~ features
    }

    InferenceResult "1" --> "30" AnomalyScore
    InferenceResult "1" --> "30" Reconstruction
```

### 5.3 메트릭 스키마

#### 텔레메트리 메트릭

| 메트릭 이름 | 레이블 | 설명 |
|------------|--------|------|
| `smap_feature` | satellite_id, subsystem, feature_index | 센서 특징값 |
| `loop` | satellite_id | 시뮬레이터 루프 번호 |
| `record_index` | satellite_id | 레코드 인덱스 |

#### 추론 메트릭

| 메트릭 이름 | 레이블 | 설명 |
|------------|--------|------|
| `inference_anomaly_detected` | satellite_id, subsystem, model_name | 이상 탐지 여부 (0/1) |
| `inference_anomaly_score` | satellite_id, subsystem, model_name, timestep | 타임스텝별 이상점수 |
| `inference_anomaly_score_mean` | satellite_id, subsystem, model_name | 평균 이상점수 |
| `inference_anomaly_score_max` | satellite_id, subsystem, model_name | 최대 이상점수 |
| `inference_reconstruction` | satellite_id, subsystem, model_name, timestep, feature_index | 특징별 복원값 |
| `inference_reconstruction_mean` | satellite_id, subsystem, model_name, timestep | 타임스텝별 복원값 평균 |
| `inference_time_ms` | satellite_id, subsystem, model_name | 추론 시간 (ms) |

---

## 6. 시퀀스 다이어그램

### 6.1 전체 데이터 흐름

```mermaid
sequenceDiagram
    participant Sim as Simulator
    participant K as Kafka
    participant R as Router
    participant S as Scheduler
    participant RMQ as RabbitMQ
    participant W as Worker
    participant T as Triton
    participant MW as Metrics Writer
    participant VM as VictoriaMetrics

    Sim->>K: Produce telemetry (raw)
    K->>R: Consume raw topic
    R->>K: Produce subsystem topics (×35)
    K->>S: Consume subsystem topic
    Note over S: Buffer + Sliding Window
    S->>RMQ: Dispatch inference task
    RMQ->>W: Dequeue task
    W->>T: ONNX inference request
    T-->>W: Inference response
    W->>K: Produce inference result
    K->>MW: Consume raw + inference
    MW->>VM: Write metrics (Prometheus format)
```

### 6.2 슬라이딩 윈도우 처리

```mermaid
sequenceDiagram
    participant K as Kafka
    participant S as Scheduler
    participant B as Buffer
    participant RMQ as RabbitMQ

    loop For each message
        K->>S: Telemetry record
        S->>B: Append to buffer

        alt Buffer >= window_size
            B->>S: Get sliding windows
            loop For each window
                S->>S: Create inference task
                S->>RMQ: Dispatch task
            end
            B->>B: Remove old records (stride)
        end
    end
```

### 6.3 추론 실행 흐름

```mermaid
sequenceDiagram
    participant RMQ as RabbitMQ
    participant W as Worker
    participant TC as Triton Client
    participant T as Triton Server
    participant K as Kafka

    RMQ->>W: Inference task
    activate W

    W->>W: Preprocess input
    Note over W: Normalize, reshape to (1, 30, 25)

    W->>TC: Create InferRequest
    TC->>T: POST /v2/models/{model}/infer
    activate T
    T->>T: ONNX forward pass (GPU)
    T-->>TC: InferResponse
    deactivate T

    TC-->>W: Parse outputs
    W->>W: Calculate anomaly scores
    Note over W: MSE(input, reconstruction)

    W->>K: Publish inference result
    deactivate W
```

### 6.4 메트릭 저장 흐름

```mermaid
sequenceDiagram
    participant K as Kafka
    participant MW as Metrics Writer
    participant VM as VictoriaMetrics

    K->>MW: Telemetry message
    activate MW
    MW->>MW: Extract subsystem features
    loop For each feature (25×7)
        MW->>MW: Format Prometheus metric
        Note over MW: smap_feature{labels} value timestamp
    end
    MW->>VM: POST /api/v1/import/prometheus
    deactivate MW

    K->>MW: Inference result
    activate MW
    MW->>MW: Extract anomaly scores
    MW->>MW: Extract reconstructions
    loop For each metric type
        MW->>MW: Format Prometheus metric
    end
    MW->>VM: POST /api/v1/import/prometheus
    deactivate MW
```

---

## 부록

### A. 성능 특성

| 항목 | 측정값 | 비고 |
|------|--------|------|
| 텔레메트리 처리량 | 5 records/sec | 5 위성 동시 전송 |
| 추론 지연시간 | 50-100ms | Triton GPU 추론 |
| 메트릭 쓰기 속도 | 177 metrics/satellite/sec | VictoriaMetrics |
| 쿼리 응답시간 | 2-8ms | 전체 데이터 쿼리 |
| 시계열 수 | 875개 | 5×7×25 |
| 추론 작업 생성 | ~106 tasks/batch | 슬라이딩 윈도우 |

### B. 확장성 고려사항

#### 수평 확장
- Kafka 파티션 수 증가
- Inference Worker 수 증가 (`docker compose up --scale inference-worker=N`)
- VictoriaMetrics 클러스터 구성

#### 수직 확장
- Triton 서버 GPU 메모리 증가
- VictoriaMetrics 메모리 할당 증가
- Kafka 버퍼 크기 조정

### C. 보안 고려사항

#### 현재 구현
- 로컬 네트워크 격리 (docker bridge network)
- RabbitMQ 기본 인증 (guest/guest)
- PostgreSQL 패스워드 인증

#### 프로덕션 권장사항
- Kafka SSL/TLS 암호화
- RabbitMQ 사용자 권한 관리
- PostgreSQL SSL 연결
- Nginx HTTPS 적용
- JWT 기반 API 인증
- 서비스 간 mTLS
