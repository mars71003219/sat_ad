# Triton Inference Server - 통합 모델 리포지토리

위성 텔레메트리 이상 감지 시스템을 위한 Triton 모델 저장소입니다.
모든 백엔드(ONNX, TensorRT, PyTorch, Python, Ensemble)를 체계적으로 관리합니다.

## 디렉토리 구조

```
triton-repository/
├── onnx/                    # ONNX Runtime 백엔드
│   ├── SMAP_A-1/
│   │   ├── 1/
│   │   │   └── model.onnx
│   │   └── config.pbtxt
│   └── ...                  (27개 모델)
│
├── tensorrt/                # TensorRT 백엔드 (고성능 GPU 추론)
│   ├── SMAP_A-1_trt/
│   │   ├── 1/
│   │   │   └── model.plan
│   │   └── config.pbtxt
│   └── ...
│
├── pytorch/                 # PyTorch/TorchScript 백엔드
│   ├── tranad_sat1/
│   │   ├── 1/
│   │   │   └── model.pt
│   │   └── config.pbtxt
│   └── ...
│
├── python/                  # Python 커스텀 백엔드
│   ├── preprocessing/
│   │   ├── 1/
│   │   │   └── model.py
│   │   └── config.pbtxt
│   ├── postprocessing/
│   └── custom_logic/
│
├── ensemble/                # 앙상블 모델 (여러 백엔드 조합)
│   ├── multi_detector/
│   │   ├── 1/              # 버전 디렉토리 (빈 폴더)
│   │   └── config.pbtxt     # 앙상블 설정
│   └── ...
│
├── configs/                 # 공통 설정 파일
│   ├── common.pbtxt         # 공통 파라미터
│   └── templates/           # 백엔드별 config 템플릿
│
└── scripts/                 # 유틸리티 스크립트
    ├── deploy_onnx.py       # ONNX 모델 배포
    ├── convert_tensorrt.py  # ONNX → TensorRT 변환
    └── validate_models.sh   # 모델 검증
```

## 백엔드별 설명

### 1. ONNX Backend (onnx/)
**현재 사용 중**

- **용도**: 프레임워크 독립적 추론
- **장점**: 이식성, 범용성
- **모델**: OmniAnomaly (27개)
- **입력**: FP32, shape [-1, 25]
- **출력**: reconstruction, anomaly_score, anomaly_detected

**예시 구조:**
```
onnx/SMAP_E-1/
├── 1/
│   └── model.onnx          # ONNX 모델 파일
└── config.pbtxt            # Triton 설정
```

### 2. TensorRT Backend (tensorrt/)
**향후 확장**

- **용도**: NVIDIA GPU 최적화 추론 (ONNX보다 2-5배 빠름)
- **장점**: 최고 성능, FP16/INT8 양자화 지원
- **변환**: ONNX → TensorRT .plan 파일
- **GPU**: RTX 5060 (sm_89)

**생성 방법:**
```bash
python scripts/convert_tensorrt.py \
  --onnx onnx/SMAP_E-1/1/model.onnx \
  --output tensorrt/SMAP_E-1_trt/1/model.plan \
  --fp16  # FP16 정밀도
```

### 3. PyTorch Backend (pytorch/)
**향후 확장**

- **용도**: TorchScript 모델 직접 서빙
- **장점**: PyTorch 네이티브 기능 사용 가능
- **모델 예시**: TranAD 원본 체크포인트 변환

**변환 방법:**
```python
import torch

model = TranAD(feats=25)
model.load_state_dict(torch.load('checkpoint.pt'))
model.eval()

traced = torch.jit.trace(model, example_input)
traced.save('model.pt')
```

### 4. Python Backend (python/)
**향후 확장**

- **용도**: 커스텀 Python 로직 실행
- **사용 사례**:
  - 전처리: 데이터 정규화, 특징 추출
  - 후처리: 임계값 적용, 결과 필터링
  - 비즈니스 로직: DB 조회, 캐싱
  - 외부 API 호출

**예시 (전처리):**
```python
# python/preprocessing/1/model.py
import triton_python_backend_utils as pb_utils
import numpy as np

class TritonPythonModel:
    def execute(self, requests):
        responses = []
        for request in requests:
            # 원본 특징 추출
            raw_data = pb_utils.get_input_tensor_by_name(request, "raw_data")
            data = raw_data.as_numpy()

            # 정규화
            normalized = (data - self.mean) / self.std

            # 다음 모델로 전달
            out_tensor = pb_utils.Tensor("normalized_data", normalized)
            responses.append(pb_utils.InferenceResponse([out_tensor]))
        return responses
```

### 5. Ensemble Backend (ensemble/)
**향후 확장**

- **용도**: 여러 모델을 파이프라인으로 연결
- **특징**: 추론 그래프 정의 (DAG)
- **사용 사례**: 전처리 → 추론 → 후처리 파이프라인

**예시 (다중 모델 앙상블):**
```
ensemble/anomaly_pipeline/
├── 1/                      # 빈 폴더
└── config.pbtxt

config.pbtxt 내용:
platform: "ensemble"
ensemble_scheduling {
  step [
    {
      model_name: "preprocessing"
      model_version: 1
      input_map { key: "raw_input" value: "raw_input" }
      output_map { key: "normalized" value: "preprocessed_data" }
    },
    {
      model_name: "SMAP_E-1"
      model_version: 1
      input_map { key: "input_data" value: "preprocessed_data" }
      output_map { key: "anomaly_score" value: "onnx_score" }
    },
    {
      model_name: "tranad_sat1"
      model_version: 1
      input_map { key: "input_data" value: "preprocessed_data" }
      output_map { key: "anomaly_score" value: "pytorch_score" }
    },
    {
      model_name: "postprocessing"
      model_version: 1
      input_map { key: "score1" value: "onnx_score" }
      input_map { key: "score2" value: "pytorch_score" }
      output_map { key: "final_result" value: "final_result" }
    }
  ]
}
```

## 모델 배포 가이드

### ONNX 모델 추가

```bash
# 1. 모델 디렉토리 생성
mkdir -p triton-repository/onnx/NEW_MODEL/1

# 2. ONNX 파일 복사
cp model.onnx triton-repository/onnx/NEW_MODEL/1/

# 3. config.pbtxt 생성
cat > triton-repository/onnx/NEW_MODEL/config.pbtxt << EOF
name: "NEW_MODEL"
backend: "onnxruntime"
max_batch_size: 0

input [
  {
    name: "input_data"
    data_type: TYPE_FP32
    dims: [ -1, 25 ]
  }
]

output [
  {
    name: "output"
    data_type: TYPE_FP32
    dims: [ -1, 25 ]
  }
]

instance_group [
  {
    count: 1
    kind: KIND_GPU
    gpus: [ 0 ]
  }
]
EOF

# 4. Triton 재시작 (자동 로드)
docker compose restart triton-server
```

### TensorRT 변환 및 배포

```bash
# 1. ONNX → TensorRT 변환
python scripts/convert_tensorrt.py \
  --onnx onnx/SMAP_E-1/1/model.onnx \
  --output tensorrt/SMAP_E-1_trt/1/model.plan \
  --fp16 \
  --workspace 4096

# 2. config.pbtxt 생성 (backend: "tensorrt")
# 3. Triton 재시작
```

### PyTorch 모델 배포

```bash
# 1. TorchScript 변환
python scripts/convert_torchscript.py \
  --checkpoint tranad/checkpoints/sat1.ckpt \
  --output pytorch/tranad_sat1/1/model.pt

# 2. config.pbtxt 생성 (backend: "pytorch")
# 3. Triton 재시작
```

## 모델 버전 관리

Triton은 각 모델의 여러 버전을 동시에 서빙할 수 있습니다:

```
onnx/SMAP_E-1/
├── 1/
│   └── model.onnx          # 버전 1 (구버전)
├── 2/
│   └── model.onnx          # 버전 2 (신버전)
└── config.pbtxt

config.pbtxt:
version_policy {
  latest { num_versions: 2 }  # 최신 2개 버전 동시 서빙
}
```

클라이언트는 특정 버전 요청 가능:
```python
response = triton_client.infer(
    model_name="SMAP_E-1",
    model_version="2",  # 버전 지정
    inputs=inputs
)
```

## 성능 최적화

### 1. Dynamic Batching
여러 요청을 배치로 묶어 처리:

```
dynamic_batching {
  max_queue_delay_microseconds: 100
  preferred_batch_size: [ 4, 8 ]
}
```

### 2. Instance Group
모델 인스턴스 복제로 처리량 증가:

```
instance_group [
  {
    count: 4          # 4개 인스턴스
    kind: KIND_GPU
    gpus: [ 0 ]
  }
]
```

### 3. TensorRT FP16
정밀도를 FP16으로 낮춰 2배 속도 향상:

```bash
trtexec --onnx=model.onnx --fp16 --saveEngine=model.plan
```

## 모니터링

### 모델 상태 확인
```bash
curl http://localhost:8000/v2/models
curl http://localhost:8000/v2/models/SMAP_E-1
```

### 통계 조회
```bash
curl http://localhost:8000/v2/models/SMAP_E-1/stats
```

### 헬스체크
```bash
curl http://localhost:8000/v2/health/ready
curl http://localhost:8000/v2/health/live
```

## 현재 배포 상태

### ONNX Models (27개)
- **EPS (전력)**: SMAP_E-1, E-2, E-3, E-4, E-5
- **ACS (자세제어)**: SMAP_A-1, A-2, A-3, A-4, A-5
- **FSW (비행 SW)**: SMAP_F-1, F-2, F-3
- **TCS (열제어)**: SMAP_T-1, T-2, T-3
- **Data (데이터)**: SMAP_D-1, D-2, D-3, D-4, D-5
- **SS (구조)**: SMAP_S-1
- **PS (추진)**: SMAP_P-1, P-2, P-3, P-4, P-7

### 추론 성능
- **GPU**: RTX 5060 (8GB VRAM)
- **평균 추론 시간**: 40-50ms per window
- **처리량**: ~20-25 inferences/sec
- **메모리 사용**: 4.8GB / 8.1GB

## 향후 로드맵

1. **Phase 1 (현재)**: ONNX Runtime 백엔드
2. **Phase 2**: TensorRT 변환으로 성능 2-5배 향상
3. **Phase 3**: PyTorch 백엔드 추가 (TranAD 원본)
4. **Phase 4**: Python 전처리/후처리 파이프라인
5. **Phase 5**: Ensemble 모델로 다중 알고리즘 앙상블

## 참고 자료

- [Triton 공식 문서](https://docs.nvidia.com/deeplearning/triton-inference-server/)
- [ONNX Runtime](https://onnxruntime.ai/)
- [TensorRT](https://developer.nvidia.com/tensorrt)
- [PyTorch Backend](https://github.com/triton-inference-server/pytorch_backend)
- [Python Backend](https://github.com/triton-inference-server/python_backend)
