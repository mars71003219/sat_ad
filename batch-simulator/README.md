# SMAP 위성 텔레메트리 시뮬레이터

NASA SMAP 데이터셋 기반 위성 텔레메트리 시뮬레이터입니다. 5개 위성의 7개 서브시스템 실측 데이터를 Kafka로 전송합니다.

## 데이터 구조

각 위성(sat1~sat5)은 7개 서브시스템의 test.npy 파일을 가집니다:

```
data/
├── sat1/
│   ├── A-1_test.npy  # ACS (자세제어계)
│   ├── D-1_test.npy  # Data (원격측정명령계)
│   ├── E-1_test.npy  # EPS (전력계)
│   ├── F-1_test.npy  # FSW (비행소프트웨어)
│   ├── P-1_test.npy  # PS (추진계)
│   ├── S-1_test.npy  # SS (구조계)
│   └── T-1_test.npy  # TCS (열제어계)
├── sat2/...
├── sat3/...
├── sat4/...
└── sat5/...
```

각 파일은 `(레코드 수, 25개 특징)` 형태의 numpy 배열입니다.

## 실행 방법

### 1. Docker Compose 실행 (권장)

```bash
# 프로젝트 루트에서 실행
docker-compose --profile smap up smap-simulator

# 백그라운드 실행
docker-compose --profile smap up -d smap-simulator

# 로그 확인
docker-compose logs -f smap-simulator

# 중지
docker-compose --profile smap stop smap-simulator
```

### 2. 간단 실행 (쉘 스크립트)

```bash
# 기본 실행 (5개 위성, 1회 재생, 1초 간격)
bash start_smap_simulator.sh

# 커스텀 설정
NUM_SATELLITES=3 LOOPS=2 DELAY_MS=500 bash start_smap_simulator.sh

# 도움말
bash start_smap_simulator.sh --help
```

### 3. Python 직접 실행

```bash
# 의존성 설치
pip install confluent-kafka numpy

# 실행
python smap_simulator.py --kafka localhost:9092 --satellites 5 --loops 1 --delay 1000
```

### 4. Docker 컨테이너 실행

```bash
docker run --rm --network telemetry-net \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/smap_simulator.py:/app/smap_simulator.py \
  -w /app \
  python:3.10-slim \
  bash -c "pip install -q confluent-kafka numpy && \
           python smap_simulator.py --kafka kafka:9092 --satellites 5 --loops 1"
```

## 옵션

| 옵션 | 환경변수 | 기본값 | 설명 |
|------|----------|--------|------|
| --kafka | KAFKA_SERVERS | kafka:9092 | Kafka 서버 주소 |
| --satellites | NUM_SATELLITES | 5 | 위성 개수 (1-5) |
| --loops | LOOPS | 1 | 반복 재생 횟수 |
| --delay | DELAY_MS | 1000 | 레코드 간 딜레이(ms) |
| --data-dir | DATA_DIR | ./data | 데이터 디렉토리 |

## Kafka 메시지 포맷

```json
{
  "satellite_id": "sat1",
  "timestamp": "2025-11-11T12:34:56.789Z",
  "loop": 1,
  "record_index": 0,
  "subsystems": {
    "EPS": {
      "code": "E",
      "features": [0.1, 0.2, ...],
      "num_features": 25
    },
    "ACS": {
      "code": "A",
      "features": [0.1, 0.2, ...],
      "num_features": 25
    },
    ...
  }
}
```

## 서브시스템 매핑

| 코드 | 이름 | 설명 |
|------|------|------|
| E | EPS | Electric Power System (전력계) |
| A | ACS | Attitude Control System (자세제어계) |
| F | FSW | Flight Software (비행소프트웨어) |
| T | TCS | Thermal Control System (열제어계) |
| D | Data | Data Handling (원격측정명령계) |
| S | SS | Structure System (구조계) |
| P | PS | Propulsion System (추진계) |

## 데이터 통계

| 위성 | 최소 레코드 수 | 설명 |
|------|----------------|------|
| sat1 | 7,331 | 약 2시간 (1초 간격) |
| sat2 | 7,331 | 약 2시간 |
| sat3 | 7,331 | 약 2시간 |
| sat4 | 7,331 | 약 2시간 |
| sat5 | 4,693 | 약 1.3시간 |

모든 위성은 가장 짧은 서브시스템(S-1: 7,331 레코드)에 맞춰 전송됩니다.
