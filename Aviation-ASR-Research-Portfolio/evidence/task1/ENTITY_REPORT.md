# 任务一：完整 dev 实体指标对照

生成时间（UTC）：2026-09-21T13:37:29.281101+00:00。相同的 1200 条 dev；未使用 test。

## 统计口径

- 复用仓库原有 atc_entity_rules.py，不修改规则。参考来自原始 transcription_n，预测来自已有 hypothesis。
- 逐句以（实体类型，规则规范值）精确匹配；同一句内相同实体值去重，不跨句匹配，不评价 span 边界。
- 主指标包含全部 1,200 条：参考没有提取到实体的句子中，预测新增的实体也计 FP。
- 另报“参考实体阳性子集”，对应仓库论文主表的统计范围；两个范围不可混用。
- 错值同时计一个 FP 和一个 FN；F1=2TP/(2TP+FP+FN)。分母为零记 null/—，有错误但 TP=0 时 F1=0。
- Support 是逐句去重后参考实体值总数；表中的 P/R/F1 单位为 %。

## 主结果：全部 dev

| 模型 | TP | FP | FN | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 238 | 10 | 121 | 359 | 95.97 | 66.30 | 78.42 |
| 正式 LoRA | 241 | 188 | 118 | 359 | 56.18 | 67.13 | 61.17 |

参考可提取到实体的句子：292；参考未提取到实体的句子：908。
后一组中预测新增实体值：Baseline 3，LoRA 122（并非人工确认的幻觉数量）。

| 实体类型 | Support | 基模 P | 基模 R | 基模 F1 | LoRA P | LoRA R | LoRA F1 | ΔF1（百分点） |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 呼号 (callsign) | 34 | 81.82 | 26.47 | 40.00 | 7.91 | 41.18 | 13.27 | -26.73 |
| 跑道 (runway) | 83 | 95.08 | 69.88 | 80.56 | 87.88 | 69.88 | 77.85 | -2.70 |
| 航向 (heading) | 76 | 98.18 | 71.05 | 82.44 | 100.00 | 78.95 | 88.24 | 5.79 |
| 频率 (frequency) | 1 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 0.00 |
| 距离 (distance) | 60 | 90.32 | 46.67 | 61.54 | 65.79 | 41.67 | 51.02 | -10.52 |
| 时间 (time) | 26 | 100.00 | 84.62 | 91.67 | 100.00 | 65.38 | 79.07 | -12.60 |
| 飞行高度层 (flight_level) | 18 | 100.00 | 33.33 | 50.00 | 81.82 | 50.00 | 62.07 | 12.07 |
| 高度（米） (altitude_m) | 0 | — | — | — | 0.00 | — | 0.00 | — |
| 高度（英尺） (altitude_ft) | 0 | — | — | — | — | — | — | — |
| 速度 (speed) | 52 | 98.08 | 98.08 | 98.08 | 98.00 | 94.23 | 96.08 | -2.00 |
| QNH (qnh) | 9 | 100.00 | 100.00 | 100.00 | 100.00 | 88.89 | 94.12 | -5.88 |
| 机上人数 (pob) | 0 | — | — | — | — | — | — | — |
| 应答机编码 (squawk) | 0 | — | — | — | — | — | — | — |

## 仓库兼容范围：仅参考实体阳性句子

| 模型 | 句子数 | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 292 | 238 | 7 | 121 | 97.14 | 66.30 | 78.81 |
| lora | 292 | 241 | 66 | 118 | 78.50 | 67.13 | 72.37 |

## 范围与限制

- 这是基于规则参考的 entity-value 指标，不是人工 NER 金标准，不直接等于音频中所有实体的识别准确率。
- 呼号仅覆盖规则现有的 9 个 spoken airline 前缀：air cruiser, blue nova, chase air, china star, exo, kingfisher, orbit air, ornate, zenith。
- 规则对关键词、数字读法和单位有要求；例如时间只匹配四位数字加 UTC。未提取到实体不等于文本中确实没有实体。
- 既有规则可能有边界、漏检及规范值不一致问题；本轮冻结规则，不为提高分数修改它。人工复核候选另存。
- Support 很小或为零的类别只作描述，不能据此得出稳定提升或下降结论。
- 没有重新解码音频；下列错误候选仅是文本层面的诊断，尚未完成听音核验。

## 文件

- entity_comparison.json：两种范围、两模型的全部计数和指标。
- entity_metrics.csv：可直接制表的分类结果（指标存 0–1 比率）。
- entity_rows.jsonl：全部 1,200 条的参考/预测实体 span、TP/FP/FN，便于核验。
- entity_changes.csv：实体有误或模型之间实体预测变化的句子，包含改进与退化候选。
- protocol.json、inputs.sha256、冻结的规则与脚本：复现依据。
- command.txt：使用同一输入重新计算的命令；重跑需换一个空输出目录。

服务器结果目录：`/data/home/scyb475/run/czm/results/entity_dev_full_167720_v1`

## 可复算命令

```bash
/usr/bin/python3 /data/home/scyb475/run/czm/scripts/evaluate_task1_entities_v1.py --manifest /data/home/scyb475/run/zz/data_relationship_audit/intern_assessment_subset_20260911/dev_manifest.csv.gz --baseline /data/home/scyb475/run/czm/results/baseline_dev_full_162200/baseline_dev_full_details.csv --lora /data/home/scyb475/run/czm/results/eval_train_full_167720/lora_full_dev_details.csv --rules /data/home/scyb475/run/zz/atc_entity_pipeline_20260723/src_entity_aux/atc_entity_rules.py --expected-rules-sha256 a73e9b901987665193a89fda4bce8a1a0bf83fe5a63777a01fe6fd9569997705 --output /data/home/scyb475/run/czm/results/entity_dev_full_167720_v1
```

## 补充核验与发现

- 已与仓库原函数交叉核验：两个模型、两个统计范围的 TP/FP/FN 及定义有效的 P/R/F1 一致，见 validation.json。
- 发现 159 条 EXO321 误报候选；原基模 67 条规范化空输出中 57 条出现此现象，整句正确 0 条。
- 初步文本诊断和 12 个复核候选见 DIAGNOSTICS.md；尚未听音，不将其称为已核验的声学错误。

## 一条命令重新计算

在服务器终端执行（文本统计，无 GPU）：

```bash
bash /data/home/scyb475/run/czm/scripts/run_task1_entity_eval_v1.sh
```

每次生成新的时间戳目录。模型、音频和清单继续复用共享路径；本轮未读取 test。
