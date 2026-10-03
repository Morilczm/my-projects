#!/usr/bin/env python3
"""One complete 12000-row epoch initialized from pinned Flan-T5-base."""
from contextlib import nullcontext
from datetime import datetime, timezone
import argparse
import json
import random
from pathlib import Path
import shlex
import sys
import time

from core import PROMPT, INPUT_SHA, canonical_target, read_inputs, sha, write_json
from common import (environment, load_config, read_json, require, setup_torch,
                    train_order, update_groups, verify_hashes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    args = parser.parse_args()
    run = args.run
    config = load_config(run / 'code/config.json')
    model_record = read_json(run / 'model_record.json')
    require(model_record['repo_id'] == config['repo_id'] and model_record['revision'] == config['revision'], 'Base model identity differs')
    verify_hashes(model_record['path'], model_record['files_sha256'])
    output = run / 'training'
    output.mkdir(exist_ok=False)
    torch = setup_torch(config)
    from transformers import AutoTokenizer, T5ForConditionalGeneration
    import transformers
    started = time.perf_counter()
    write_json(output / 'status.json', {'status': 'running', 'test_used': False})
    tokenizer = AutoTokenizer.from_pretrained(model_record['path'], local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(model_record['path'], local_files_only=True).to('cuda')
    require(all(p.dtype == torch.float32 for p in model.parameters()), 'Expected fp32 model weights')
    rows = read_inputs(args.inputs, 'train')
    sources = [PROMPT.format(text=row['transcription_n']) for row in rows]
    targets = [canonical_target(row['excel_original_text']) for row in rows]
    require(all(targets), 'Empty target')
    encoded_sources = tokenizer(sources, truncation=False)
    encoded_targets = tokenizer(text_target=targets, truncation=False)['input_ids']
    lengths = {'max_source_tokens': max(map(len, encoded_sources['input_ids'])),
               'max_target_tokens': max(map(len, encoded_targets))}
    write_json(output / 'length_audit.json', lengths)
    require(lengths['max_source_tokens'] <= config['max_source_tokens'] and lengths['max_target_tokens'] <= config['max_target_tokens'],
            'Token budget exceeded; no training data truncated')
    order = train_order(len(rows), config['seed'])
    write_json(output / 'train_row_order.json', [rows[i]['row_id'] for i in order])
    groups = list(update_groups(order, config['micro_batch'], config['gradient_accumulation']))
    require(len(groups) == config['optimizer_steps'], 'Optimizer update count differs')
    require(all(len(g) == 2 and all(len(b) == 4 for b in g) for g in groups), 'Unexpected incomplete batch')
    optimizer = torch.optim.AdamW(model.parameters(), lr=config['learning_rate'], weight_decay=config['weight_decay'])
    anchor = model.get_input_embeddings().weight
    initial_anchor = anchor.detach().cpu().clone()
    bf16 = torch.cuda.is_bf16_supported()
    model.train()
    torch.cuda.synchronize()
    optimization_start = time.perf_counter()
    seen, batch_losses, processed_rows = [], [], 0
    with (output / 'steps.jsonl').open('x', encoding='utf-8') as log:
        for step, group in enumerate(groups, 1):
            optimizer.zero_grad(set_to_none=True)
            losses = []
            for indices in group:
                features = [{'input_ids': encoded_sources['input_ids'][i],
                             'attention_mask': encoded_sources['attention_mask'][i]} for i in indices]
                encoded = tokenizer.pad(features, padding=True, return_tensors='pt').to('cuda')
                target_features = [{'input_ids': encoded_targets[i]} for i in indices]
                labels = tokenizer.pad(target_features, padding=True, return_tensors='pt')['input_ids'].to('cuda')
                labels[labels == tokenizer.pad_token_id] = -100
                context = torch.autocast('cuda', dtype=torch.bfloat16) if bf16 else nullcontext()
                with context:
                    loss = model(**encoded, labels=labels).loss
                require(bool(torch.isfinite(loss)), f'Nonfinite loss at optimizer step {step}')
                losses.append(float(loss.detach()))
                (loss / len(group)).backward()
                seen.extend(indices)
                processed_rows += len(indices)
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), config['max_grad_norm'])
            require(bool(torch.isfinite(norm)) and float(norm) > 0, f'Invalid gradient at step {step}')
            optimizer.step()
            batch_losses.extend(losses)
            record = {'step': step, 'processed_rows': processed_rows, 'mean_microbatch_loss': sum(losses) / len(losses),
                      'gradient_norm_before_clip': float(norm), 'learning_rate': optimizer.param_groups[0]['lr']}
            log.write(json.dumps(record, allow_nan=False) + '\n')
            if step == 1 or step % 50 == 0 or step == len(groups):
                log.flush()
                print(json.dumps(record), flush=True)
    torch.cuda.synchronize()
    optimization_seconds = time.perf_counter() - optimization_start
    require(seen == order and len(set(seen)) == 12000 and processed_rows == 12000, 'Incomplete or duplicated train coverage')
    anchor_delta = float((anchor.detach().cpu() - initial_anchor).abs().max())
    require(anchor_delta > 0, 'No embedding update')
    require(all(bool(torch.isfinite(param).all()) for param in model.parameters()), 'Nonfinite final parameter')
    del initial_anchor
    model_path = output / 'model'
    model.save_pretrained(model_path, safe_serialization=True)
    tokenizer.save_pretrained(model_path)
    # Retain enough state for a deliberate future epoch-boundary continuation.
    # This version deliberately provides no automatic resume or additional epoch.
    torch.save({'completed_epoch': 1, 'optimizer_steps': len(groups), 'optimizer': optimizer.state_dict(),
                'python_rng_state': random.getstate(), 'torch_rng_state': torch.get_rng_state(),
                'cuda_rng_state_all': torch.cuda.get_rng_state_all(), 'config': config,
                'train_row_order_sha256': sha(output / 'train_row_order.json')}, output / 'training_state.pt')
    del optimizer
    model.eval()
    probes = [rows[i]['transcription_n'] for i in order[:2]]
    probe_features = tokenizer([PROMPT.format(text=t) for t in probes], padding=True, return_tensors='pt').to('cuda')
    with torch.inference_mode():
        probe_ids = model.generate(**probe_features, **config['generation']).cpu().tolist()
    write_json(output / 'reload_probes.json', {'sources': probes, 'token_ids': probe_ids})
    metadata = {
        'status': 'full_epoch_trained_reload_pending', 'created_at': datetime.now(timezone.utc).isoformat(),
        'train_rows': processed_rows, 'unique_rows_processed': len(set(seen)), 'epochs': 1, 'optimizer_steps': len(groups),
        'config': config, 'inputs_sha256': INPUT_SHA, 'base_model_revision': model_record['revision'],
        'base_model_record_sha256': sha(run / 'model_record.json'),
        'precision': 'bf16_autocast_fp32_weights' if bf16 else 'fp32', 'all_parameters_finite': True,
        'anchor_max_abs_update': anchor_delta, 'mean_microbatch_loss': sum(batch_losses) / len(batch_losses),
        'loss_scope': 'unweighted mean of per-microbatch token cross-entropy; not a generation-quality metric',
        'optimizer_loop_seconds': optimization_seconds, 'process_wall_seconds': time.perf_counter() - started,
        'environment': {**environment(torch), 'transformers_file': transformers.__file__},
        'peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'peak_reserved_bytes': torch.cuda.max_memory_reserved(),
        'checkpoint_sha256': {p.name: sha(p) for p in model_path.iterdir() if p.is_file()},
        'training_state_sha256': sha(output / 'training_state.pt'),
        'train_order_sha256': sha(output / 'train_row_order.json'), 'steps_sha256': sha(output / 'steps.jsonl'),
        'command': shlex.join(sys.argv), 'test_used': False,
    }
    write_json(output / 'training.json', metadata)
    write_json(output / 'status.json', {'status': metadata['status'], 'test_used': False})
    print(json.dumps({k: metadata[k] for k in ('status', 'train_rows', 'optimizer_steps', 'anchor_max_abs_update', 'optimizer_loop_seconds')}, indent=2), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # No final training.json is written before all required artifacts exist.
        raise
