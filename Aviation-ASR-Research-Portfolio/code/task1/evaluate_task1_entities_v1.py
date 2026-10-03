#!/usr/bin/env python3
"""Recompute rule-based entity-value metrics from existing dev ASR predictions.

No model, audio, test data, or external service is used. Matching follows the
repository's per-utterance set of (entity_type, canonical_hint) values. The main
scope includes all dev rows; a reference-entity-positive scope is also reported
for compatibility with compare_controlled_entity_runs.entity_metrics.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shlex
import sys

sys.dont_write_bytecode = True

KINDS = {
    'callsign': '呼号', 'runway': '跑道', 'heading': '航向',
    'frequency': '频率', 'distance': '距离', 'time': '时间',
    'flight_level': '飞行高度层', 'altitude_m': '高度（米）',
    'altitude_ft': '高度（英尺）', 'speed': '速度', 'qnh': 'QNH',
    'pob': '机上人数', 'squawk': '应答机编码',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def norm(text):
    return re.sub(r'\s+', ' ', re.sub(r"[^a-z0-9']+", ' ', str(text or '').lower())).strip()


def calculate(tp, fp, fn):
    return {
        'tp': tp, 'fp': fp, 'fn': fn, 'support': tp + fn, 'predicted': tp + fp,
        'precision': tp / (tp + fp) if tp + fp else None,
        'recall': tp / (tp + fn) if tp + fn else None,
        'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def flatten(spans):
    return {(span['entity_type'], span['canonical_hint']) for span in spans}


def counts(gold, predicted):
    return len(gold & predicted), len(predicted - gold), len(gold - predicted)


def summarize(pairs, kinds):
    per_type = {}
    for kind in kinds:
        triples = [counts({x for x in g if x[0] == kind}, {x for x in p if x[0] == kind}) for g, p in pairs]
        tp, fp, fn = (sum(t[i] for t in triples) for i in range(3))
        per_type[kind] = calculate(tp, fp, fn)
        per_type[kind]['reference_rows'] = sum(any(x[0] == kind for x in g) for g, _ in pairs)
    totals = [sum(v[key] for v in per_type.values()) for key in ('tp', 'fp', 'fn')]
    micro = calculate(*totals)
    positive = [(g, p) for g, p in pairs if g]
    negative = [(g, p) for g, p in pairs if not g]
    return {
        'rows': len(pairs), 'reference_entity_rows': len(positive),
        'reference_no_entity_rows': len(negative),
        'entity_exact_on_reference_positive': sum(g == p for g, p in positive),
        'entity_exact_rate_on_reference_positive': sum(g == p for g, p in positive) / len(positive) if positive else None,
        'predicted_values_on_reference_no_entity_rows': sum(len(p) for _, p in negative),
        'rows_with_predictions_on_reference_no_entity_rows': sum(bool(p) for _, p in negative),
        'micro': micro, 'per_type': per_type,
    }


def verify_fingerprints(path, expected_manifest, manifest_hash):
    saved = {}
    for line in path.read_text().splitlines():
        fingerprint, filename = line.split(maxsplit=1)
        saved[filename.lstrip('*')] = fingerprint
    require(saved.get(str(expected_manifest)) == manifest_hash, f'Manifest fingerprint differs from {path}')


def validate_alignment(manifest, details, label):
    require(len(manifest) == len(details), f'{label}: row count differs')
    seen = set()
    for index, (reference, prediction) in enumerate(zip(manifest, details)):
        require(prediction['row_id'] == str(index), f'{label}: row order differs at {index}')
        require(reference.get('split', '').lower() == prediction['split'].lower() == 'dev', f'{label}: non-dev row {index}')
        identity = (reference['record_set'], reference['sql_id'], reference['archive_member'])
        require(identity not in seen, f'{label}: duplicate identity at {index}')
        seen.add(identity)
        for key in ('record_set', 'sql_id', 'archive_member', 'subset_id', 'source_row_id'):
            require(reference.get(key, '') == prediction.get(key, ''), f'{label}: {key} differs at {index}')
        require(norm(reference['transcription_n']) == prediction['reference_spoken'], f'{label}: reference differs at {index}')
        require(bool(prediction['reference_spoken']), f'{label}: empty reference {index}')
        require(prediction['hypothesis'] == norm(prediction['hypothesis_raw']), f'{label}: hypothesis normalization differs at {index}')
        require(not prediction['error'].strip(), f'{label}: technical failure at {index}; resolve before scoring')


def pct(value):
    return '—' if value is None else f'{100 * value:.2f}'


def report_markdown(result):
    models = result['models']
    b, l = (models[name]['all_dev_rows'] for name in ('baseline', 'lora'))
    lines = [
        '# 任务一：完整 dev 实体指标对照', '',
        f"生成时间（UTC）：{result['created_at']}。相同的 {result['rows']} 条 dev；未使用 test。", '',
        '## 统计口径', '',
        '- 复用仓库原有 atc_entity_rules.py，不修改规则。参考来自原始 transcription_n，预测来自已有 hypothesis。',
        '- 逐句以（实体类型，规则规范值）精确匹配；同一句内相同实体值去重，不跨句匹配，不评价 span 边界。',
        '- 主指标包含全部 1,200 条：参考没有提取到实体的句子中，预测新增的实体也计 FP。',
        '- 另报“参考实体阳性子集”，对应仓库论文主表的统计范围；两个范围不可混用。',
        '- 错值同时计一个 FP 和一个 FN；F1=2TP/(2TP+FP+FN)。分母为零记 null/—，有错误但 TP=0 时 F1=0。',
        '- Support 是逐句去重后参考实体值总数；表中的 P/R/F1 单位为 %。', '',
        '## 主结果：全部 dev', '',
        '| 模型 | TP | FP | FN | Support | Precision | Recall | F1 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for label, item in [('Baseline', b), ('正式 LoRA', l)]:
        m = item['micro']
        lines.append(f"| {label} | {m['tp']} | {m['fp']} | {m['fn']} | {m['support']} | {pct(m['precision'])} | {pct(m['recall'])} | {pct(m['f1'])} |")
    lines += ['', f"参考可提取到实体的句子：{b['reference_entity_rows']}；参考未提取到实体的句子：{b['reference_no_entity_rows']}。",
              f"后一组中预测新增实体值：Baseline {b['predicted_values_on_reference_no_entity_rows']}，LoRA {l['predicted_values_on_reference_no_entity_rows']}（并非人工确认的幻觉数量）。", '',
              '| 实体类型 | Support | 基模 P | 基模 R | 基模 F1 | LoRA P | LoRA R | LoRA F1 | ΔF1（百分点） |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for kind in KINDS:
        x, y = b['per_type'][kind], l['per_type'][kind]
        delta = None if x['f1'] is None or y['f1'] is None else y['f1'] - x['f1']
        lines.append(f"| {KINDS[kind]} ({kind}) | {x['support']} | {pct(x['precision'])} | {pct(x['recall'])} | {pct(x['f1'])} | {pct(y['precision'])} | {pct(y['recall'])} | {pct(y['f1'])} | {pct(delta)} |")
    lines += ['', '## 仓库兼容范围：仅参考实体阳性句子', '',
              '| 模型 | 句子数 | TP | FP | FN | P | R | F1 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name in ('baseline', 'lora'):
        item = models[name]['reference_entity_positive_rows']
        m = item['micro']
        lines.append(f"| {name} | {item['rows']} | {m['tp']} | {m['fp']} | {m['fn']} | {pct(m['precision'])} | {pct(m['recall'])} | {pct(m['f1'])} |")
    lines += ['', '## 范围与限制', '',
              '- 这是基于规则参考的 entity-value 指标，不是人工 NER 金标准，不直接等于音频中所有实体的识别准确率。',
              '- 呼号仅覆盖规则现有的 9 个 spoken airline 前缀：' + ', '.join(result['protocol']['callsign_prefixes']) + '。',
              '- 规则对关键词、数字读法和单位有要求；例如时间只匹配四位数字加 UTC。未提取到实体不等于文本中确实没有实体。',
              '- 既有规则可能有边界、漏检及规范值不一致问题；本轮冻结规则，不为提高分数修改它。人工复核候选另存。',
              '- Support 很小或为零的类别只作描述，不能据此得出稳定提升或下降结论。',
              '- 没有重新解码音频；下列错误候选仅是文本层面的诊断，尚未完成听音核验。', '',
              '## 文件', '',
              '- entity_comparison.json：两种范围、两模型的全部计数和指标。',
              '- entity_metrics.csv：可直接制表的分类结果（指标存 0–1 比率）。',
              '- entity_rows.jsonl：全部 1,200 条的参考/预测实体 span、TP/FP/FN，便于核验。',
              '- entity_changes.csv：实体有误或模型之间实体预测变化的句子，包含改进与退化候选。',
              '- protocol.json、inputs.sha256、冻结的规则与脚本：复现依据。',
              '- command.txt：使用同一输入重新计算的命令；重跑需换一个空输出目录。', '',
              '服务器结果目录：`' + result['output'] + '`', '',
              '## 可复算命令', '', '```bash', result['command'], '```', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--lora', type=Path, required=True)
    parser.add_argument('--rules', type=Path, required=True)
    parser.add_argument('--expected-rules-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-rows', type=int, default=1200)
    args = parser.parse_args()
    require(not args.output.exists(), 'Output already exists; use a fresh directory')
    require(digest(args.rules) == args.expected_rules_sha256, 'Entity rule source changed')
    manifest = read_csv(args.manifest)
    require(len(manifest) == args.expected_rows, 'Unexpected manifest row count')
    manifest_hash = digest(args.manifest)
    verify_fingerprints(args.baseline.parent / 'input_sha256.txt', args.manifest, manifest_hash)
    verify_fingerprints(args.lora.parent / 'input_sha256.txt', args.manifest, manifest_hash)
    details = {'baseline': read_csv(args.baseline), 'lora': read_csv(args.lora)}
    for name, rows in details.items():
        validate_alignment(manifest, rows, name)
    spec = importlib.util.spec_from_file_location('frozen_atc_entity_rules', args.rules)
    rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules)
    audit, changes = [], []
    pair_sets = {'baseline': [], 'lora': []}
    duplicated_values = Counter()
    for index, reference in enumerate(manifest):
        gold_spans = rules.extract_entity_spans(reference['transcription_n'])
        gold = flatten(gold_spans)
        require(all(kind in KINDS for kind, _ in gold), 'Unexpected entity type in reference')
        duplicated_values['reference'] += len(gold_spans) - len(gold)
        item = {'row_id': index, 'sql_id': reference['sql_id'], 'record_set': reference['record_set'],
                'subset_id': reference['subset_id'], 'archive_member': reference['archive_member'],
                'reference_spoken': reference['transcription_n'], 'reference_spans': gold_spans,
                'reference_values': sorted(gold), 'models': {}}
        for name, rows in details.items():
            hypothesis = rows[index]['hypothesis']
            spans = rules.extract_entity_spans(hypothesis)
            predicted = flatten(spans)
            require(all(kind in KINDS for kind, _ in predicted), 'Unexpected entity type in prediction')
            duplicated_values[name] += len(spans) - len(predicted)
            pair_sets[name].append((gold, predicted))
            item['models'][name] = {'hypothesis': hypothesis, 'hypothesis_raw': rows[index]['hypothesis_raw'],
                                    'spans': spans, 'values': sorted(predicted),
                                    'tp': sorted(gold & predicted), 'fp': sorted(predicted - gold),
                                    'fn': sorted(gold - predicted)}
        audit.append(item)
        b, l = item['models']['baseline'], item['models']['lora']
        be, le = len(b['fp']) + len(b['fn']), len(l['fp']) + len(l['fn'])
        if be or le or b['values'] != l['values']:
            changes.append({'row_id': index, 'sql_id': reference['sql_id'], 'subset_id': reference['subset_id'],
                            'archive_member': reference['archive_member'],
                            'change': 'fewer_entity_errors' if le < be else 'more_entity_errors' if le > be else 'same_error_count',
                            'reference_spoken': reference['transcription_n'],
                            'baseline_hypothesis': b['hypothesis'], 'lora_hypothesis': l['hypothesis'],
                            'reference_values': json.dumps(sorted(gold), ensure_ascii=False),
                            'baseline_tp': json.dumps(b['tp']), 'baseline_fp': json.dumps(b['fp']), 'baseline_fn': json.dumps(b['fn']),
                            'lora_tp': json.dumps(l['tp']), 'lora_fp': json.dumps(l['fp']), 'lora_fn': json.dumps(l['fn'])})
    models = {}
    for name, pairs in pair_sets.items():
        models[name] = {'all_dev_rows': summarize(pairs, KINDS),
                        'reference_entity_positive_rows': summarize([(g, p) for g, p in pairs if g], KINDS)}
    protocol = {
        'task': 'task1 spoken-form ASR entity-value evaluation', 'test_used': False,
        'reference': 'raw train-independent dev transcription_n', 'prediction': 'saved normalized hypothesis',
        'matching': 'exact (entity_type, canonical_hint) set intersection within each row; deduplicate identical values within row',
        'main_scope': 'all dev rows including false positives on rows with no rule-extracted reference entities',
        'compatibility_scope': 'reference_entity_positive_rows; repository main-table entity_metrics scope',
        'zero_division': 'precision/recall: null when denominator=0; F1: 2TP/(2TP+FP+FN), null only when denominator=0',
        'callsign_prefixes': list(rules.CALLSIGN_PREFIXES), 'human_gold': False,
        'rules_path': str(args.rules), 'rules_sha256': digest(args.rules),
        'rules_changed': False, 'duplicate_spans_collapsed': dict(duplicated_values),
    }
    command = shlex.join([sys.executable, str(Path(__file__).absolute()), *sys.argv[1:]])
    result = {'status': 'ok', 'created_at': datetime.now(timezone.utc).isoformat(), 'rows': len(manifest),
              'same_dev_rows': True, 'test_used': False, 'models': models, 'protocol': protocol,
              'output': str(args.output), 'command': command,
              'sources': {'manifest': str(args.manifest), 'baseline': str(args.baseline), 'lora': str(args.lora)},
              'entity_change_counts': dict(Counter(row['change'] for row in changes))}
    args.output.mkdir(parents=True)
    (args.output / 'atc_entity_rules_frozen.py').write_bytes(args.rules.read_bytes())
    (args.output / 'evaluate_task1_entities.py').write_bytes(Path(__file__).read_bytes())
    (args.output / 'command.txt').write_text(command + '\n')
    inputs = [args.manifest, args.baseline, args.lora, args.rules, Path(__file__).absolute()]
    (args.output / 'inputs.sha256').write_text(''.join(f'{digest(path)}  {path}\n' for path in inputs))
    write_json(args.output / 'protocol.json', protocol)
    write_json(args.output / 'entity_comparison.json', result)
    with (args.output / 'entity_rows.jsonl').open('w', encoding='utf-8') as handle:
        for item in audit:
            handle.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + '\n')
    table = []
    for name, scopes in models.items():
        for scope, scores in scopes.items():
            for kind, metrics in [('micro', scores['micro']), *scores['per_type'].items()]:
                table.append({'model': name, 'scope': scope, 'entity_type': kind,
                              'label_zh': KINDS.get(kind, '总体 micro'), **metrics})
    for filename, records in [('entity_metrics.csv', table), ('entity_changes.csv', changes)]:
        fieldnames = list(dict.fromkeys(key for record in records for key in record))
        with (args.output / filename).open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
    (args.output / 'ENTITY_REPORT.md').write_text(report_markdown(result), encoding='utf-8')
    print(json.dumps({'status': 'ok', 'rows': len(manifest), 'output': str(args.output),
                      'models': {name: {scope: scores['micro'] for scope, scores in scopes.items()}
                                 for name, scopes in models.items()}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
