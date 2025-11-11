# SMAP 시뮬레이터 사용 가이드

## 빠른 시작

### 1. Docker Compose로 시작 (권장)

```bash
# 프로젝트 루트에서 실행
cd /home/hsnam/projects/telemetry_anomaly_det

# SMAP 시뮬레이터만 시작
docker-compose --profile smap up -d smap-simulator

# 로그 확인
docker-compose logs -f smap-simulator

# 중지
docker-compose --profile smap stop smap-simulator
```

### 2. 로컬에서 직접 실행

```bash
cd batch-simulator

# 기본 실행 (5개 위성, 1회 재생, 1초 간격)
bash start_smap_simulator.sh

# 커스텀 설정
NUM_SATELLITES=3 LOOPS=2 DELAY_MS=500 bash start_smap_simulator.sh
```

### 3. Python 스크립트 직접 실행

```bash
cd batch-simulator

# 의존성 설치
pip install confluent-kafka numpy

# 실행
python smap_simulator.py \
  --kafka localhost:9092 \
  --satellites 5 \
  --loops 1 \
  --delay 1000 \
  --data-dir ./data
```

## 설정 옵션

| 옵션 | 환경변수 | 기본값 | 설명 |
|------|----------|--------|------|
| --kafka | KAFKA_SERVERS | kafka:9092 | Kafka 브로커 주소 |
| --satellites | NUM_SATELLITES | 5 | 위성 개수 (1-5) |
| --loops | LOOPS | 1 | 반복 재생 횟수 |
| --delay | DELAY_MS | 1000 | 레코드 간 딜레이(ms) |
| --data-dir | DATA_DIR | ./data | 데이터 디렉토리 |

## 위성별 데이터 정보

각 위성은 7개 서브시스템의 실측 데이터를 전송합니다:

| 위성 | 최소 레코드 수 | 예상 시간 (1초 간격) |
|------|----------------|----------------------|
| sat1 | 7,331 | 약 2시간 |
| sat2 | 7,331 | 약 2시간 |
| sat3 | 7,331 | 약 2시간 |
| sat4 | 7,331 | 약 2시간 |
| sat5 | 4,693 | 약 1.3시간 |

## 서브시스템 목록

| 코드 | 이름 | 설명 | 특징 수 |
|------|------|------|---------|
| E | EPS | Electric Power System (전력계) | 25 |
| A | ACS | Attitude Control System (자세제어계) | 25 |
| F | FSW | Flight Software (비행소프트웨어) | 25 |
| T | TCS | Thermal Control System (열제어계) | 25 |
| D | Data | Data Handling (원격측정명령계) | 25 |
| S | SS | Structure System (구조계) | 25 |
| P | PS | Propulsion System (추진계) | 25 |

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
      "features": [0.1, 0.2, ..., 0.25],
      "num_features": 25
    },
    "ACS": {
      "code": "A",
      "features": [0.1, 0.2, ..., 0.25],
      "num_features": 25
    },
    ...
  }
}
```

## 사용 예시

### 예시 1: 단일 위성, 빠른 테스트

```bash
# 1개 위성, 1회 재생, 100ms 간격 (빠른 테스트)
NUM_SATELLITES=1 LOOPS=1 DELAY_MS=100 bash start_smap_simulator.sh
```

### 예시 2: 3개 위성, 여러 번 재생

```bash
# 3개 위성, 5회 재생, 1초 간격
NUM_SATELLITES=3 LOOPS=5 DELAY_MS=1000 bash start_smap_simulator.sh
```

### 예시 3: 전체 위성, 실시간 속도

```bash
# 5개 위성, 무한 재생, 1초 간격
python smap_simulator.py \
  --kafka kafka:9092 \
  --satellites 5 \
  --loops 999999 \
  --delay 1000
```

### 예시 4: Docker Compose로 백그라운드 실행

```bash
# SMAP 프로필로 시작
docker-compose --profile smap up -d smap-simulator

# 로그 실시간 모니터링
docker-compose logs -f smap-simulator

# Kafka 메시지 확인
docker-compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic satellite-telemetry \
  --from-beginning \
  --max-messages 10
```

## 테스트

### 데이터 로드 테스트

```bash
cd batch-simulator
python test_all_satellites.py
```

### 메시지 생성 테스트

```bash
cd batch-simulator
python test_simulator.py
```

### 데이터 shape 확인

```bash
cd batch-simulator
python test_data_shape.py
```

## 문제 해결

### Kafka 연결 실패

```bash
# Kafka 상태 확인
docker-compose ps kafka

# Kafka 로그 확인
docker-compose logs kafka

# Kafka 재시작
docker-compose restart kafka
```

### 데이터 파일 없음

```bash
# 데이터 디렉토리 확인
ls -la batch-simulator/data/sat*/

# 누락된 파일이 있으면 fallback 로직이 작동합니다
# 예: sat4에 F-4가 없으면 F-1 사용
```

### 메모리 부족

```bash
# 위성 수 줄이기
NUM_SATELLITES=2 bash start_smap_simulator.sh

# 또는 딜레이 증가
DELAY_MS=2000 bash start_smap_simulator.sh
```

## 모니터링

### Kafka UI에서 메시지 확인

1. 브라우저에서 http://localhost:8080 접속
2. Topics > satellite-telemetry 선택
3. Messages 탭에서 실시간 메시지 확인

### 로그 확인

```bash
# 시뮬레이터 로그
docker-compose logs -f smap-simulator

# Kafka 로그
docker-compose logs -f kafka

# Victoria Consumer 로그 (메시지 수신 확인)
docker-compose logs -f victoria-consumer
```

## 성능 참고

| 설정 | 레코드/초 | 예상 처리 시간 (7,331 레코드) |
|------|-----------|-------------------------------|
| delay=100ms | 10 | 약 12분 |
| delay=500ms | 2 | 약 1시간 |
| delay=1000ms (기본) | 1 | 약 2시간 |
| delay=2000ms | 0.5 | 약 4시간 |

5개 위성이 동시 전송 시 초당 약 5개 메시지 (1초 간격 기준)
