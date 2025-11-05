"""
Triton Python Backend - Thermal (온도) 서브시스템 LSTM 모델
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
    """Triton Python Backend Model - Thermal 서브시스템"""

    def initialize(self, args):
        """모델 초기화"""
        self.model_config = json.loads(args['model_config'])

        # Thermal 서브시스템 특징 수: 6개
        self.num_features = 6
        self.sequence_length = 30
        self.forecast_steps = 10
        self.hidden_size = 64
        self.num_layers = 2

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.model = LSTMNetwork(
            input_size=self.num_features,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            output_size=self.num_features
        )

        try:
            self.model = self.model.to(self.device)
            test_input = torch.randn(1, self.sequence_length, self.num_features).to(self.device)
            with torch.no_grad():
                _ = self.model(test_input)
            print(f"[Triton Thermal] Model initialized on {self.device}")
        except RuntimeError as e:
            print(f"[Triton Thermal] GPU initialization failed, falling back to CPU: {str(e)[:200]}")
            self.device = torch.device("cpu")
            self.model = self.model.cpu()

        self.model.eval()
        print(f"[Triton Thermal] Config: features={self.num_features}, seq_len={self.sequence_length}, forecast={self.forecast_steps}")

    def execute(self, requests):
        """추론 실행"""
        responses = []

        for request in requests:
            input_tensor = pb_utils.get_input_tensor_by_name(request, "input_data")
            input_data = input_tensor.as_numpy()

            if len(input_data.shape) == 2:
                input_data = np.expand_dims(input_data, axis=0)

            input_torch = torch.from_numpy(input_data).float().to(self.device)

            with torch.no_grad():
                predictions = []
                current_seq = input_torch

                for _ in range(self.forecast_steps):
                    pred = self.model(current_seq)
                    predictions.append(pred.unsqueeze(1))
                    current_seq = torch.cat([current_seq[:, 1:, :], pred.unsqueeze(1)], dim=1)

                predictions_output = torch.cat(predictions, dim=1)
                last_input = input_torch[:, -1, :]
                last_prediction = predictions_output[:, 0, :]
                anomaly_score = torch.mean(torch.abs(last_prediction - last_input), dim=1, keepdim=True)

            predictions_numpy = predictions_output.cpu().numpy().astype(np.float32).squeeze(0)
            anomaly_score_numpy = anomaly_score.cpu().numpy().astype(np.float32)

            predictions_tensor = pb_utils.Tensor("predictions", predictions_numpy)
            anomaly_tensor = pb_utils.Tensor("anomaly_score", anomaly_score_numpy)

            inference_response = pb_utils.InferenceResponse(
                output_tensors=[predictions_tensor, anomaly_tensor]
            )
            responses.append(inference_response)

        return responses

    def finalize(self):
        """모델 종료"""
        print("[Triton Thermal] Model finalized")
        del self.model
