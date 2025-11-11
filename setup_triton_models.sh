#!/bin/bash
# Triton Model Repository 설정 스크립트
# satellite_model_mapping.json 기반 위성별 ONNX 모델 배포

set -e

ONNX_DIR="tranad/onnx_models"
TRITON_MODELS_DIR="triton-models-onnx"

echo "Triton ONNX Model Repository 설정 중..."
echo "위성별 서브시스템 모델 매핑 적용"
echo ""

# satellite_model_mapping.json에 정의된 모든 모델
# sat1-sat5의 EPS, ACS, FSW, TCS, Data, SS, PS
REQUIRED_MODELS=(
    # sat1
    "SMAP_E-1" "SMAP_A-1" "SMAP_F-1" "SMAP_T-1" "SMAP_D-1" "SMAP_S-1" "SMAP_P-1"
    # sat2
    "SMAP_E-2" "SMAP_A-2" "SMAP_F-2" "SMAP_T-2" "SMAP_D-2" "SMAP_P-2"
    # sat3
    "SMAP_E-3" "SMAP_A-3" "SMAP_F-3" "SMAP_T-3" "SMAP_D-3" "SMAP_P-3"
    # sat4
    "SMAP_E-4" "SMAP_A-4" "SMAP_D-4" "SMAP_P-4"
    # sat5
    "SMAP_E-5" "SMAP_A-5" "SMAP_D-5" "SMAP_P-7"
)

# 중복 제거 (SMAP_S-1, SMAP_F-1, SMAP_T-1 등은 여러 위성에서 공유)
UNIQUE_MODELS=($(printf "%s\n" "${REQUIRED_MODELS[@]}" | sort -u))

# 기존 디렉토리 제거 및 재생성
rm -rf "$TRITON_MODELS_DIR"

deployed_count=0
for model_name in "${UNIQUE_MODELS[@]}"; do
    model_dir="$TRITON_MODELS_DIR/${model_name}"
    onnx_file="$ONNX_DIR/${model_name}.onnx"

    if [ ! -f "$onnx_file" ]; then
        echo "⚠️  $model_name: ONNX 파일 없음 (건너뜀)"
        continue
    fi

    echo "배포 중: $model_name"

    # Triton 모델 디렉토리 구조 생성
    mkdir -p "$model_dir/1"

    # ONNX 모델 복사
    cp "$onnx_file" "$model_dir/1/model.onnx"

    # config.pbtxt 생성
    cat > "$model_dir/config.pbtxt" << EOF
name: "${model_name}"
backend: "onnxruntime"
max_batch_size: 0

input [
  {
    name: "input_data"
    data_type: TYPE_FP32
    dims: [ 1, 25 ]
  }
]

output [
  {
    name: "reconstruction"
    data_type: TYPE_FP32
    dims: [ 1, 25 ]
  },
  {
    name: "anomaly_score"
    data_type: TYPE_FP32
    dims: [ 1, 1 ]
  },
  {
    name: "anomaly_detected"
    data_type: TYPE_FP32
    dims: [ 1, 1 ]
  }
]

# ONNX Runtime 최적화
optimization {
  graph: {
    level: 1
  }
}

# GPU 실행 설정
instance_group [
  {
    count: 1
    kind: KIND_GPU
    gpus: [ 0 ]
  }
]

# 동적 배칭 (성능 향상)
dynamic_batching {
  max_queue_delay_microseconds: 100
}
EOF

    echo "  ✓ $model_name 배포 완료"
    ((deployed_count++))
done

echo ""
echo "=========================================="
echo "Triton ONNX Model Repository 설정 완료"
echo "=========================================="
echo "배포된 모델: ${deployed_count}개"
echo "저장 경로: $TRITON_MODELS_DIR/"
echo ""
echo "위성별 매핑 요약:"
echo "  sat1: E-1, A-1, F-1, T-1, D-1, S-1, P-1"
echo "  sat2: E-2, A-2, F-2, T-2, D-2, S-1, P-2"
echo "  sat3: E-3, A-3, F-3, T-3, D-3, S-1, P-3"
echo "  sat4: E-4, A-4, F-1, T-1, D-4, S-1, P-4"
echo "  sat5: E-5, A-5, F-2, T-2, D-5, S-1, P-7"
echo ""
echo "다음 단계:"
echo "1. docker-compose -f docker-compose.topic-centric.yml up -d --build triton-server"
echo "2. docker logs -f triton-server (모델 로딩 확인)"
echo "3. 시뮬레이터 실행 및 추론 테스트"
