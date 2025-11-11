# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TranAD is a deep transformer network for anomaly detection in multivariate time series data, published in VLDB 2022. The codebase implements TranAD and several baseline models (GDN, MAD_GAN, MTAD_GAT, MSCRED, USAD, OmniAnomaly, LSTM_AD) for comparison.

## Installation

Python 3.7+ required:
```bash
pip3 install torch==1.8.1+cpu torchvision==0.9.1+cpu torchaudio===0.8.1 -f https://download.pytorch.org/whl/torch_stable.html
pip3 install -r requirements.txt
```

## Common Commands

### Preprocessing
Preprocess datasets before training (remove unavailable datasets from command if needed):
```bash
python3 preprocess.py SMAP MSL SWaT WADI SMD MSDS UCR MBA NAB
```

### Training and Testing
Train a model:
```bash
python3 main.py --model <model> --dataset <dataset> --retrain
```

Train with 20% data:
```bash
python3 main.py --model <model> --dataset <dataset> --retrain --less
```

Test only (load existing checkpoint):
```bash
python3 main.py --model <model> --dataset <dataset> --test
```

**Available models**: TranAD, GDN, MAD_GAN, MTAD_GAT, MSCRED, USAD, OmniAnomaly, LSTM_AD

**Available datasets**: SMAP, MSL, SWaT, WADI, SMD, MSDS, MBA, UCR, NAB

**Ablation models**: TranAD_SelfConditioning, TranAD_Adversarial, TranAD_Transformer, TranAD_Basic

## Architecture

### Main Entry Point
- `main.py`: Primary training/testing pipeline
  - `load_dataset()`: Loads preprocessed data from `processed/<dataset>/`
  - `load_model()`: Dynamically loads model class from `src/models.py`
  - `backprop()`: Handles training/testing for all model types with model-specific loss functions
  - `convert_to_windows()`: Converts time series to sliding windows for sequence models

### Data Flow
1. Raw data in `data/<dataset>/` → preprocessing via `preprocess.py` → `processed/<dataset>/*.npy`
2. Each dataset produces: `train.npy`, `test.npy`, `labels.npy` (with dataset-specific prefixes)
3. Training: data → windowing → model → loss → optimizer step → checkpoint saved to `checkpoints/<model>_<dataset>/`
4. Testing: data → windowing → model → anomaly scores → POT evaluation → metrics

### Key Modules
- `src/models.py`: Contains all model implementations (524 lines)
  - Each model is a PyTorch nn.Module with standardized attributes: `name`, `lr`, `n_window`, `batch`
  - TranAD variants (lines 354-524): TranAD_Basic, TranAD_Transformer, TranAD_Adversarial, TranAD_SelfConditioning, TranAD
  - Baseline models: LSTM variants, Attention, DAGMM, OmniAnomaly, USAD, GDN, MTAD_GAT, MSCRED, MAD_GAN

- `src/constants.py`: Dataset-specific hyperparameters
  - `lm_d`: POT threshold parameters per dataset
  - `lr_d`: Learning rates per dataset
  - `percentiles`: Threshold percentiles for MERLIN baseline

- `src/parser.py`: Command-line argument parser
  - `--model`, `--dataset`, `--test`, `--retrain`, `--less`

- `src/pot.py`: Peak-Over-Threshold evaluation for anomaly detection
- `src/diagnosis.py`: Anomaly diagnosis scoring (hit_att, ndcg metrics)
- `src/plotting.py`: Result visualization
- `src/utils.py`: Utility functions (cut_array for --less mode, color printing)
- `src/merlin.py`: MERLIN baseline implementation

### Model-Specific Backprop Logic
The `backprop()` function in `main.py` contains branching logic for each model type:
- **TranAD models** (line 251): Two-phase adversarial training with transformer encoder-decoder
- **GAN models** (line 212): Alternating discriminator/generator training
- **USAD** (line 155): Dual autoencoder adversarial training
- **OmniAnomaly** (line 132): VAE with KLD loss
- **Attention models** (line 105): Multi-head attention
- **DAGMM** (line 79): Gaussian Mixture Model
- **GDN/MTAD_GAT/MSCRED** (line 182): Standard MSE reconstruction

### Checkpointing
Models save to `checkpoints/<model>_<dataset>/model.ckpt` with:
- `model_state_dict`, `optimizer_state_dict`, `scheduler_state_dict`
- `epoch`, `accuracy_list`
- Loaded automatically unless `--retrain` is specified

### Output
- Training loss printed per epoch
- Test results: precision, recall, f1, TP/FP/TN/FN, Hit@100%, NDCG@100%, threshold
- Plots saved to `plots/<model>_<dataset>/`
- Default: 5 epochs training, AdamW optimizer, StepLR scheduler (step=5, gamma=0.9)

## Dataset Preprocessing Details
- `preprocess.py` handles 10 datasets with custom loaders per dataset
- Normalization methods: `normalize()`, `normalize2()`, `normalize3()` for different datasets
- SMAP/MSL: Loads from pre-split train/test .npy files, extracts anomaly indices from CSV
- SWaT/WADI: Loads from CSV with timestamp-based anomaly labels
- SMD: Multiple machines, loads from .txt files with separate interpretation labels
- UCR/NAB: Single-variate time series
- MBA: Excel-based input
- Output: All datasets saved as (samples, features) numpy arrays

## Important Notes
- Models expect data shape: (batch_size, window_size, n_features) for windowed models
- POT (Peak-Over-Threshold) is used for threshold selection, not fixed thresholds
- Dataset-specific hyperparameters in `src/constants.py` are tuned per paper results
- Original baseline implementations may differ from paper versions (see README warning)
