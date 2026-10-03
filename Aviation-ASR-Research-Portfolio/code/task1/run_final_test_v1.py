#!/usr/bin/env python3
"""One frozen final test run; reuse audited historical baseline predictions."""
import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version

sys.dont_write_bytecode = True


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def csv_rows(path):
    path = Path(path)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pct(x):
    return '—' if x is None else f'{x*100:.2f}%'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--postprocess-only', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    out = args.output
    require(out.exists(), 'Job output directory must exist')
    for path, expected in plan['fingerprints'].items():
        require(sha(path) == expected, f'Frozen input changed: {path}')
    for path, stat in plan['base_weight_stat'].items():
        actual = Path(path).stat()
        require(actual.st_size == stat['size'] and actual.st_mtime_ns == stat['mtime_ns'], f'Base weight changed: {path}')
    for package, expected in plan['versions'].items():
        require(version(package) == expected, f'Package version changed: {package}')
    import numpy as np
    import torch
    evaluator = load_module('frozen_test_evaluator', plan['evaluator'])
    scorer = load_module('frozen_entity_scorer', plan['entity_scorer'])
    rules = load_module('frozen_entity_rules', plan['entity_rules'])
    manifest = csv_rows(plan['manifest'])
    require(len(manifest) == 1200 and all(r['split'] == 'test' for r in manifest), 'Expected complete 1200-row test')
    baseline = csv_rows(plan['baseline_details'])
    old_summary = json.loads(Path(plan['baseline_summary']).read_text())
    old_meta = json.loads(Path(plan['baseline_metadata']).read_text())

    def validate(rows, name):
        require(len(rows) == len(manifest), f'{name}: incomplete coverage')
        for i, (ref, row) in enumerate(zip(manifest, rows)):
            require(row['row_id'] == str(i), f'{name}: row order mismatch at {i}')
            for key in ('sql_id', 'archive_member', 'record_set', 'subset_id', 'split'):
                require(ref[key] == row[key], f'{name}: identity mismatch at {i}/{key}')
            require(evaluator.norm(ref['transcription_n']) == row['reference_spoken'], f'{name}: reference mismatch at {i}')
            require(evaluator.norm(row['hypothesis_raw']) == row['hypothesis'], f'{name}: normalization mismatch at {i}')
            require(not row['error'], f'{name}: technical failure at {i}')
    validate(baseline, 'baseline')
    require(old_meta['generation_config'] == json.loads((Path(plan['model'])/'generation_config.json').read_text()), 'Historical generation config changed')
    require(old_summary['rows'] == 1200 and old_summary['test_used'] and old_summary['adapter'] == '', 'Invalid historical baseline')
    require(old_summary['max_new_tokens'] == 128 and old_summary['no_repeat_ngram_size'] == 0, 'Historical decoding differs')
    name = 'lora_final_test'
    timing_file = out/'runtime.json'
    if not args.postprocess_only:
        require(torch.cuda.is_available(), 'GPU required')
        require(torch.cuda.get_device_name(0) == plan['gpu_model'], 'Expected same GPU type as dev and historical baseline')
        require(not (out/f'{name}_details.csv').exists(), 'Predictions already exist; refusing second inference')
        # The exclusive marker persists across job IDs, so accidental resubmission cannot rerun test inference.
        marker = args.plan.parent/'INFERENCE_STARTED.json'
        with marker.open('x') as handle:
            json.dump({'job_id':os.environ['SLURM_JOB_ID'], 'started_at':datetime.now(timezone.utc).isoformat(), 'output':str(out)},handle)
        random.seed(plan['seed'])
        np.random.seed(plan['seed'])
        torch.manual_seed(plan['seed'])
        torch.cuda.manual_seed_all(plan['seed'])
        torch.set_num_threads(4)
        torch.cuda.reset_peak_memory_stats()
        original_generate = evaluator.generate_one
        timings = []

        def timed_generate(*positional, **keywords):
            audio = keywords.get('audio') if 'audio' in keywords else positional[6]
            duration = len(audio)/16000.0
            torch.cuda.synchronize()
            start = time.perf_counter()
            try:
                return original_generate(*positional, **keywords)
            finally:
                torch.cuda.synchronize()
                timings.append({'row_id':len(timings), 'seconds':time.perf_counter()-start, 'decoded_audio_seconds':duration})
        evaluator.generate_one = timed_generate
        metadata = {
            'status':'running', 'job_id':os.environ['SLURM_JOB_ID'], 'started_at_utc':datetime.now(timezone.utc).isoformat(),
            'gpu':torch.cuda.get_device_name(0), 'versions':plan['versions'], 'seed':plan['seed'],
            'test_used':True, 'plan_sha256':sha(args.plan), 'base_weight_sha256':{},
            'timing_scope':'generate_one includes feature extraction, generation, token decoding and confidence; excludes archive/audio decode; first 3 calls excluded from steady summary',
        }
        # Hash on allocated compute node; no duplicate model files.
        metadata['base_weight_sha256'] = {path:sha(path) for path in plan['base_weight_stat']}
        command = [plan['evaluator'], '--manifest',plan['manifest'], '--model',plan['model'], '--adapter',plan['adapter'],
                   '--output-dir',str(out), '--name',name, '--max-new-tokens','128', '--no-repeat-ngram-size','0']
        dump(out/'command.json',command)
        dump(timing_file,metadata)
        start = time.perf_counter()
        try:
            sys.argv = command
            evaluator.main()
            metadata['status'] = 'ok'
        except BaseException as exc:
            metadata.update(status='failed', error=repr(exc))
            raise
        finally:
            metadata.update(wall_seconds=time.perf_counter()-start,
                            finished_at_utc=datetime.now(timezone.utc).isoformat(),
                            peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
                            peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved())
            steady = timings[3:]
            if steady:
                latencies = [t['seconds'] for t in steady]
                audio_seconds = sum(t['decoded_audio_seconds'] for t in steady)
                metadata['steady_timing'] = {'warmup_rows_excluded':3,'rows':len(steady),
                    'p50_seconds':float(np.percentile(latencies,50)), 'p95_seconds':float(np.percentile(latencies,95)),
                    'throughput_rows_per_second':len(steady)/sum(latencies),
                    'rtf':sum(latencies)/audio_seconds if audio_seconds else None,
                    'decoded_audio_seconds':audio_seconds}
            dump(out/'per_row_timing.json',timings)
            dump(timing_file,metadata)
    require((out/f'{name}_details.csv').exists(), 'No completed predictions for postprocessing')
    adapted = csv_rows(out/f'{name}_details.csv')
    validate(adapted,'lora')
    new_summary = json.loads((out/f'{name}_summary.json').read_text())
    require(new_summary['test_used'] and new_summary['adapter']==plan['adapter'] and new_summary['failed_rows']==0,'Invalid adapter summary')
    require(new_summary['status']=='ok' and new_summary['rows']==1200,'Incomplete adapter result')
    models, audit, comparisons = {}, [], []
    gold_sets = [scorer.flatten(rules.extract_entity_spans(r['transcription_n'])) for r in manifest]
    for model, rows, saved in [('baseline',baseline,old_summary),('lora',adapted,new_summary)]:
        words = sum(len(r['reference_spoken'].split()) for r in rows)
        errors = sum(evaluator.edit_distance(r['reference_spoken'].split(),r['hypothesis'].split()) for r in rows)
        exact = sum(r['reference_spoken']==r['hypothesis'] for r in rows)
        require(math.isclose(errors/words,saved['corpus_wer']) and exact==saved['exact'],f'{model}: saved ASR metrics mismatch')
        preds = [scorer.flatten(rules.extract_entity_spans(r['hypothesis'])) for r in rows]
        pairs = list(zip(gold_sets,preds))
        models[model] = {'asr':{'rows':len(rows),'corpus_wer':errors/words,'exact':exact,'exact_rate':exact/len(rows),
            'empty_normalized':sum(not r['hypothesis'].strip() for r in rows), 'empty_raw':sum(not r['hypothesis_raw'].strip() for r in rows), 'failed_rows':0},
            'all_test_rows':scorer.summarize(pairs,scorer.KINDS),
            'reference_entity_positive_rows':scorer.summarize([(g,p) for g,p in pairs if g],scorer.KINDS)}
        for i,(g,p) in enumerate(pairs):
            audit.append({'model':model,'row_id':i,'sql_id':rows[i]['sql_id'],'archive_member':rows[i]['archive_member'],
                          'reference_values':sorted(g),'predicted_values':sorted(p),'tp':sorted(g&p),'fp':sorted(p-g),'fn':sorted(g-p)})
    for i,(b,l) in enumerate(zip(baseline,adapted)):
        comparisons.append({'row_id':i,'sql_id':b['sql_id'],'archive_member':b['archive_member'],
            'reference_spoken':b['reference_spoken'],'baseline_hypothesis':b['hypothesis'],'lora_hypothesis':l['hypothesis'],
            'baseline_exact':b['reference_spoken']==b['hypothesis'],'lora_exact':l['reference_spoken']==l['hypothesis']})
    with (out/'test_comparison.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        w=csv.DictWriter(handle,fieldnames=list(comparisons[0])); w.writeheader(); w.writerows(comparisons)
    with (out/'entity_rows.jsonl').open('w',encoding='utf-8') as handle:
        for row in audit: handle.write(json.dumps(row,ensure_ascii=False)+'\n')
    records=[]
    for model,data in models.items():
        for scope in ('all_test_rows','reference_entity_positive_rows'):
            for kind,m in [('micro',data[scope]['micro']),*data[scope]['per_type'].items()]:
                records.append({'model':model,'scope':scope,'entity_type':kind,**{k:m[k] for k in ['tp','fp','fn','support','predicted','precision','recall','f1']}})
    with (out/'entity_metrics.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        w=csv.DictWriter(handle,fieldnames=list(records[0])); w.writeheader(); w.writerows(records)
    result={'status':'ok','test_used':True,'same_test_rows':True,'rows':1200,'models':models,
            'baseline_reused':True,'baseline_job_id':'161294','adapter':plan['adapter'],
            'adapter_final_test_runs':1,'known_history':plan['test_history'], 'protocol':plan['entity_protocol'],
            'runtime':json.loads(timing_file.read_text()),'plan_sha256':sha(args.plan),
            'quality_improvement_is_not_assumed':True}
    dump(out/'final_test_comparison.json',result)
    b,l = models['baseline'],models['lora']
    lines=['# 任务一最终 test 对照','',f"完整 test：1,200 条。正式模型：`{plan['adapter']}`。",'',
           '## 最终结果','', '| 指标 | Baseline | 正式 LoRA |','|---|---:|---:|']
    for key,label in [('corpus_wer','spoken WER'),('exact_rate','整句 Exact')]:
        lines.append(f"| {label} | {pct(b['asr'][key])} | {pct(l['asr'][key])} |")
    for key,label in [('precision','实体 micro P'),('recall','实体 micro R'),('f1','实体 micro F1')]:
        lines.append(f"| {label}（全部 test） | {pct(b['all_test_rows']['micro'][key])} | {pct(l['all_test_rows']['micro'][key])} |")
    for key,label in [('empty_normalized','规范化空输出数'),('failed_rows','技术失败数')]:
        lines.append(f"| {label} | {b['asr'][key]} | {l['asr'][key]} |")
    lines += ['', '| 实体类型 | 参考数量 | 基模 P | 基模 R | 基模 F1 | LoRA P | LoRA R | LoRA F1 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for kind,label in scorer.KINDS.items():
        x,y=b['all_test_rows']['per_type'][kind],l['all_test_rows']['per_type'][kind]
        lines.append(f"| {label} | {x['support']} | {pct(x['precision'])} | {pct(x['recall'])} | {pct(x['f1'])} | {pct(y['precision'])} | {pct(y['recall'])} | {pct(y['f1'])} |")
    lines += ['', '## 规则范围与历史披露','',
        '- 使用冻结的原有实体规则，逐句按类型＋规范值集合匹配；不是人工 NER 金标准。主指标含参考未提取到实体句子中的 FP。',
        '- 仅参考实体阳性句子的兼容口径另存 final_test_comparison.json 和 entity_metrics.csv；零分母为 null。',
        '- 呼号仅覆盖已有 9 个前缀；规则覆盖、误标和参考读法限制与 dev 报告相同。',
        '- 历史作业 161294 在 2026-09-13 做过 test 前 100 条调试和完整 1,200 条 baseline 推理。本次复用完整结果，不重复运行基模。',
        '- 正式 LoRA 此次仅进行一次完整 test 推理；最终模型和规则在本次推理前冻结，test 不用于后续模型、阈值或规则选择。',
        '- 历史基模的清单、评估代码、版本、生成配置及预测结果指纹通过核验；历史记录没有基模权重内容哈希，不能追溯证明历史权重逐字节相同。当前权重哈希已记录。',
        '- 配置冻结时已知 dev 实体 F1 退化；按用户要求评估当前模型，结果不被筛选为仅展示收益。','',
        '## 运行资源','',
        '- LoRA 运行耗时、峰值显存及逐句计时见 runtime.json / per_row_timing.json。',
        '- 逐句计时含特征提取、生成、文本解码和置信度；不含音频读取解码，前 3 条只作预热并仍纳入质量评估。',
        '- RTF 分母为解码音频时长；沿用旧评估器的音频截断行为，不据此声称完整长音频处理效率。',
        '- 历史基模只有进程墙钟时间和峰值显存，未保存同口径逐句计时，不能报告严格的 baseline/LoRA 推理加速比。','',
        '## 成果位置','',f'`{out}`','',
        '- final_test_comparison.json：完整质量指标与历史披露。',
        '- lora_final_test_details.csv / lora_final_test_summary.json：本次逐条预测与原评估汇总。',
        '- test_comparison.csv：基模与 LoRA 逐条对照。',
        '- entity_metrics.csv / entity_rows.jsonl：两种口径分类指标及逐条实体。',
        '- frozen_plan.json / job_script.sbatch / runtime.json：配置与运行记录。','']
    (out/'FINAL_TEST_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    dump(out/'COMPLETE.json',{'status':'ok','job_id':os.environ.get('SLURM_JOB_ID'),'completed_at':datetime.now(timezone.utc).isoformat()})
    print('FINAL_TEST_COMPLETE '+str(out),flush=True)
    print(json.dumps({k:{'asr':v['asr'],'entities':v['all_test_rows']['micro']} for k,v in models.items()},indent=2),flush=True)


if __name__=='__main__':
    main()
