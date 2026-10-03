#!/usr/bin/env python3
"""Full dev evaluation (1200 x 3 modes), frozen score/gate, streaming records."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import shlex
import sys
import time

from core import (PROMPT, MODES, INPUT_SHA, canonical_target, gate, safe_rule,
                  read_inputs, score, sha, write_json)
from common import (environment, load_config, read_json, require, setup_torch,
                    verify_hashes, verify_records, verify_rules)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--stage', choices=['pretrained', 'trained'], required=True)
    args = parser.parse_args()
    config = load_config(args.run / 'code/config.json')
    record = read_json(args.run / 'model_record.json')
    rules = verify_rules(args.run / 'prepared', args.inputs)
    if args.stage == 'trained':
        training = read_json(args.run / 'training/training.json')
        require(training['optimizer_steps'] == 1500 and training['train_rows'] == 12000
                and training['test_used'] is False and training['config'] == config, 'Incomplete full training')
        model_path = args.run / 'training/model'
        hashes = training['checkpoint_sha256']
    else:
        require(record['revision'] == config['revision'], 'Wrong base revision')
        model_path = Path(record['path'])
        hashes = record['files_sha256']
    verify_hashes(model_path, hashes)
    output = args.run / args.stage
    output.mkdir(exist_ok=False)
    write_json(output / 'status.json', {'status': 'running', 'test_used': False})
    torch = setup_torch(config)
    from transformers import AutoTokenizer, T5ForConditionalGeneration
    started = time.perf_counter()
    rows = read_inputs(args.inputs, 'dev')
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(model_path, local_files_only=True).to('cuda').eval()
    lengths = {}
    # Targets are inspected for coverage only, never passed to generate().
    for mode, field in MODES.items():
        lengths[mode] = max(map(len, tokenizer([PROMPT.format(text=r[field]) for r in rows], truncation=False)['input_ids']))
    lengths['reference_target'] = max(map(len, tokenizer(text_target=[canonical_target(r['excel_original_text']) for r in rows], truncation=False)['input_ids']))
    write_json(output / 'length_audit.json', lengths)
    require(all(lengths[mode] <= config['max_source_tokens'] for mode in MODES)
            and lengths['reference_target'] <= config['max_target_tokens'], 'Full dev token budget exceeded')

    def generate(sources):
        encoded = tokenizer([PROMPT.format(text=s) for s in sources], padding=True,
                            return_tensors='pt', truncation=False).to('cuda')
        require(encoded['input_ids'].shape[1] <= config['max_source_tokens'], 'Unvalidated input length')
        with torch.inference_mode():
            return model.generate(**encoded, **config['generation'])

    reload_passed = None
    if args.stage == 'trained':
        probes = read_json(args.run / 'training/reload_probes.json')
        actual = generate(probes['sources']).cpu().tolist()
        reload_passed = actual == probes['token_ids']
        write_json(output / 'reload_check.json', {'passed': reload_passed, 'probes': len(actual),
                    'expected_token_ids': probes['token_ids'], 'actual_token_ids': actual})
        require(reload_passed, 'Full model independent reload token IDs differ')
    generate([rows[0]['transcription_n']])
    summaries, per_subset, diagnostics, times = {}, {}, {}, []
    for mode, field in MODES.items():
        records = {'raw_model': [], 'guarded_model': []}
        diag = Counter()
        with (output / (mode + '_raw_model.jsonl')).open('x', encoding='utf-8') as raw_file, \
             (output / (mode + '_guarded_model.jsonl')).open('x', encoding='utf-8') as final_file:
            for start in range(0, len(rows), config['eval_batch_size']):
                batch = rows[start:start + config['eval_batch_size']]
                sources = [r[field] for r in batch]
                active = [i for i, source in enumerate(sources) if source.strip()]
                candidates, ended, generated_tokens = [''] * len(batch), [True] * len(batch), [0] * len(batch)
                if active:
                    try:
                        torch.cuda.synchronize()
                        t = time.perf_counter()
                        ids = generate([sources[i] for i in active])
                        torch.cuda.synchronize()
                        times.append({'mode': mode, 'first_row_id': batch[0]['row_id'],
                                      'rows': len(active), 'seconds': time.perf_counter() - t})
                        decoded = tokenizer.batch_decode(ids, skip_special_tokens=True)
                        token_lists = ids.cpu().tolist()
                    except Exception as exc:
                        raw_file.flush()
                        final_file.flush()
                        write_json(output / 'status.json', {'status': 'failed', 'mode': mode,
                            'row_ids': [r['row_id'] for r in batch], 'error': repr(exc),
                            'partial_rows_retained': len(records['raw_model']), 'test_used': False})
                        raise
                    for j, i in enumerate(active):
                        candidates[i] = decoded[j]
                        tokens = token_lists[j][1:]
                        ended[i] = tokenizer.eos_token_id in tokens
                        generated_tokens[i] = tokens.index(tokenizer.eos_token_id) + 1 if ended[i] else len(tokens)
                for i, row in enumerate(batch):
                    source = sources[i]
                    force = 'source_empty' if not source.strip() else None if ended[i] else 'generation_length_cap'
                    decision = gate(source, candidates[i], rules, force_reason=force)
                    common = {key: row[key] for key in ('row_id', 'record_set', 'sql_id', 'archive_member', 'subset_id')}
                    common.update(source=source, reference=canonical_target(row['excel_original_text']),
                                  reference_original=row['excel_original_text'], source_evidence=safe_rule(source, rules),
                                  candidate_raw=candidates[i], generation_reached_eos=ended[i], generated_tokens=generated_tokens[i],
                                  error=row.get('baseline_error' if mode == 'baseline_asr' else 'task1_error' if mode == 'task1_asr' else '', ''))
                    raw = {**common, 'prediction': candidates[i]}
                    final = {**common, 'prediction': decision['text'], 'accepted': decision['accepted'],
                             'fallback_reason': None if decision['accepted'] else decision['reason']}
                    for name, item, handle in [('raw_model', raw, raw_file), ('guarded_model', final, final_file)]:
                        records[name].append(item)
                        handle.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + '\n')
                    diag['source_empty'] += not source.strip()
                    diag['generation_length_cap'] += bool(source.strip()) and not ended[i]
                    diag['generated_empty_on_nonempty_source'] += bool(source.strip()) and not candidates[i].strip()
                    diag['accepted_rows'] += decision['accepted']
                if (start + len(batch)) % 200 == 0:
                    raw_file.flush()
                    final_file.flush()
                    print(f'{args.stage} {mode}: {start + len(batch)}/1200', flush=True)
        summaries[mode] = verify_records(records['raw_model'], records['guarded_model'], rows, field, rules)
        diagnostics[mode] = dict(diag)
        per_subset[mode] = {}
        for name, data in records.items():
            grouped = defaultdict(list)
            for item in data:
                grouped[item['subset_id']].append(item)
            per_subset[mode][name] = {key: score(group) for key, group in grouped.items()}
    result = {'status': 'full_dev_evaluated', 'stage': args.stage, 'rows_per_mode': 1200,
              'models': summaries, 'per_subset': per_subset, 'diagnostics': diagnostics,
              'reload_token_ids_match': reload_passed, 'generation': config['generation'],
              'model_generation_config': model.generation_config.to_dict(), 'precision': 'float32',
              'model_revision': record['revision'], 'weights_sha256': hashes, 'inputs_sha256': INPUT_SHA,
              'environment': environment(torch), 'process_wall_seconds': time.perf_counter() - started,
              'peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'peak_reserved_bytes': torch.cuda.max_memory_reserved(),
              'timed_generation_batches': times,
              'timing_scope': 'tokenization+generation+GPU sync; warmup excluded; no ASR, no audio, not per-utterance latency',
              'command': shlex.join(sys.argv), 'test_used': False}
    write_json(output / 'metrics.json', result)
    write_json(output / 'status.json', {'status': result['status'], 'test_used': False})
    print(f'{args.stage}: full dev completed, 3 x 1200 rows, raw and guarded retained.', flush=True)


if __name__ == '__main__':
    main()
