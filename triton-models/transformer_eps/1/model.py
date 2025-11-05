"""
Triton Python Backend - EPS (전력) 서브시스템 LSTM 모델
"""
import numpy as np
import torch
import torch.nn as nn
import triton_python_backend_utils as pb_utils
import json


class LSTMNetwork(nn.Module):
    """LSTM 네트워크"""

    def __init__(self, input_size, hidden_size=64, num_layers=2, output_size=None):
        super(LSTMNetwork, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        if output_size is None:
            output_size = input_size

        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)

        out, _ = self.lstm(x, (h0, c0))
        out = self.fc(out[:, -1, :])
        return out


class TritonPythonModel:
    """Triton Python Backend Model - EPS 서브시스템"""

    def initialize(self, args):
        """모델 초기화"""
        self.model_config = json.loads(args['model_config'])

        # EPS 서브시스템 특징 수: 12개
        self.num_features = 12
        self.sequence_length = 30  # 입력 시퀀스 길이
        self.forecast_steps = 10   # 예측 스텝 수
        self.hidden_size = 64
        self.num_layers = 2

        # 디바이스 설정 (CPU/GPU)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # LSTM 모델 생성
        self.model = LSTMNetwork(
            input_size=self.num_features,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            output_size=self.num_features
        )

        try:
            self.model = self.model.to(self.device)
            # 테스트 실행
            test_input = torch.randn(1, self.sequence_length, self.num_features).to(self.device)
            with torch.no_grad():
                _ = self.model(test_input)
            print(f"[Triton EPS] Model initialized on {self.device}")
        except RuntimeError as e:
            print(f"[Triton EPS] GPU initialization failed, falling back to CPU: {str(e)[:200]}")
            self.device = torch.device("cpu")
            self.model = self.model.cpu()

        self.model.eval()
        print(f"[Triton EPS] Config: features={self.num_features}, seq_len={self.sequence_length}, forecast={self.forecast_steps}")

    def execute(self, requests):
        """추론 실행"""
        responses = []

        for request in requests:
            # 입력 텐서 추출: [sequence_length, features]
            input_tensor = pb_utils.get_input_tensor_by_name(request, "input_data")
            input_data = input_tensor.as_numpy()

            # 배치 차원 추가 및 PyTorch 텐서로 변환
            if len(input_data.shape) == 2:
                input_data = np.expand_dims(input_data, axis=0)

            input_torch = torch.from_numpy(input_data).float().to(self.device)

            # 추론 실행 (Autoregressive prediction)
            with torch.no_grad():
                predictions = []
                current_seq = input_torch

                for _ in range(self.forecast_steps):
                    pred = self.model(current_seq)  # [batch, features]
                    predictions.append(pred.unsqueeze(1))  # [batch, 1, features]

                    # 다음 시퀀스 생성
                    current_seq = torch.cat([
                        current_seq[:, 1:, :],  # 첫 번째 타임스텝 제거
                        pred.unsqueeze(1)        # 예측값 추가
                    ], dim=1)

                # 예측 결과 병합: [batch, forecast_steps, features]
                predictions_output = torch.cat(predictions, dim=1)

                # 이상 점수 계산 (간단한 재구성 오차)
                # 마지막 예측과 실제 입력의 평균 차이
                last_input = input_torch[:, -1, :]  # [batch, features]
                last_prediction = predictions_output[:, 0, :]  # [batch, features]
                anomaly_score = torch.mean(torch.abs(last_prediction - last_input), dim=1, keepdim=True)  # [batch, 1]

            # NumPy로 변환
            predictions_numpy = predictions_output.cpu().numpy().astype(np.float32).squeeze(0)  # [forecast_steps, features]
            anomaly_score_numpy = anomaly_score.cpu().numpy().astype(np.float32)  # [batch, 1]

            # Triton 출력 텐서 생성
            predictions_tensor = pb_utils.Tensor("predictions", predictions_numpy)
            anomaly_tensor = pb_utils.Tensor("anomaly_score", anomaly_score_numpy)

            # 응답 생성
            inference_response = pb_utils.InferenceResponse(
                output_tensors=[predictions_tensor, anomaly_tensor]
            )
            responses.append(inference_response)

        return responses

    def finalize(self):
        """모델 종료"""
        print("[Triton EPS] Model finalized")
        del self.model
