"""
Common OmniAnomaly Model for Triton Inference Server
All SMAP entities use this shared implementation
"""

import sys
sys.path.append('/workspace/tranad_src')

import os
import numpy as np
import torch
import torch.nn as nn
import json
import triton_python_backend_utils as pb_utils
from typing import List, Dict, Any


class OmniAnomaly(nn.Module):
    """OmniAnomaly Model (KDD 19) - VAE-based anomaly detection"""
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

    def forward(self, x, hidden=None):
        hidden = torch.rand(2, 1, self.n_hidden, dtype=torch.float64) if hidden is not None else hidden
        out, hidden = self.lstm(x.view(1, 1, -1), hidden)
        # Encoding
        x = self.encoder(out)
        mu, logvar = torch.split(x, [self.n_latent, self.n_latent], dim=-1)
        # Reparameterization trick
        std = torch.exp(0.5*logvar)
        eps = torch.randn_like(std)
        x = mu + eps*std
        # Decoding
        x = self.decoder(x)
        return x.view(-1), mu.view(-1), logvar.view(-1), hidden


class TritonPythonModel:
    """Triton Python Backend for OmniAnomaly - Common Implementation"""

    def initialize(self, args: Dict[str, str]) -> None:
        """
        Initialize the model

        Args:
            args: Dictionary containing model configuration
        """
        self.model_config = json.loads(args['model_config'])

        # Extract entity name from model name (e.g., "smap_A-1" -> "A-1")
        model_name = self.model_config['name']
        self.entity = model_name.replace('smap_', '')

        # Device selection: GPU if available, else CPU
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Load OmniAnomaly model
        self.model = OmniAnomaly(feats=25).double()

        # Load checkpoint - construct path from model_repository
        # args contains: model_config, model_instance_kind, model_instance_device_id, model_repository, model_version, model_name
        model_repo = args.get('model_repository', '/models')
        model_version = args.get('model_version', '1')
        # model_repo already includes the model name, so just append version
        model_dir = os.path.join(model_repo, model_version)
        checkpoint_path = os.path.join(model_dir, 'model.ckpt')

        try:
            # Load checkpoint to CPU first to avoid CUDA kernel compatibility issues
            checkpoint = torch.load(checkpoint_path, map_location='cpu')
            self.model.load_state_dict(checkpoint['model_state_dict'])
            # Then move to target device
            self.model.to(self.device)
            self.model.eval()
            print(f"[OmniAnomaly {self.entity}] Model loaded successfully on {self.device}")
        except Exception as e:
            print(f"[OmniAnomaly {self.entity}] Failed to load checkpoint: {e}")
            raise

        # Anomaly threshold (from POT evaluation, dataset-specific)
        # SMAP threshold from constants.py: lm = (0.98, 1)
        self.threshold = 0.16  # Will be refined based on training stats

        # Hidden state (stateful inference)
        self.hidden = None

        print(f"[OmniAnomaly {self.entity}] Initialized with threshold={self.threshold}")

    def execute(self, requests: List) -> List:
        """
        Execute inference

        Args:
            requests: List of inference requests

        Returns:
            List of inference responses
        """
        responses = []

        for request in requests:
            try:
                # Parse input tensor
                input_tensor = pb_utils.get_input_tensor_by_name(request, "input_data")
                input_data = input_tensor.as_numpy()  # shape: (25,)

                # Convert to torch tensor
                x = torch.from_numpy(input_data).double().to(self.device)

                # OmniAnomaly inference
                with torch.no_grad():
                    reconstruction, mu, logvar, self.hidden = self.model(x, self.hidden)

                # Calculate anomaly score (MSE)
                reconstruction_np = reconstruction.cpu().numpy()
                anomaly_score = np.mean((input_data - reconstruction_np) ** 2)

                # Anomaly detection
                detected = anomaly_score > self.threshold

                # Prepare output tensors
                out_reconstruction = pb_utils.Tensor(
                    "reconstruction",
                    reconstruction_np.astype(np.float64)
                )
                out_score = pb_utils.Tensor(
                    "anomaly_score",
                    np.array([anomaly_score], dtype=np.float64)
                )
                out_detected = pb_utils.Tensor(
                    "anomaly_detected",
                    np.array([detected], dtype=bool)
                )

                # Create inference response
                response = pb_utils.InferenceResponse(
                    output_tensors=[out_reconstruction, out_score, out_detected]
                )
                responses.append(response)

            except Exception as e:
                error_msg = f"Error during inference: {str(e)}"
                print(f"[OmniAnomaly {self.entity}] {error_msg}")
                response = pb_utils.InferenceResponse(
                    output_tensors=[],
                    error=pb_utils.TritonError(error_msg)
                )
                responses.append(response)

        return responses

    def finalize(self) -> None:
        """Cleanup when model is unloaded"""
        print(f"[OmniAnomaly {self.entity}] Model finalized")
        self.hidden = None
