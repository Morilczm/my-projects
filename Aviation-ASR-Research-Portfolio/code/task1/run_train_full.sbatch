#!/usr/bin/env bash
#SBATCH --job-name=czm-lora-full
#SBATCH --partition=gpu_a800
#SBATCH --gpus=1
#SBATCH --cpus-per-task=4
#SBATCH --output=/data/home/scyb475/run/czm/logs/train_full_%j.out
#SBATCH --error=/data/home/scyb475/run/czm/logs/train_full_%j.err

set -euo pipefail
: "${SLURM_JOB_ID:?Use sbatch; do not run on the login node}"
export PROJECT_ROOT=/data/home/scyb475/run/zz
export PIPELINE="$PROJECT_ROOT/atc_entity_pipeline_20260723"
export RUN_ROOT=/data/home/scyb475/run/czm
export PYTHON="$PROJECT_ROOT/envs/whisperatc/bin/python"
export SUBSET="$PROJECT_ROOT/data_relationship_audit/intern_assessment_subset_20260911"
export MODEL=/data/home/scyb475/run/model/WhisperATC/whisper-large-v3-atco2-asr
export LABELS_DIR="$RUN_ROOT/weak_labels/train_v1"
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export PYTHONPATH="$PIPELINE/src_entity_aux:$PIPELINE/src:/data/home/scyb475/.local/lib/python3.10/site-packages"
cd "$PROJECT_ROOT"

PREPARE="$RUN_ROOT/scripts/prepare_train_smoke.py"
TRAINER="$RUN_ROOT/src/train_task1_prefix_fixed.py"
OUT="$RUN_ROOT/adapters/train_full_${SLURM_JOB_ID}"
META="$RUN_ROOT/metadata/train_full_${SLURM_JOB_ID}"
test ! -e "$OUT"
test ! -e "$META"
mkdir -p "$META"
cp "$0" "$META/job_script.sbatch"
hostname
date -Is
nvidia-smi > "$META/nvidia_smi.txt"

"$PYTHON" -c 'import torch; assert torch.cuda.is_available(), "No GPU visible; refusing training"; print("GPU:", torch.cuda.get_device_name(0))'
"$PYTHON" "$PREPARE" > "$META/preparation.log"
cat "$META/preparation.log"
# Require the same corrected trainer, train data, weak labels, and model configs as the successful smoke.
sha256sum --check "$RUN_ROOT/metadata/train_smoke_163018/inputs.sha256" > "$META/smoke_inputs_check.txt"
cat "$META/smoke_inputs_check.txt"
cp "$TRAINER" "$META/train_task1_prefix_fixed.py"
sha256sum "$TRAINER" "$LABELS_DIR/weak_labels.jsonl" "$SUBSET/train_manifest.csv.gz" \
  "$MODEL/config.json" "$MODEL/generation_config.json" > "$META/inputs.sha256"
"$PYTHON" -m pip freeze > "$META/requirements.txt"

# The trainer loads the base and creates a fresh LoRA. No smoke adapter is loaded.
COMMON=(
  --manifest "$SUBSET/train_manifest.csv.gz"
  --weak-labels "$LABELS_DIR/weak_labels.jsonl"
  --model "$MODEL"
  --output "$OUT"
  --target-column transcription_n
  --loss-mode native
  --entity-weight 1.0
  --lora-scope decoder
  --sampling-mode random
  --learning-rate 1e-4
  --grad-accum 8
  --seed 42
  --num-workers 0
  --limit 0
  --max-steps 1500
)

"$PYTHON" "$TRAINER" "${COMMON[@]}" --audit-only --audit-all
COMMAND=("$PYTHON" "$TRAINER" "${COMMON[@]}")
printf '%q ' "${COMMAND[@]}" > "$META/command.txt"
printf '\n' >> "$META/command.txt"
SECONDS=0
"${COMMAND[@]}"
printf '%s\n' "$SECONDS" > "$META/training_process_wall_seconds.txt"

"$PYTHON" - "$OUT" <<'PY'
import json
import math
import sys
from pathlib import Path

out = Path(sys.argv[1])
s = json.loads((out / 'entity_weighted_lora_summary.json').read_text())
assert s['status'] == 'ok'
assert s['rows'] == s['manifest_rows'] == 12000, s
assert s['micro_steps'] == 12000 and s['optimizer_steps'] == 1500, s
assert s['loss_mode'] == 'native' and s['entity_weight'] == 1.0
assert s['lora_scope'] == 'decoder' and s['sampling_mode'] == 'random'
assert math.isfinite(s['mean_loss']), s
assert s['unit_weight_loss_invariant'] == 'passed'
assert s['gradient_audit']['decoder']['nonzero_grad'] > 0
assert s['gradient_audit']['encoder']['trainable'] == 0
assert (out / 'adapter_config.json').is_file()
weights = [out / name for name in ('adapter_model.safetensors', 'adapter_model.bin')]
assert any(p.is_file() and p.stat().st_size > 0 for p in weights)
prefix = json.loads((out / 'prefix_alignment.json').read_text())
assert prefix['status'] == 'ok'
assert prefix['decoder_prefix_ids'] == [50258, 50259, 50360, 50364]
print('TRAIN_FULL_DONE ' + str(out))
print('Next: inspect saved delta and reload for full dev evaluation. Optimizer step counter alone does not prove every AMP update succeeded.')
PY
date -Is
