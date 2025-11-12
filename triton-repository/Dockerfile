# Multi-Backend Triton Server for RTX 5060 (CUDA 13.0)
# Supports: PyTorch, ONNX Runtime, TensorRT, TorchScript, Python Backend

# Base Image: Triton Server 24.08 (CUDA 12.6 base, compatible with CUDA 13.0 runtime)
FROM nvcr.io/nvidia/tritonserver:24.08-py3

# Environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libcurl4 \
    fontconfig \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ============================================================
# Backend 1: PyTorch (CUDA 12.4 - RTX 5060 호환)
# ============================================================
RUN pip uninstall -y torch torchvision torchaudio && \
    pip install --no-cache-dir \
    torch==2.4.1 \
    torchvision==0.19.1 \
    --index-url https://download.pytorch.org/whl/cu124

# ============================================================
# Backend 2: ONNX Runtime (GPU)
# ============================================================
RUN pip install --no-cache-dir onnxruntime-gpu==1.19.2

# ============================================================
# Backend 3: TensorRT
# TensorRT는 Triton 24.08 이미지에 이미 포함되어 있음
# /usr/lib/x86_64-linux-gnu/libnvinfer.so.*
# ============================================================

# ============================================================
# Backend 4: Python Backend Dependencies
# OmniAnomaly 및 기타 Python 모델용
# ============================================================
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    scikit-learn \
    pyyaml \
    pydantic

# Model repository (각 백엔드별로 분리된 구조)
WORKDIR /models
VOLUME ["/models"]

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/v2/health/ready || exit 1

# Triton Server startup
# --backend-directory: 명시하지 않으면 기본 경로 사용 (/opt/tritonserver/backends)
# TorchScript, TensorRT, ONNX Runtime는 기본 포함됨
CMD ["tritonserver", \
     "--model-repository=/models", \
     "--strict-model-config=false", \
     "--log-verbose=1", \
     "--backend-config=python,shm-default-byte-size=33554432", \
     "--model-control-mode=poll"]
