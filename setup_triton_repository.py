#!/usr/bin/env python3
"""
통합 Triton Model Repository 구성 스크립트
- 단일 triton-repository/ 디렉토리에 모든 백엔드 통합
- ONNX, TensorRT, Python Backend 혼합 관리
"""

import os
import shutil
import json
from pathlib import Path

# 경로 설정
ONNX_DIR = Path("tranad/onnx_models")
TRITON_REPO = Path("triton-repository")
MAPPING_FILE = Path("triton-omnianomaly/satellite_model_mapping.json")

# satellite_model_mapping.json 로드
with open(MAPPING_FILE) as f:
    mapping_data = json.load(f)

# 필요한 모델 추출
required_models = set()
for sat_id, subsystems in mapping_data['mapping'].items():
    for subsystem, model_name in subsystems.items():
        required_models.add(model_name)

print("=" * 60)
print("통합 Triton Model Repository 구성")
print("=" * 60)
print(f"Repository 경로: {TRITON_REPO}/")
print(f"필요한 모델 수: {len(required_models)}")
print(f"백엔드: ONNX Runtime (GPU)")
print()

# 기존 디렉토리 정리
if TRITON_REPO.exists():
    print(f"기존 repository 제거: {TRITON_REPO}/")
    shutil.rmtree(TRITON_REPO)
TRITON_REPO.mkdir(parents=True)

# ONNX 모델용 config.pbtxt 템플릿
ONNX_CONFIG_TEMPLATE = """name: "{model_name}"
backend: "onnxruntime"
max_batch_size: 0

input [
  {{
    name: "input_data"
    data_type: TYPE_FP32
    dims: [ -1, 25 ]
  }}
]

output [
  {{
    name: "reconstruction"
    data_type: TYPE_FP32
    dims: [ -1, 25 ]
  }},
  {{
    name: "anomaly_score"
    data_type: TYPE_FP32
    dims: [ -1, 1 ]
  }},
  {{
    name: "anomaly_detected"
    data_type: TYPE_FP32
    dims: [ -1, 1 ]
  }}
]

optimization {{
  graph: {{
    level: 1
  }}
}}

instance_group [
  {{
    count: 1
    kind: KIND_GPU
    gpus: [ 0 ]
  }}
]

dynamic_batching {{
  max_queue_delay_microseconds: 100
}}
"""

deployed = {"onnx": 0, "tensorrt": 0, "python": 0}

# ONNX 모델 배포
print("ONNX 모델 배포 중...")
for model_name in sorted(required_models):
    onnx_file = ONNX_DIR / f"{model_name}.onnx"

    if not onnx_file.exists():
        print(f"  ⚠️  {model_name}: ONNX 파일 없음")
        continue

    # 모델 디렉토리 생성
    model_dir = TRITON_REPO / model_name
    version_dir = model_dir / "1"
    version_dir.mkdir(parents=True)

    # ONNX 모델 복사
    shutil.copy(onnx_file, version_dir / "model.onnx")

    # config.pbtxt 생성
    config_content = ONNX_CONFIG_TEMPLATE.format(model_name=model_name)
    (model_dir / "config.pbtxt").write_text(config_content)

    print(f"  ✓ {model_name} (ONNX)")
    deployed["onnx"] += 1

# TensorRT 모델 확인 (추후 추가 가능)
tensorrt_dir = Path("tranad/tensorrt_models")
if tensorrt_dir.exists():
    print("\nTensorRT 모델 배포 중...")
    for plan_file in sorted(tensorrt_dir.glob("*.plan")):
        model_name = plan_file.stem
        model_dir = TRITON_REPO / model_name
        version_dir = model_dir / "1"
        version_dir.mkdir(parents=True)

        shutil.copy(plan_file, version_dir / "model.plan")

        # TensorRT config.pbtxt
        config = f'''name: "{model_name}"
backend: "tensorrt"
max_batch_size: 0
input [{{ name: "input_data", data_type: TYPE_FP32, dims: [1, 25] }}]
output [{{ name: "reconstruction", data_type: TYPE_FP32, dims: [1, 25] }}]
'''
        (model_dir / "config.pbtxt").write_text(config)
        print(f"  ✓ {model_name} (TensorRT)")
        deployed["tensorrt"] += 1

print()
print("=" * 60)
print("Repository 구성 완료")
print("=" * 60)
print(f"총 배포 모델: {sum(deployed.values())}개")
print(f"  - ONNX Runtime: {deployed['onnx']}개")
print(f"  - TensorRT: {deployed['tensorrt']}개")
print(f"  - Python Backend: {deployed['python']}개")
print()
print("Repository 구조:")
print(f"  {TRITON_REPO}/")
for model_dir in sorted(TRITON_REPO.iterdir())[:5]:
    if model_dir.is_dir():
        backend = "unknown"
        config_file = model_dir / "config.pbtxt"
        if config_file.exists():
            config_text = config_file.read_text()
            if "onnxruntime" in config_text:
                backend = "ONNX"
            elif "tensorrt" in config_text:
                backend = "TensorRT"
            elif "python" in config_text:
                backend = "Python"
        print(f"    ├── {model_dir.name}/ ({backend})")
print(f"    └── ... ({sum(deployed.values()) - 5}개 더)")
print()
print("위성별 매핑:")
for sat_id, subsystems in sorted(mapping_data['mapping'].items()):
    models_str = ", ".join(f"{v}" for v in subsystems.values())
    print(f"  {sat_id}: {models_str}")
print()
print("다음 단계:")
print("1. docker-compose.yml에서 volume을 ./triton-repository:/models로 수정")
print("2. docker-compose up -d --build triton-server")
print("3. docker logs -f triton-server")
