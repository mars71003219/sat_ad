#!/usr/bin/env python3
"""
Triton ONNX Model Repository 배포 스크립트
satellite_model_mapping.json 기반 위성별 모델 배포
"""

import os
import shutil
import json
from pathlib import Path

# 경로 설정
ONNX_DIR = Path("tranad/onnx_models")
TRITON_MODELS_DIR = Path("triton-models-onnx")
MAPPING_FILE = Path("triton-omnianomaly/satellite_model_mapping.json")

# satellite_model_mapping.json 로드
with open(MAPPING_FILE) as f:
    mapping_data = json.load(f)

# 필요한 모델 추출
required_models = set()
for sat_id, subsystems in mapping_data['mapping'].items():
    for subsystem, model_name in subsystems.items():
        required_models.add(model_name)

print("Triton ONNX Model Repository 설정 중...")
print(f"위성별 서브시스템 모델 매핑 적용")
print(f"필요한 고유 모델 수: {len(required_models)}\n")

# 기존 디렉토리 제거 및 재생성
if TRITON_MODELS_DIR.exists():
    shutil.rmtree(TRITON_MODELS_DIR)
TRITON_MODELS_DIR.mkdir(parents=True)

# config.pbtxt 템플릿
CONFIG_TEMPLATE = """name: "{model_name}"
backend: "onnxruntime"
max_batch_size: 0

input [
  {{
    name: "input_data"
    data_type: TYPE_FP32
    dims: [ 1, 25 ]
  }}
]

output [
  {{
    name: "reconstruction"
    data_type: TYPE_FP32
    dims: [ 1, 25 ]
  }},
  {{
    name: "anomaly_score"
    data_type: TYPE_FP32
    dims: [ 1, 1 ]
  }},
  {{
    name: "anomaly_detected"
    data_type: TYPE_FP32
    dims: [ 1, 1 ]
  }}
]

# ONNX Runtime 최적화
optimization {{
  graph: {{
    level: 1
  }}
}}

# GPU 실행 설정
instance_group [
  {{
    count: 1
    kind: KIND_GPU
    gpus: [ 0 ]
  }}
]

# 동적 배칭
dynamic_batching {{
  max_queue_delay_microseconds: 100
}}
"""

deployed_count = 0
for model_name in sorted(required_models):
    onnx_file = ONNX_DIR / f"{model_name}.onnx"

    if not onnx_file.exists():
        print(f"⚠️  {model_name}: ONNX 파일 없음 (건너뜀)")
        continue

    print(f"배포 중: {model_name}")

    # 모델 디렉토리 생성
    model_dir = TRITON_MODELS_DIR / model_name
    version_dir = model_dir / "1"
    version_dir.mkdir(parents=True)

    # ONNX 모델 복사
    shutil.copy(onnx_file, version_dir / "model.onnx")

    # config.pbtxt 생성
    config_content = CONFIG_TEMPLATE.format(model_name=model_name)
    (model_dir / "config.pbtxt").write_text(config_content)

    print(f"  ✓ {model_name} 배포 완료")
    deployed_count += 1

print("\n" + "=" * 50)
print("Triton ONNX Model Repository 설정 완료")
print("=" * 50)
print(f"배포된 모델: {deployed_count}개")
print(f"저장 경로: {TRITON_MODELS_DIR}/")
print()
print("위성별 매핑 요약:")
for sat_id, subsystems in sorted(mapping_data['mapping'].items()):
    models = ", ".join(f"{k}={v}" for k, v in subsystems.items())
    print(f"  {sat_id}: {models}")
print()
print("다음 단계:")
print("1. docker-compose -f docker-compose.topic-centric.yml up -d --build triton-server")
print("2. docker logs -f triton-server (모델 로딩 확인)")
print("3. 시뮬레이터 실행 및 추론 테스트")
