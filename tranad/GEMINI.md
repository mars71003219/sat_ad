# GEMINI.md: TranAD Project

## Project Overview

This project, "TranAD," is the official implementation for the paper "TranAD: Deep Transformer Networks for Anomaly Detection in Multivariate Time Series Data," published in VLDB 2022. It provides a framework for training and evaluating various anomaly detection models, with a focus on the proposed Transformer-based model, TranAD.

The project is written in Python and uses the PyTorch library for model implementation. It is designed to work with a variety of standard time-series anomaly detection datasets such as SMAP, MSL, SWaT, and SMD.

The core logic is split into two main stages:
1.  **Preprocessing (`preprocess.py`):** Raw dataset files (CSVs, JSON, etc.) are processed, normalized, and saved into a consistent NumPy (`.npy`) format in the `processed/` directory.
2.  **Training/Testing (`main.py`):** The preprocessed `.npy` files are loaded to train and evaluate the specified anomaly detection model. Results, plots, and model checkpoints are saved in the `results/`, `plots/`, and `checkpoints/` directories, respectively.

## Building and Running

### 1. Installation

The project requires Python 3.7+ and the dependencies listed in `requirements.txt`.

```bash
# 1. Install PyTorch (CPU version specified in README)
pip3 install torch==1.8.1+cpu torchvision==0.9.1+cpu torchaudio===0.8.1 -f https://download.pytorch.org/whl/torch_stable.html

# 2. Install other dependencies
pip3 install -r requirements.txt
```

### 2. Data Preprocessing

Before training, the raw datasets must be preprocessed. The `preprocess.py` script handles this for all supported datasets.

```bash
# Preprocess all datasets
python3 preprocess.py SMAP MSL SWaT WADI SMD MSDS UCR MBA NAB
```
This will create `.npy` files in the `processed/<dataset_name>/` directories.

### 3. Training and Evaluation

The `main.py` script is the main entry point for training and testing models.

```bash
# To train and evaluate a model (e.g., TranAD on SMAP)
python3 main.py --model TranAD --dataset SMAP --retrain

# To run in test-only mode (using a pre-trained checkpoint)
python3 main.py --model TranAD --dataset SMAP --test
```

*   `--model`: Specifies the model to use (e.g., `TranAD`, `LSTM_AD`, `USAD`).
*   `--dataset`: Specifies the dataset to use (e.g., `SMAP`, `MSL`, `SWaT`).
*   `--retrain`: Forces the model to retrain even if a checkpoint exists.
*   `--test`: Skips training and only runs evaluation on the test set.

## Development Conventions

*   **Configuration:** Key hyperparameters (learning rate, batch size, window size) are defined within each model's class in `src/models.py`. Global constants are in `src/constants.py`.
*   **Data Loading:** The `main.py` script contains a `load_dataset` function that is hardcoded to load specific preprocessed files. For example, for the `SMAP` dataset, it is currently configured to only load the `P-1` channel's data (`P-1_train.npy`, `P-1_test.npy`, etc.), even though `preprocess.py` processes all available channels. This is an important detail for anyone modifying or extending the data loading pipeline.
*   **Model Architecture:** All model architectures are defined as `nn.Module` classes in `src/models.py`. This is the central file for understanding the different anomaly detection algorithms.
*   **Entry Point:** `main.py` orchestrates the entire workflow, from parsing arguments to loading data, training, testing, and saving results.
*   **Utilities:** Helper functions for plotting, color-coding terminal output, and other miscellaneous tasks are located in `src/utils.py`.
