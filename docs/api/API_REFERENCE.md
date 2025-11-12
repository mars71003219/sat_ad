# API 문서

## 목차
1. [개요](#1-개요)
2. [인증](#2-인증)
3. [엔드포인트](#3-엔드포인트)
4. [데이터 모델](#4-데이터-모델)
5. [에러 처리](#5-에러-처리)
6. [사용 예시](#6-사용-예시)

---

## 1. 개요

### 1.1 Base URL

```
http://localhost/api
```

또는 직접 접근:
```
http://localhost:8003
```

### 1.2 API 버전

**현재 버전**: v1.0.0

### 1.3 응답 형식

모든 API는 JSON 형식으로 응답합니다.

**성공 응답**:
```json
{
  "data": {...},
  "status": "success"
}
```

**에러 응답**:
```json
{
  "detail": "Error message",
  "status_code": 400
}
```

---

## 2. 인증

현재 버전에서는 인증이 구현되어 있지 않습니다. (프로덕션 환경에서는 JWT 또는 OAuth2 구현 권장)

---

## 3. 엔드포인트

### 3.1 Health Check

#### GET `/health`

서버 상태 확인

**Request**:
```bash
curl http://localhost:8003/health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "operation-server",
  "version": "1.0.0"
}
```

---

### 3.2 Dashboard API

#### GET `/api/dashboard/stats`

대시보드 통계 조회

**Request**:
```bash
curl http://localhost/api/dashboard/stats
```

**Response**:
```json
{
  "inference_stats": {
    "total_inferences": 15420,
    "anomalies_detected": 234,
    "avg_inference_time_ms": 75.3
  },
  "total_satellites": 5,
  "active_satellites": 5,
  "satellites": [
    {
      "satellite_id": "sat1",
      "name": "SMAP-1",
      "monitoring_enabled": true
    },
    ...
  ]
}
```

#### GET `/api/dashboard/features`

서브시스템의 특징 목록 조회

**Parameters**:
| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| subsystem | string | Y | 서브시스템 코드 (ACS, Data, EPS, FSW, PS, SS, TCS) |

**Request**:
```bash
curl "http://localhost/api/dashboard/features?subsystem=EPS"
```

**Response**:
```json
{
  "subsystem": "EPS",
  "features": [
    "feature_0",
    "feature_1",
    ...
    "feature_24"
  ]
}
```

---

### 3.3 Configuration API

#### GET `/api/config/satellites`

전체 위성 설정 조회

**Request**:
```bash
curl http://localhost/api/config/satellites
```

**Response**:
```json
[
  {
    "satellite_id": "sat1",
    "name": "SMAP-1",
    "monitoring_enabled": true,
    "subsystems": ["ACS", "Data", "EPS", "FSW", "PS", "SS", "TCS"]
  },
  ...
]
```

#### GET `/api/config/satellites/{satellite_id}`

특정 위성 설정 조회

**Parameters**:
| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| satellite_id | string | Y | 위성 ID (sat1, sat2, ...) |

**Request**:
```bash
curl http://localhost/api/config/satellites/sat1
```

**Response**:
```json
{
  "satellite_id": "sat1",
  "name": "SMAP-1",
  "monitoring_enabled": true,
  "subsystems": ["ACS", "Data", "EPS", "FSW", "PS", "SS", "TCS"],
  "models": {
    "ACS": "SMAP_A-1",
    "Data": "SMAP_D-1",
    "EPS": "SMAP_E-1",
    ...
  }
}
```

#### PUT `/api/config/satellites/{satellite_id}`

위성 설정 업데이트

**Parameters**:
| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| satellite_id | string | Y | 위성 ID |

**Request Body**:
```json
{
  "monitoring_enabled": false
}
```

**Request**:
```bash
curl -X PUT http://localhost/api/config/satellites/sat1 \
  -H "Content-Type: application/json" \
  -d '{"monitoring_enabled": false}'
```

**Response**:
```json
{
  "satellite_id": "sat1",
  "monitoring_enabled": false,
  "updated_at": "2025-11-12T10:00:00Z"
}
```

#### GET `/api/config/models`

전체 모델 설정 조회

**Request**:
```bash
curl http://localhost/api/config/models
```

**Response**:
```json
[
  {
    "model_name": "SMAP_A-1",
    "subsystem": "ACS",
    "version": "1.0",
    "window_size": 30,
    "threshold": 4.0
  },
  ...
]
```

---

### 3.4 Metrics Query API

#### POST `/api/metrics/query`

VictoriaMetrics PromQL 쿼리 실행

**Request Body**:
```json
{
  "query": "smap_feature{satellite_id=\"sat1\"}",
  "start": 1762922000,
  "end": 1762923000,
  "step": "30s"
}
```

**Request**:
```bash
curl -X POST http://localhost/api/metrics/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "smap_feature{satellite_id=\"sat1\",subsystem=\"EPS\"}",
    "start": 1762922000,
    "end": 1762923000,
    "step": "30s"
  }'
```

**Response**:
```json
{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {
          "__name__": "smap_feature",
          "satellite_id": "sat1",
          "subsystem": "EPS",
          "feature_index": "0"
        },
        "values": [
          [1762922000, "0.5"],
          [1762922030, "0.6"],
          ...
        ]
      },
      ...
    ]
  }
}
```

#### GET `/api/metrics/telemetry`

텔레메트리 데이터 조회 (간편 쿼리)

**Parameters**:
| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| satellite_id | string | Y | 위성 ID |
| subsystem | string | N | 서브시스템 (미지정 시 전체) |
| feature_index | string | N | 특징 인덱스 (미지정 시 전체) |
| duration | string | N | 기간 (기본값: 5m) |

**Request**:
```bash
curl "http://localhost/api/metrics/telemetry?satellite_id=sat1&subsystem=EPS&duration=10m"
```

**Response**:
```json
{
  "satellite_id": "sat1",
  "subsystem": "EPS",
  "time_range": {
    "start": "2025-11-12T09:50:00Z",
    "end": "2025-11-12T10:00:00Z"
  },
  "data": [
    {
      "feature_index": "0",
      "values": [
        {"timestamp": 1762922000, "value": 0.5},
        {"timestamp": 1762922030, "value": 0.6},
        ...
      ]
    },
    ...
  ]
}
```

#### GET `/api/metrics/inference`

추론 결과 조회

**Parameters**:
| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| satellite_id | string | N | 위성 ID |
| subsystem | string | N | 서브시스템 |
| anomaly_only | boolean | N | 이상만 조회 (기본값: false) |
| limit | int | N | 결과 개수 (기본값: 100) |

**Request**:
```bash
curl "http://localhost/api/metrics/inference?satellite_id=sat1&anomaly_only=true&limit=10"
```

**Response**:
```json
{
  "total": 10,
  "anomalies": [
    {
      "satellite_id": "sat1",
      "subsystem": "ACS",
      "model_name": "SMAP_A-1",
      "mean_anomaly_score": 4.5,
      "max_anomaly_score": 5.2,
      "is_anomaly": true,
      "timestamp": "2025-11-12T10:00:00Z"
    },
    ...
  ]
}
```

---

### 3.5 WebSocket API

#### WS `/api/ws/{client_id}`

실시간 데이터 스트리밍

**Parameters**:
| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| client_id | string | Y | 클라이언트 ID (UUID 권장) |

**Connection**:
```javascript
const ws = new WebSocket('ws://localhost/api/ws/client-123');

ws.onopen = () => {
  console.log('Connected');

  // 구독 요청
  ws.send(JSON.stringify({
    action: 'subscribe',
    satellite_id: 'sat1',
    subsystem: 'EPS'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};
```

**Subscribe Message**:
```json
{
  "action": "subscribe",
  "satellite_id": "sat1",
  "subsystem": "EPS"
}
```

**Unsubscribe Message**:
```json
{
  "action": "unsubscribe",
  "satellite_id": "sat1",
  "subsystem": "EPS"
}
```

**Server Message (Telemetry)**:
```json
{
  "type": "telemetry",
  "satellite_id": "sat1",
  "subsystem": "EPS",
  "timestamp": "2025-11-12T10:00:00Z",
  "features": [0.5, 0.3, 0.8, ...],
  "feature_index": 0,
  "value": 0.5
}
```

**Server Message (Inference)**:
```json
{
  "type": "inference",
  "satellite_id": "sat1",
  "subsystem": "ACS",
  "model_name": "SMAP_A-1",
  "is_anomaly": true,
  "anomaly_score": 4.5,
  "timestamp": "2025-11-12T10:00:00Z"
}
```

---

## 4. 데이터 모델

### 4.1 Satellite

```json
{
  "satellite_id": "string",
  "name": "string",
  "monitoring_enabled": "boolean",
  "subsystems": ["string"],
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 4.2 TelemetryData

```json
{
  "satellite_id": "string",
  "subsystem": "string",
  "feature_index": "string",
  "value": "float",
  "timestamp": "datetime"
}
```

### 4.3 InferenceResult

```json
{
  "satellite_id": "string",
  "subsystem": "string",
  "model_name": "string",
  "window_size": "integer",
  "window_start_time": "datetime",
  "window_end_time": "datetime",
  "mean_anomaly_score": "float",
  "max_anomaly_score": "float",
  "is_anomaly": "boolean",
  "anomaly_scores": ["float"],
  "reconstructions": [[float]],
  "inference_time_ms": "float",
  "timestamp": "datetime"
}
```

### 4.4 ModelConfig

```json
{
  "model_name": "string",
  "subsystem": "string",
  "version": "string",
  "window_size": "integer",
  "threshold": "float",
  "enabled": "boolean"
}
```

---

## 5. 에러 처리

### 5.1 HTTP 상태 코드

| 코드 | 설명 |
|------|------|
| 200 | 성공 |
| 400 | 잘못된 요청 (파라미터 오류) |
| 404 | 리소스를 찾을 수 없음 |
| 422 | 유효성 검증 실패 |
| 500 | 서버 내부 오류 |

### 5.2 에러 응답 형식

```json
{
  "detail": "Error message",
  "status_code": 400,
  "error_type": "ValidationError",
  "path": "/api/config/satellites/invalid"
}
```

### 5.3 일반적인 에러

#### 400 Bad Request
```json
{
  "detail": "Invalid subsystem: INVALID",
  "valid_subsystems": ["ACS", "Data", "EPS", "FSW", "PS", "SS", "TCS"]
}
```

#### 404 Not Found
```json
{
  "detail": "Satellite sat99 not found"
}
```

#### 422 Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "monitoring_enabled"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## 6. 사용 예시

### 6.1 대시보드 데이터 가져오기

```bash
# 통계 조회
curl http://localhost/api/dashboard/stats | jq

# 특정 위성 텔레메트리
curl "http://localhost/api/metrics/telemetry?satellite_id=sat1&subsystem=EPS&duration=5m" | jq
```

### 6.2 이상탐지 결과 조회

```bash
# 전체 이상탐지 결과
curl "http://localhost/api/metrics/inference?anomaly_only=true" | jq

# 특정 위성의 이상
curl "http://localhost/api/metrics/inference?satellite_id=sat1&anomaly_only=true" | jq '.anomalies[] | {subsystem, score: .mean_anomaly_score}'
```

### 6.3 VictoriaMetrics 직접 쿼리

```bash
# 평균 이상점수 상위 5개
curl -X POST http://localhost/api/metrics/query \
  -H "Content-Type: application/json" \
  -d '{"query": "topk(5, inference_anomaly_score_mean)"}' | jq

# 특정 위성의 EPS 특징
curl -X POST http://localhost/api/metrics/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "smap_feature{satellite_id=\"sat1\", subsystem=\"EPS\"}",
    "start": '$(date -d '10 minutes ago' +%s)',
    "end": '$(date +%s)',
    "step": "30s"
  }' | jq
```

### 6.4 설정 변경

```bash
# 위성 모니터링 비활성화
curl -X PUT http://localhost/api/config/satellites/sat1 \
  -H "Content-Type: application/json" \
  -d '{"monitoring_enabled": false}'

# 모델 임계값 변경
curl -X PUT http://localhost/api/config/models/SMAP_A-1 \
  -H "Content-Type: application/json" \
  -d '{"threshold": 5.0}'
```

### 6.5 Python 클라이언트 예시

```python
import requests
import json

BASE_URL = "http://localhost/api"

# 대시보드 통계
response = requests.get(f"{BASE_URL}/dashboard/stats")
stats = response.json()
print(f"Total satellites: {stats['total_satellites']}")
print(f"Active satellites: {stats['active_satellites']}")

# 텔레메트리 데이터
params = {
    "satellite_id": "sat1",
    "subsystem": "EPS",
    "duration": "5m"
}
response = requests.get(f"{BASE_URL}/metrics/telemetry", params=params)
telemetry = response.json()

# 이상탐지 결과
params = {
    "satellite_id": "sat1",
    "anomaly_only": True,
    "limit": 10
}
response = requests.get(f"{BASE_URL}/metrics/inference", params=params)
anomalies = response.json()
for anomaly in anomalies['anomalies']:
    print(f"{anomaly['subsystem']}: {anomaly['mean_anomaly_score']}")

# PromQL 쿼리
query_data = {
    "query": "smap_feature{satellite_id=\"sat1\"}",
    "start": 1762922000,
    "end": 1762923000,
    "step": "30s"
}
response = requests.post(f"{BASE_URL}/metrics/query", json=query_data)
result = response.json()
```

### 6.6 JavaScript 클라이언트 예시

```javascript
// Fetch API
const BASE_URL = 'http://localhost/api';

// 대시보드 통계
async function getDashboardStats() {
  const response = await fetch(`${BASE_URL}/dashboard/stats`);
  const data = await response.json();
  return data;
}

// WebSocket 실시간 데이터
const ws = new WebSocket('ws://localhost/api/ws/client-123');

ws.onopen = () => {
  // EPS 서브시스템 구독
  ws.send(JSON.stringify({
    action: 'subscribe',
    satellite_id: 'sat1',
    subsystem: 'EPS'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'telemetry') {
    updateTelemetryChart(data);
  } else if (data.type === 'inference') {
    if (data.is_anomaly) {
      showAnomalyAlert(data);
    }
  }
};

// 이상탐지 조회
async function getAnomalies(satelliteId) {
  const params = new URLSearchParams({
    satellite_id: satelliteId,
    anomaly_only: 'true',
    limit: '10'
  });

  const response = await fetch(`${BASE_URL}/metrics/inference?${params}`);
  const data = await response.json();
  return data.anomalies;
}
```

---

## 부록

### A. PromQL 쿼리 예시

```promql
# 전체 텔레메트리
smap_feature

# 특정 위성의 EPS
smap_feature{satellite_id="sat1", subsystem="EPS"}

# 이상탐지 (이상점수 > 4)
inference_anomaly_score_mean > 4

# 평균 추론 시간
avg(inference_time_ms)

# 서브시스템별 이상 개수
count(inference_anomaly_detected{is_anomaly="1"}) by (subsystem)

# 특정 특징의 시계열
smap_feature{feature_index="0"}

# 정규표현식 매칭
smap_feature{subsystem=~"EPS|ACS"}
```

### B. Rate Limit

현재 구현되어 있지 않습니다. 프로덕션 환경에서는 API Gateway 또는 Nginx rate limiting 적용 권장.

### C. 캐싱

- Dashboard stats: 10초 캐시
- Telemetry data: 캐시 없음 (실시간)
- Inference results: 5초 캐시

### D. Swagger UI

API 문서는 Swagger UI로도 확인 가능합니다:
```
http://localhost:8003/docs
```
