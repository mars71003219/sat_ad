#!/bin/bash
# Setup Triton model repository for OmniAnomaly SMAP entities

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKPOINT_DIR="/home/hsnam/projects/telemetry_anomaly_det/tranad/checkpoints/OmniAnomaly"
MODELS_DIR="$SCRIPT_DIR/models"

# List of SMAP entities to deploy
ENTITIES=("A-1" "A-2" "A-3" "A-4" "A-5" \
          "D-1" "D-2" "D-3" "D-4" "D-5" \
          "E-1" "E-2" "E-3" "E-4" "E-5" \
          "F-1" "F-2" "F-3" \
          "P-1" "P-2" "P-3" "P-4" "P-7" \
          "S-1" \
          "T-1" "T-2" "T-3")

echo "Setting up Triton OmniAnomaly models..."

for entity in "${ENTITIES[@]}"; do
    echo "Processing entity: $entity"

    # Create model directory
    model_name="smap_${entity}"
    model_dir="$MODELS_DIR/$model_name"
    mkdir -p "$model_dir/1"

    # Copy config.pbtxt (use A-1 as template)
    sed "s/smap_A-1/$model_name/g" "$MODELS_DIR/smap_A-1/config.pbtxt" > "$model_dir/config.pbtxt"

    # Copy common model.py implementation
    cp "$SCRIPT_DIR/common/omnianomaly_model.py" "$model_dir/1/model.py"

    # Copy checkpoint
    checkpoint_file="$CHECKPOINT_DIR/model_SMAP_${entity}.ckpt"
    if [ -f "$checkpoint_file" ]; then
        cp "$checkpoint_file" "$model_dir/1/"
        echo "  ✓ Copied checkpoint for $entity"
    else
        echo "  ✗ Checkpoint not found: $checkpoint_file"
    fi
done

echo "Model setup complete!"
echo "Models created in: $MODELS_DIR"
