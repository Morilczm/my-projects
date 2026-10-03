# 实习生考核冻结子集

本目录是基于论文 v3 数据集生成的考核专用子集。它不复制音频，manifest 中的 `archive_path` 和 `archive_member` 仍指向原始音频归档；使用前需要确认当前集群上的原始归档路径可访问。

## 文件

```text
train_manifest.csv.gz   12,000 条，用于训练
dev_manifest.csv.gz      1,200 条，用于调参和 checkpoint 选择
test_manifest.csv.gz     1,200 条，最终一次性评估
subset_summary.json      选择规则、行数、实体覆盖和文件哈希
```

生成脚本为上级目录的 `build_intern_assessment_subset.py`。重新生成时必须使用相同的脚本版本、源 v3 manifest 和默认参数；脚本使用固定版本字符串 `intern-assessment-v1-20260911` 和 SHA-256 稳定排序。

## 选择规则

- 来源为 `dataset_v3_audio_dedup_20260720` 的 v3 train/dev/test，源数据已完成跨 split 音频、文本和分组泄漏审计。
- 每个子集保持四类场景 `02/01`、`02/02`、`03`、`04` 的原始比例（按最大余数法取整）。
- 训练目标优先覆盖规则可识别的航空实体样本；`entity_positive` 只用于采样和分析，不是人工标注。
- 同一 `text_group_key` 按稳定哈希排序并设置较高上限，避免极少数重复文本占满子集，同时保留多说话人/多录音变体。
- test 子集只用于最终报告，不得用其 reference 选择模型、超参数、恢复规则或响应速度方案。

## 统计摘要

具体数字和文件 SHA-256 以 `subset_summary.json` 为准。当前冻结版本为：

| Split | 行数 | 规则实体样本 | 实体样本比例 | 场景计数 `02/01, 02/02, 03, 04` |
|---|---:|---:|---:|---|
| train | 12,000 | 3,510 | 29.25% | 3,732 / 79 / 6,573 / 1,616 |
| dev | 1,200 | 292 | 24.33% | 421 / 4 / 730 / 45 |
| test | 1,200 | 371 | 30.92% | 366 / 27 / 647 / 160 |

`02/01` 和 `02/02` 主要是词/短语类样本，规则实体覆盖很少；它们仍然保留，用于防止实习生只优化数字实体而忽略普通航空表达。

## 字段约定

- `transcription_n`：spoken-form ASR 目标，用于任务一。
- `excel_original_text`：canonical/reference 文本来源，用于任务二；评估时沿用仓库已有的规范化逻辑。
- `archive_path`、`archive_member`：音频归档位置和归档内成员。
- `subset_id`、`subset_name`：场景类型。
- `text_group_key`、`grouping_key`：重复控制和泄漏审计字段。
- `entity_positive`：由仓库规则解析器生成的采样辅助字段，不等同于人工 gold NER 标签。

