#!/usr/bin/env python3
"""Complete the unfinished final test with a disclosed length-exception policy."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import random
import re
import shlex
import sys
import time

from core import (PROMPT, canonical_target, gate, legacy_restore, safe_rule,
                  score, sha, write_json)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def read_csv(path):
    path = Path(path)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def spoken_norm(text):
    return re.sub(r'\s+', ' ', re.sub(r"[^a-z0-9']+", ' ', str(text or '').lower())).strip()


def verify_file(path, expected, label):
    require(sha(path) == expected, 'Frozen input changed: ' + label)


def pct(value):
    return '—' if value is None else f'{100 * value:.2f}'


from recovery import SOURCE, PLAN_SHA, ORACLE_SHA, check_original, reuse_oracle, active_indices, reason, verify_lengths

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    require(args.output.is_dir() and not any(args.output.iterdir()), 'Output must be an existing empty directory')
    check_original()
    require(sha(args.plan) == PLAN_SHA, 'Recovery must reuse original resolved plan')
    plan = json.loads(args.plan.read_text())
    require(plan['status'] == 'resolved_and_frozen_before_task2_test'
            and plan['test_run_policy'].startswith('single frozen'), 'Invalid frozen plan')
    for key, expected in plan['resolved_sha256'].items():
        verify_file(plan[key], expected, key)
    for name, expected in plan['trained_model_sha256'].items():
        verify_file(Path(plan['trained_model']) / name, expected, 'trained_model/' + name)
    verify_file(plan['package_path'] + '/SHA256SUMS', plan['package_sha256s_sha256'], 'package inventory')
    selection = json.loads((Path(plan['package_path']) / 'dev_selection_record.json').read_text())
    require(selection['selected_primary_system'] == plan['primary_system']
            and selection['test_used_for_this_selection'] is False, 'Selection differs')
    for package, expected in plan['task2_versions'].items():
        if expected is not None:
            require(metadata.version(package) == expected, 'Package version changed: ' + package)
    import torch
    from transformers import AutoTokenizer, T5ForConditionalGeneration
    require(torch.cuda.is_available() and os.environ.get('SLURM_JOB_ID'), 'GPU allocation required')
    require(torch.cuda.get_device_name(0) == 'NVIDIA A800-SXM4-80GB', 'Unexpected GPU model')
    random.seed(42)
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.cuda.reset_peak_memory_stats()
    tokenizer = AutoTokenizer.from_pretrained(plan['trained_model'], local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(plan['trained_model'], local_files_only=True).to('cuda').eval()
    require(all(param.dtype == torch.float32 and bool(torch.isfinite(param).all()) for param in model.parameters()),
            'Trained model weights are not finite fp32')
    # Test references and ASR text are read only after all code/model/environment
    # checks pass. The marker persists across jobs and prevents another inference.
    marker = SOURCE / 'TASK2_TEST_RECOVERY_STARTED.json'
    with marker.open('x', encoding='utf-8') as f:
        json.dump({'job_id': os.environ['SLURM_JOB_ID'], 'started_at': datetime.now(timezone.utc).isoformat(),
                   'output': str(args.output), 'plan_sha256': sha(args.plan), 'recovery_of': '169151', 'policy_change': 'overlength raw=failed blank; guarded=unchanged conservative fallback; no truncation'}, f)
        f.write('\n')
    write_json(args.output / 'status.json', {'status': 'running', 'test_used': True,
               'marker': str(marker), 'post_test_tuning_allowed': False})
    manifest = read_csv(plan['test_manifest'])
    baseline = read_csv(plan['baseline_details'])
    task1 = read_csv(plan['task1_details'])
    require(len(manifest) == len(baseline) == len(task1) == 1200, 'Expected complete 1200-row test inputs')
    require(all(row.get('split', '').lower() == 'test' for row in manifest), 'Manifest is not test-only')
    def validate(details, name):
        for index, (ref, row) in enumerate(zip(manifest, details)):
            require(row['row_id'] == str(index), f'{name}: row order differs at {index}')
            for key in ('record_set', 'sql_id', 'archive_member', 'subset_id', 'split'):
                require(row[key] == ref[key], f'{name}: identity differs at {index}/{key}')
            require(row['reference_spoken'] == spoken_norm(ref['transcription_n']), f'{name}: spoken reference differs at {index}')
            require(row['hypothesis'] == spoken_norm(row['hypothesis_raw']), f'{name}: hypothesis normalization differs at {index}')
            require(not row['error'].strip(), f'{name}: technical ASR failure at {index}')
    validate(baseline, 'baseline')
    validate(task1, 'task1')
    inputs = {'oracle': [row['transcription_n'] for row in manifest],
              'baseline_asr': [row['hypothesis'] for row in baseline],
              'task1_asr': [row['hypothesis'] for row in task1]}
    rules = json.loads((Path(plan['package_path']) / 'rules_config.json').read_text())
    references = [canonical_target(row['excel_original_text']) for row in manifest]
    require(all(references), 'Empty canonical reference')
    target_max = max(map(len, tokenizer(text_target=references, truncation=False)['input_ids']))
    require(target_max <= plan['max_target_tokens'], 'Test target exceeds frozen diagnostic budget')
    # Reference target length is an evaluation integrity check and never enters generate().
    write_json(args.output / 'length_audit.json', {'reference_target_max': target_max})
    torch.cuda.synchronize()
    generation_started = time.perf_counter()
    all_metrics, per_subset, diagnostics, timing = {}, {}, {}, []
    length_audit = {}
    for mode, sources in inputs.items():
        lengths = list(map(len, tokenizer([PROMPT.format(text=s) for s in sources], truncation=False)['input_ids']))
        verify_lengths(mode, lengths, plan['max_source_tokens'])
        length_audit[mode] = {'maximum': max(lengths), 'over_limit': {str(i): n for i,n in enumerate(lengths) if n > plan['max_source_tokens']}}
        write_json(args.output / 'source_length_audit.json', length_audit)
        if mode == 'oracle':
            records = reuse_oracle(SOURCE, args.output, manifest, references, sources, rules)
            print('oracle reused: 1200 rows x 4 files, no inference repeated', flush=True)
        else:
            records = {name: [] for name in ('raw_t5', 'guarded_t5', 'legacy_rules', 'conservative_rules')}
            files = {name: (args.output / f'{mode}_{name}.jsonl').open('x', encoding='utf-8') for name in records}
            try:
                for start in range(0, 1200, plan['eval_batch_size']):
                    batch_sources = sources[start:start + plan['eval_batch_size']]
                    batch_lengths = lengths[start:start + len(batch_sources)]
                    active = active_indices(batch_sources, batch_lengths, plan['max_source_tokens'])
                    candidates, ended, token_counts = [''] * len(batch_sources), [None] * len(batch_sources), [0] * len(batch_sources)
                    if active:
                        prompts = [PROMPT.format(text=batch_sources[i]) for i in active]
                        encoded = tokenizer(prompts, padding=True, return_tensors='pt', truncation=False).to('cuda')
                        torch.cuda.synchronize()
                        batch_start = time.perf_counter()
                        with torch.inference_mode():
                            ids = model.generate(**encoded, **plan['generation'])
                        torch.cuda.synchronize()
                        timing.append({'mode': mode, 'first_row': start, 'rows': len(active),
                                       'seconds': time.perf_counter() - batch_start})
                        decoded = tokenizer.batch_decode(ids, skip_special_tokens=True)
                        for j, i in enumerate(active):
                            tokens = ids[j].cpu().tolist()[1:]
                            candidates[i] = decoded[j]
                            ended[i] = tokenizer.eos_token_id in tokens
                            token_counts[i] = tokens.index(tokenizer.eos_token_id) + 1 if ended[i] else len(tokens)
                    for offset, source in enumerate(batch_sources):
                        index = start + offset
                        force = reason(source, batch_lengths[offset], plan['max_source_tokens'], ended[offset])
                        decision = gate(source, candidates[offset], rules, force_reason=force)
                        common = {'row_id': str(index), 'record_set': manifest[index]['record_set'],
                                  'sql_id': manifest[index]['sql_id'], 'archive_member': manifest[index]['archive_member'],
                                  'subset_id': manifest[index]['subset_id'], 'split': 'test', 'mode': mode,
                                  'source': source, 'reference': references[index],
                                  'reference_original': manifest[index]['excel_original_text'],
                                  'source_evidence': safe_rule(source, rules)}
                        items = {
                            'raw_t5': {**common, 'prediction': candidates[offset], 'candidate_raw': candidates[offset],
                                       'generation_reached_eos': ended[offset], 'generated_tokens': token_counts[offset],
                                       'model_invoked': offset in active,
                                       'source_tokens': batch_lengths[offset],
                                       'error': 'source_length_budget_exceeded' if batch_lengths[offset] > plan['max_source_tokens'] else ''},
                            'guarded_t5': {**common, 'prediction': decision['text'], 'candidate_raw': candidates[offset],
                                          'generation_reached_eos': ended[offset], 'generated_tokens': token_counts[offset],
                                       'model_invoked': offset in active,
                                       'source_tokens': batch_lengths[offset],
                                       'error': 'source_length_budget_exceeded' if batch_lengths[offset] > plan['max_source_tokens'] else '',
                                          'accepted': decision['accepted'],
                                          'fallback_reason': None if decision['accepted'] else decision['reason']},
                            'legacy_rules': {**common, 'prediction': legacy_restore(source, rules)},
                            'conservative_rules': {**common, 'prediction': safe_rule(source, rules)},
                        }
                        for name, item in items.items():
                            records[name].append(item)
                            files[name].write(json.dumps(item, ensure_ascii=False, allow_nan=False) + '\n')
                    if start % 200 == 196:
                        for handle in files.values():
                            handle.flush()
                        print(f'test {mode}: {start + len(batch_sources)}/1200', flush=True)
            finally:
                for handle in files.values():
                    handle.close()
        all_metrics[mode] = {name: score(items) for name, items in records.items()}
        per_subset[mode] = {}
        for name, items in records.items():
            grouped = defaultdict(list)
            for item in items:
                grouped[item['subset_id']].append(item)
            per_subset[mode][name] = {subset: score(group) for subset, group in grouped.items()}
        diagnostics[mode] = {'source_empty': sum(not s.strip() for s in sources),
            'raw_empty_on_nonempty_source': sum(bool(s.strip()) and not r['prediction'].strip() for s, r in zip(sources, records['raw_t5'])),
            'generation_length_cap': sum(r['generation_reached_eos'] is False for r in records['raw_t5']),
            'input_overlength_rows': sum(n > plan['max_source_tokens'] for n in lengths),
            'accepted_rows': sum(r['accepted'] for r in records['guarded_t5']),
            'fallback_reasons': dict(__import__('collections').Counter(r['fallback_reason'] for r in records['guarded_t5'] if r['fallback_reason']))}
    torch.cuda.synchronize()
    result = {'status': 'task2_final_test_complete_with_disclosed_recovery', 'test_used': True, 'rows_per_mode': 1200,
              'recovery': {'original_job': '169151', 'original_marker_preserved': True, 'oracle_reused_sha256': ORACLE_SHA,
                  'source_limit_unchanged': 256, 'baseline_row_526_tokens': 285,
                  'raw_overlength_policy': 'no model call; failed blank prediction scored on all 1200 rows',
                  'guarded_overlength_policy': 'no model call; frozen conservative rule fallback',
                  'original_protocol_fully_unchanged': False, 'model_and_selection_unchanged': True},
              'primary_system': plan['primary_system'], 'systems': all_metrics, 'per_subset': per_subset,
              'diagnostics': diagnostics, 'task1_asr_summary': plan['task1_asr_summary'],
              'generation': plan['generation'], 'precision': plan['precision'],
              'trained_model_sha256': plan['trained_model_sha256'], 'plan_sha256': sha(args.plan),
              'test_input_sha256': {key: plan['resolved_sha256'][key] for key in ('test_manifest','baseline_details','task1_details')},
              'test_history': plan['test_history'], 'post_test_tuning_allowed': False,
              'runtime': {'generation_and_postprocess_seconds': time.perf_counter() - generation_started,
                          'timed_generation_batches': timing,
                          'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
                          'peak_reserved_bytes': torch.cuda.max_memory_reserved(),
                          'gpu': torch.cuda.get_device_name(0), 'torch': torch.__version__,
                          'timing_scope': 'Recovery only: baseline/task1 GPU generation batches; oracle reused; excludes prior oracle runtime and ASR/audio'},
              'command': shlex.join(sys.argv)}
    result['output_prediction_sha256'] = {p.name: sha(p) for p in sorted(args.output.glob('*.jsonl'))}
    write_json(args.output / 'final_result.json', result)
    primary = result['systems']['task1_asr']['legacy_rules']
    raw = result['systems']['task1_asr']['raw_t5']
    guarded = result['systems']['task1_asr']['guarded_t5']
    lines = ['# 任务二最终 test 报告', '',
             '模型、规则和主系统选择在 test 前冻结。169151 已完成 oracle；本次复用其文件，仅完成尚未生成的两类 ASR 输入。Baseline 第 526 条为 285 token，超出原 256 上限，本次补充 raw 失败空预测及 guarded 保守规则回退。这是 test 期间的技术协议修复，不声称完全保持原协议；全部行保留在分母中，未根据 test 分数调参。', '',
             '| 输入 | 系统 | WER | Exact | 实体 P | 实体 R | 实体 F1 | 回退率 |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for mode in ('oracle','baseline_asr','task1_asr'):
        for system in ('raw_t5','guarded_t5','legacy_rules','conservative_rules'):
            m = result['systems'][mode][system]; e = m['entity_micro']
            lines.append(f"| {mode} | {system} | {pct(m['corpus_wer'])}% | {pct(m['exact_rate'])}% | {pct(e['precision'])}% | {pct(e['recall'])}% | {pct(e['f1'])}% | {pct(m['fallback_rate'])}% |")
    lines += ['', '## 冻结主系统', '',
              f"任务一 ASR + legacy rules：WER {pct(primary['corpus_wer'])}%，Exact {pct(primary['exact_rate'])}%，实体 F1 {pct(primary['entity_micro']['f1'])}%。",
              f"训练后 T5 raw：WER {pct(raw['corpus_wer'])}%，Exact {pct(raw['exact_rate'])}%，实体 F1 {pct(raw['entity_micro']['f1'])}%。",
              f"训练后 T5 guarded：WER {pct(guarded['corpus_wer'])}%，Exact {pct(guarded['exact_rate'])}%，实体 F1 {pct(guarded['entity_micro']['f1'])}%，回退率 {pct(guarded['fallback_rate'])}%。", '',
              '主系统在看 test 结果前由 dev 选择；本报告同时保留模型原始和 gate 后结果，不在 test 上重新选择。', '',
              '## 限制', '',
              '- canonical 实体由冻结规则提取，不是人工 NER 金标准；全部 test 行均计入 FP/FN。',
              '- ASR 预测复用任务一保存结果，没有再次运行音频推理；本作业时间不是完整端到端音频延迟。',
              '- 任务一已有历史 test 使用，详见 test_history；任务二未用 test 选择模型、规则、gate 或 checkpoint。',
              '- 运行结束后不得根据本报告继续调参或修改规则并重跑 test。', '']
    (args.output / 'FINAL_TEST_REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    write_json(args.output / 'COMPLETE.json', {'status': result['status'], 'job_id': os.environ['SLURM_JOB_ID'],
               'completed_at': datetime.now(timezone.utc).isoformat(), 'test_used': True,
               'post_test_tuning_allowed': False})
    write_json(args.output / 'status.json', {'status': result['status'], 'test_used': True,
               'post_test_tuning_allowed': False})
    print('TASK2_FINAL_TEST_COMPLETE', args.output, flush=True)
    print(json.dumps({'primary_task1_legacy': {'wer': primary['corpus_wer'], 'exact': primary['exact_rate'],
          'entity_f1': primary['entity_micro']['f1']},
          'task1_raw_t5': {'wer': raw['corpus_wer'], 'exact': raw['exact_rate'], 'entity_f1': raw['entity_micro']['f1']},
          'task1_guarded_t5': {'wer': guarded['corpus_wer'], 'exact': guarded['exact_rate'],
                               'entity_f1': guarded['entity_micro']['f1'], 'fallback_rate': guarded['fallback_rate']}}, indent=2), flush=True)


if __name__ == '__main__':
    main()
