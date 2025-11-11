#!/usr/bin/env python3
"""
OmniAnomaly 체크포인트를 ONNX로 변환하는 스크립트
RTX 5060 (CUDA 13.0) 환경에서 Triton Server에 배포 가능한 ONNX 모델 생성
"""

import os
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
import sys


# OmniAnomaly 모델 정의 (독립 실행을 위해 직접 정의)
class OmniAnomaly(nn.Module):
    """OmniAnomaly 모델 (KDD 19) - VAE 기반 시계열 이상 탐지"""
    def __init__(self, feats):
        super(OmniAnomaly, self).__init__()
        self.name = 'OmniAnomaly'
        self.lr = 0.002
        self.beta = 0.01
        self.n_feats = feats
        self.n_hidden = 32
        self.n_latent = 8
        self.lstm = nn.GRU(feats, self.n_hidden, 2)
        self.encoder = nn.Sequential(
            nn.Linear(self.n_hidden, self.n_hidden), nn.PReLU(),
            nn.Linear(self.n_hidden, self.n_hidden), nn.PReLU(),
            nn.Flatten(),
            nn.Linear(self.n_hidden, 2*self.n_latent)
        )
        self.decoder = nn.Sequential(
            nn.Linear(self.n_latent, self.n_hidden), nn.PReLU(),
            nn.Linear(self.n_hidden, self.n_hidden), nn.PReLU(),
            nn.Linear(self.n_hidden, self.n_feats), nn.Sigmoid(),
        )

    def forward(self, x, hidden = None):
        hidden = torch.rand(2, 1, self.n_hidden, dtype=x.dtype, device=x.device) if hidden is not None else hidden
        out, hidden = self.lstm(x.view(1, 1, -1), hidden)
        ## 인코딩
        x = self.encoder(out)
        mu, logvar = torch.split(x, [self.n_latent, self.n_latent], dim=-1)
        ## 재매개변수화 트릭
        std = torch.exp(0.5*logvar)
        eps = torch.randn_like(std)
        x = mu + eps*std
        ## 디코딩
        x = self.decoder(x)
        return x.view(-1), mu.view(-1), logvar.view(-1), hidden


class OmniAnomalyONNX(nn.Module):
    """
    ONNX 변환을 위한 OmniAnomaly 래퍼
    - 추론 시 hidden state를 외부에서 관리하지 않도록 단일 입력으로 변환
    - 출력: reconstruction, anomaly_score, anomaly_detected
    """
    def __init__(self, original_model):
        super().__init__()
        self.model = original_model
        self.n_hidden = original_model.n_hidden

    def forward(self, x):
        """
        Args:
            x: [batch_size, n_feats] - 단일 타임스텝 입력

        Returns:
            reconstruction: [batch_size, n_feats] - 재구성된 값
            anomaly_score: [batch_size, 1] - 이상 스코어
            anomaly_detected: [batch_size, 1] - 이상 감지 (0 or 1)
        """
        batch_size = x.size(0)
        n_feats = x.size(1)

        # 초기 hidden state (GRU 2 layers)
        hidden = torch.zeros(2, batch_size, self.n_hidden, dtype=x.dtype, device=x.device)

        # Forward pass
        x_recon, mu, logvar, _ = self.model(x, hidden)

        # Anomaly score: reconstruction error (MSE)
        recon_error = torch.mean((x.view(batch_size, -1) - x_recon.view(batch_size, -1)) ** 2, dim=1, keepdim=True)

        # Anomaly detection: threshold at 95th percentile (adjustable)
        # 실제 threshold는 POT로 결정하지만, ONNX에서는 고정값 사용
        threshold = 0.1  # 배포 시 조정 가능
        anomaly_detected = (recon_error > threshold).float()

        return x_recon.view(batch_size, n_feats), recon_error, anomaly_detected


def load_checkpoint(checkpoint_path, n_feats):
    """체크포인트 로드"""
    model = OmniAnomaly(n_feats)
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    # Float32로 변환 (ONNX 호환성)
    model = model.float()
    return model


def convert_checkpoint_to_onnx(checkpoint_path, output_dir, entity_name, n_feats=25):
    """
    단일 체크포인트를 ONNX로 변환

    Args:
        checkpoint_path: .ckpt 파일 경로
        output_dir: ONNX 출력 디렉토리
        entity_name: 엔티티 이름 (예: SMAP_A-1)
        n_feats: 입력 특징 수 (SMAP 기본값: 25)
    """
    print(f"Converting {checkpoint_path} to ONNX...")

    # 모델 로드
    original_model = load_checkpoint(checkpoint_path, n_feats)
    onnx_model = OmniAnomalyONNX(original_model)
    onnx_model.eval()

    # 더미 입력 (batch_size=1, n_feats=25)
    dummy_input = torch.randn(1, n_feats, dtype=torch.float32)

    # 출력 디렉토리 생성
    output_path = Path(output_dir) / f"{entity_name}.onnx"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ONNX 변환
    torch.onnx.export(
        onnx_model,
        dummy_input,
        str(output_path),
        input_names=['input_data'],
        output_names=['reconstruction', 'anomaly_score', 'anomaly_detected'],
        dynamic_axes={
            'input_data': {0: 'batch_size'},
            'reconstruction': {0: 'batch_size'},
            'anomaly_score': {0: 'batch_size'},
            'anomaly_detected': {0: 'batch_size'}
        },
        opset_version=14,
        do_constant_folding=True,
    )

    print(f"✓ Saved to {output_path}")
    return output_path


def convert_all_checkpoints(checkpoint_dir, output_dir, n_feats=25):
    """
    checkpoints/OmniAnomaly/ 디렉토리의 모든 체크포인트 변환
    """
    checkpoint_dir = Path(checkpoint_dir)
    output_dir = Path(output_dir)

    # 모든 .ckpt 파일 찾기
    checkpoint_files = sorted(checkpoint_dir.glob("*.ckpt"))

    if not checkpoint_files:
        print(f"No checkpoint files found in {checkpoint_dir}")
        return []

    print(f"Found {len(checkpoint_files)} checkpoints")

    converted = []
    for ckpt_path in checkpoint_files:
        # 파일명에서 엔티티 이름 추출 (model_SMAP_A-1.ckpt -> SMAP_A-1)
        entity_name = ckpt_path.stem.replace("model_", "")

        try:
            onnx_path = convert_checkpoint_to_onnx(
                str(ckpt_path),
                str(output_dir),
                entity_name,
                n_feats
            )
            converted.append(onnx_path)
        except Exception as e:
            print(f"✗ Failed to convert {ckpt_path.name}: {e}")

    print(f"\n✓ Successfully converted {len(converted)}/{len(checkpoint_files)} models")
    return converted


def main():
    """메인 실행"""
    script_dir = Path(__file__).parent
    checkpoint_dir = script_dir / "checkpoints" / "OmniAnomaly"
    output_dir = script_dir / "onnx_models"

    print("=" * 60)
    print("OmniAnomaly Checkpoint → ONNX Converter")
    print("=" * 60)
    print(f"Checkpoint directory: {checkpoint_dir}")
    print(f"Output directory: {output_dir}")
    print()

    # 모든 체크포인트 변환
    converted_files = convert_all_checkpoints(checkpoint_dir, output_dir, n_feats=25)

    if converted_files:
        print("\n" + "=" * 60)
        print("Conversion Summary")
        print("=" * 60)
        for onnx_path in converted_files:
            print(f"  {onnx_path.name}")
        print()
        print(f"Next steps:")
        print(f"1. Copy ONNX models to Triton model repository")
        print(f"2. Create config.pbtxt for each model")
        print(f"3. Start Triton Server and test inference")


if __name__ == "__main__":
    main()
