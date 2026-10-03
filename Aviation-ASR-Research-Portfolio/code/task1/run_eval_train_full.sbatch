#!/usr/bin/env bash
#SBATCH --job-name=czm-lora-devfull
#SBATCH --partition=gpu_a800
#SBATCH --gpus=1
#SBATCH --cpus-per-task=4
#SBATCH --chdir=/data/home/scyb475/run/czm
#SBATCH --output=/data/home/scyb475/run/czm/logs/eval_train_full_%j.out
#SBATCH --error=/data/home/scyb475/run/czm/logs/eval_train_full_%j.err

set -euo pipefail
: "${SLURM_JOB_ID:?Submit with sbatch; do not run on the login node}"
export PROJECT_ROOT=/data/home/scyb475/run/zz
export PIPELINE="$PROJECT_ROOT/atc_entity_pipeline_20260723"
export RUN_ROOT=/data/home/scyb475/run/czm
export PYTHON="$PROJECT_ROOT/envs/whisperatc/bin/python"
export MODEL=/data/home/scyb475/run/model/WhisperATC/whisper-large-v3-atco2-asr
export SUBSET="$PROJECT_ROOT/data_relationship_audit/intern_assessment_subset_20260911"
export ADAPTER="$RUN_ROOT/adapters/train_full_163783"
export BASELINE="$RUN_ROOT/results/baseline_dev_full_162200"
export OUT="$RUN_ROOT/results/eval_train_full_${SLURM_JOB_ID}"
export EVAL_SCRIPT="$PIPELINE/src_entity_aux/eval_v3_entity_confidence.py"
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export PYTHONPATH="$PIPELINE/src_entity_aux:$PIPELINE/src:/data/home/scyb475/.local/lib/python3.10/site-packages"
export OMP_NUM_THREADS=4
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$RUN_ROOT/tmp/eval_train_full_${SLURM_JOB_ID}"
export CUDA_CACHE_PATH="$RUN_ROOT/cache/cuda"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

cd "$RUN_ROOT"
test ! -e "$OUT"
mkdir -p "$OUT" "$TMPDIR" "$CUDA_CACHE_PATH"
cp "$0" "$OUT/job_script.sbatch"
hostname
date -Is
nvidia-smi > "$OUT/nvidia_smi.txt"

"$PYTHON" - <<'PY'
import csv
import gzip
import hashlib
import json
import math
import os
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np
import torch


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


torch.set_num_threads(4)
require(torch.cuda.is_available(), 'No visible GPU; refusing CPU inference')
out, adapter, baseline, model = (Path(os.environ[k]) for k in ('OUT', 'ADAPTER', 'BASELINE', 'MODEL'))
manifest = Path(os.environ['SUBSET']) / 'dev_manifest.csv.gz'
evaluator = Path(os.environ['EVAL_SCRIPT'])
expected = {}
for line in (baseline / 'input_sha256.txt').read_text().splitlines():
    fingerprint, path = line.split(maxsplit=1)
    expected[str(Path(path.lstrip('*')))] = fingerprint
for path in (manifest, evaluator):
    require(expected.get(str(path)) == sha(path), f'Baseline input/version differs: {path}')
with gzip.open(manifest, 'rt', encoding='utf-8-sig', newline='') as handle:
    rows = list(csv.DictReader(handle))
require(len(rows) == 1200, 'Expected exactly 1200 dev rows')
require(all(row.get('split', '').lower() == 'dev' for row in rows), 'Expected dev-only manifest')
require(all(row.get('transcription_n', '').strip() for row in rows), 'Empty reference in dev manifest')

baseline_summary = json.loads((baseline / 'baseline_dev_full_summary.json').read_text())
require(baseline_summary['status'] == 'ok' and baseline_summary['rows'] == 1200
        and baseline_summary['failed_rows'] == 0 and baseline_summary['test_used'] is False,
        'Invalid baseline coverage/status')
require(baseline_summary['max_new_tokens'] == 128
        and baseline_summary['no_repeat_ngram_size'] == 0
        and baseline_summary['adapter'] == '', 'Unexpected baseline generation settings')
versions = {package: version(package) for package in ('torch', 'transformers', 'peft', 'numpy', 'pandas', 'av')}
baseline_environment = json.loads((baseline / 'environment.json').read_text())
require(baseline_environment['model'] == str(model), 'Baseline base model path differs')
require(versions == baseline_environment['versions'], 'Package versions differ from baseline; review before comparison')

config = json.loads((adapter / 'adapter_config.json').read_text())
require(Path(config['base_model_name_or_path']).resolve() == model.resolve(), 'Adapter base model path differs')
require(config.get('peft_type') == 'LORA' and config.get('r') == 8
        and config.get('lora_alpha') == 16, 'Unexpected LoRA type/rank/alpha')
require(not any(config.get(key) for key in ('rank_pattern', 'alpha_pattern', 'use_rslora', 'use_dora')),
        'Nonstandard LoRA scaling requires a different audit')
require(set(config['target_modules']) == {'q_proj', 'k_proj', 'v_proj', 'out_proj'}, 'Unexpected LoRA targets')
prefix = json.loads((adapter / 'prefix_alignment.json').read_text())
require(prefix.get('status') == 'ok' and prefix.get('decoder_prefix_ids') == [50258, 50259, 50360, 50364],
        'Unexpected training prefix record')
scale = config['lora_alpha'] / config['r']
weights = adapter / 'adapter_model.safetensors'
if weights.is_file():
    from safetensors.torch import load_file
    state = load_file(str(weights), device='cpu')
else:
    weights = adapter / 'adapter_model.bin'
    state = torch.load(weights, map_location='cpu', weights_only=True)
for name, tensor in state.items():
    require(isinstance(tensor, torch.Tensor) and torch.isfinite(tensor).all().item(), f'Invalid tensor: {name}')
    require('.lora_A.' in name or '.lora_B.' in name, f'Unexpected saved parameter: {name}')

pairs, used = [], set()
for name, tensor_a in sorted(state.items()):
    if '.lora_A.' not in name:
        continue
    b_name = name.replace('.lora_A.', '.lora_B.')
    require(b_name in state, f'Missing LoRA B: {name}')
    used.update((name, b_name))
    a = tensor_a.detach().double().numpy()
    b = state[b_name].detach().double().numpy()
    require(a.shape == (8, 1280) and b.shape == (1280, 8), f'Unexpected matrix shape: {name}')
    side = 'encoder' if '.encoder.' in name else 'decoder' if '.decoder.' in name else 'other'
    require(side != 'other', f'Unexpected module location: {name}')
    # Compute ||B A||_F from rank-by-rank matrices without materializing B A.
    squared_norm = float(np.sum((b.T @ b) * (a @ a.T)))
    require(math.isfinite(squared_norm), f'Nonfinite effective delta: {name}')
    norm = math.sqrt(max(0.0, squared_norm)) * abs(scale)
    if side == 'encoder':
        require(np.count_nonzero(b) == 0, f'Frozen encoder B changed: {name}')
    pairs.append({'module': name.split('.lora_A.')[0], 'side': side,
                  'a_shape': list(a.shape), 'b_shape': list(b.shape), 'scaled_delta_fro_norm': norm})
require(used == set(state), 'Unpaired LoRA tensors')
decoder = [pair for pair in pairs if pair['side'] == 'decoder']
encoder = [pair for pair in pairs if pair['side'] == 'encoder']
nonzero = sum(pair['scaled_delta_fro_norm'] > 0 for pair in decoder)
report = {'adapter': str(adapter), 'weights_sha256': sha(weights), 'decoder_modules': len(decoder),
          'nonzero_decoder_delta_modules': nonzero, 'encoder_modules': len(encoder), 'pairs': pairs}
require(len(decoder) == 256 and len(encoder) == 128, 'Unexpected LoRA module count')
report['status'] = 'ok' if nonzero == 256 else 'blocked'
(out / 'adapter_delta_audit.json').write_text(json.dumps(report, indent=2))
require(nonzero == 256, 'Some decoder modules have no effective update; inspect adapter_delta_audit.json')

runtime = {'job_id': os.environ['SLURM_JOB_ID'], 'python': sys.executable, 'versions': versions,
           'gpu': torch.cuda.get_device_name(0), 'model': str(model), 'adapter': str(adapter),
           'manifest': str(manifest), 'dev_manifest_sha256': sha(manifest),
           'eval_script_sha256': sha(evaluator), 'baseline_inputs_match': True, 'test_used': False}
(out / 'environment.json').write_text(json.dumps(runtime, indent=2))
fingerprint_files = [manifest, evaluator, weights, adapter / 'adapter_config.json', adapter / 'prefix_alignment.json']
for filename in ('config.json', 'generation_config.json'):
    path = model / filename
    (out / ('base_' + filename)).write_bytes(path.read_bytes())
    fingerprint_files.append(path)
fingerprints = ''.join(f'{sha(path)}  {path}\n' for path in fingerprint_files)
(out / 'input_sha256.txt').write_text(fingerprints)
print('ADAPTER_DELTA_OK decoder_modules=256 nonzero_delta_modules=256 encoder_modules=128', flush=True)
print('BASELINE_INPUTS_MATCH rows=1200 test_used=false', flush=True)
PY

# Reload base and adapter in a separate process using the unchanged baseline evaluator.
COMMAND=(
  "$PYTHON" "$EVAL_SCRIPT"
  --manifest "$SUBSET/dev_manifest.csv.gz"
  --model "$MODEL"
  --adapter "$ADAPTER"
  --output-dir "$OUT"
  --name lora_full_dev
  --max-new-tokens 128
  --no-repeat-ngram-size 0
)
printf '%q ' "${COMMAND[@]}" > "$OUT/command.txt"
printf '\n' >> "$OUT/command.txt"
SECONDS=0
"${COMMAND[@]}"
printf '%s\n' "$SECONDS" > "$OUT/eval_process_wall_seconds.txt"

"$PYTHON" - <<'PY'
import csv
import json
import math
import os
from pathlib import Path


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


out, baseline = (Path(os.environ[key]) for key in ('OUT', 'BASELINE'))
s = json.loads((out / 'lora_full_dev_summary.json').read_text())
b = json.loads((baseline / 'baseline_dev_full_summary.json').read_text())
rows = read_csv(out / 'lora_full_dev_details.csv')
old = read_csv(baseline / 'baseline_dev_full_details.csv')
require(s['status'] == 'ok' and s['rows'] == 1200 and s['failed_rows'] == 0, 'Evaluation incomplete or failed')
require(s['test_used'] is False and s['adapter'] == os.environ['ADAPTER'], 'Wrong evaluation split or adapter')
require(len(rows) == len(old) == 1200, 'Result coverage differs')
comparison = []
for index, (row, prior) in enumerate(zip(rows, old)):
    for key in ('row_id', 'source_row_id', 'sql_id', 'archive_member', 'reference_spoken', 'subset_id', 'record_set', 'split'):
        require(row[key] == prior[key], f'Row identity differs: row={index} key={key}')
    require(not row['error'] and not prior['error'], f'Technical failure at row {index}')
    current_exact = row['reference_spoken'] == row['hypothesis']
    prior_exact = prior['reference_spoken'] == prior['hypothesis']
    change = ('both_exact' if prior_exact and current_exact else 'corrected' if current_exact
              else 'regressed' if prior_exact else 'both_inexact')
    comparison.append({
        'row_id': row['row_id'], 'sql_id': row['sql_id'], 'subset_id': row['subset_id'],
        'record_set': row['record_set'], 'archive_member': row['archive_member'],
        'reference_spoken': row['reference_spoken'], 'baseline_hypothesis': prior['hypothesis'],
        'lora_hypothesis': row['hypothesis'], 'baseline_raw': prior['hypothesis_raw'],
        'lora_raw': row['hypothesis_raw'], 'exact_change': change,
    })
exact = sum(row['reference_spoken'] == row['hypothesis'] for row in rows)
require(exact == s['exact'] and math.isclose(exact / 1200, s['exact_rate']), 'Exact summary differs from CSV')
require(all(math.isfinite(value) and value >= 0 for value in (b['corpus_wer'], s['corpus_wer'])), 'Invalid WER')
with (out / 'dev_comparison.csv').open('w', encoding='utf-8', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=list(comparison[0]))
    writer.writeheader()
    writer.writerows(comparison)
report = {
    'status': 'ok', 'rows': 1200, 'same_dev_rows': True, 'test_used': False, 'adapter': os.environ['ADAPTER'],
    'baseline_wer': b['corpus_wer'], 'adapter_wer': s['corpus_wer'],
    'wer_change_percentage_points': (s['corpus_wer'] - b['corpus_wer']) * 100,
    'relative_wer_reduction': (b['corpus_wer'] - s['corpus_wer']) / b['corpus_wer'] if b['corpus_wer'] else None,
    'baseline_exact': b['exact'], 'adapter_exact': exact,
    'baseline_exact_rate': b['exact_rate'], 'adapter_exact_rate': s['exact_rate'],
    'baseline_empty_normalized': sum(not row['hypothesis'].strip() for row in old),
    'adapter_empty_normalized': sum(not row['hypothesis'].strip() for row in rows),
    'baseline_empty_raw': sum(not row['hypothesis_raw'].strip() for row in old),
    'adapter_empty_raw': sum(not row['hypothesis_raw'].strip() for row in rows),
    'changed_hypotheses': sum(row['hypothesis'] != prior['hypothesis'] for row, prior in zip(rows, old)),
    'exact_change_counts': {key: sum(row['exact_change'] == key for row in comparison)
                            for key in ('both_exact', 'corrected', 'regressed', 'both_inexact')},
    'failed_rows': s['failed_rows'],
    'note': 'Status describes execution integrity, not a quality improvement gate. WER values are ratios.',
}
(out / 'dev_comparison.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2), flush=True)
print('ADAPTER_FULL_DEV_DONE ' + str(out), flush=True)
PY
date -Is
