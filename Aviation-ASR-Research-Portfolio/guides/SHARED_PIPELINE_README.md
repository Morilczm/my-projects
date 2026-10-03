# ATC Entity Pipeline

这是论文工作的主 pipeline。仓库级安装、数据合同、复现步骤和清理记录见上级 [`REPRODUCTION.md`](../REPRODUCTION.md)；本文件只说明本目录内的代码和结果。

## 目录

```text
src_entity_aux/                  最终 entity-aware 训练、评估、恢复、主表代码
src/                             兼容/早期工具和单元测试
stage_*.sh                       Slurm 阶段脚本
main_table_20260727/             完整 dev/test 主表、逐条详情和状态文件
overnight_runs/                  论文采用 run 与必要的探索审计
weak_labels_v2_shared_rules/     train-only 弱标签及生成审计
clean_expanded_v3_20260727/      clean expanded manifest 记录
clean_expanded_v3_cap200_20260727/  cap=200 的数据构造记录
validation/                      保留的代码/协议审计快照
logs/                            已清理；新作业会在此生成 Slurm 输出
```

## 论文主链路

```text
dataset_v3 train manifest
  -> atc_entity_rules.py / build_entity_weak_labels.py
  -> matched LoRA / entity-token weighting / entity auxiliary LoRA
  -> eval_v3_entity_confidence.py
  -> atc_itn_v6（Legacy ITN）或 unified_restoration_head.py
  -> compare_controlled_entity_runs.py / build_main_table_from_specs.py
```

正式数据为 48,098 train、5,922 dev、4,487 test。训练时只使用 train 的 `transcription_n` 和由规则生成的弱标签；dev/test reference 仅用于冻结后的评估。

## 主要代码

| 文件 | 作用 |
|---|---|
| `src_entity_aux/atc_entity_rules.py` | 解析 runway、heading、callsign、frequency、flight level、数字和其他航空实体。 |
| `src_entity_aux/build_entity_weak_labels.py` | 从训练 manifest 生成带字符区间的 train-only JSONL/CSV 弱标签。 |
| `src_entity_aux/train_entity_weighted_lora.py` | native ASR 与实体 token weighting 的 decoder-only LoRA。 |
| `src_entity_aux/train_entity_aux_lora.py` | ASR loss 加 training-only entity auxiliary objective；推理不加载辅助头。 |
| `src_entity_aux/eval_v3_entity_confidence.py` | 生成逐条识别结果、审计字段和汇总指标。 |
| `src_entity_aux/compare_controlled_entity_runs.py` | 对齐 run 并计算 Exact、WER、Entity F1。 |
| `src_entity_aux/unified_restoration_head.py` | schema-constrained spoken-to-canonical restoration，歧义时保守回退。 |
| `src_entity_aux/evaluate_restoration_full_dev.py` | 评估 Legacy ITN 与 Unified restoration。 |
| `src_entity_aux/build_main_table_from_specs.py` | 检查 split/行数/provenance 并生成主表汇总。 |

## 结果入口

`main_table_20260727/test/` 是冻结 test 主表（4,487 行、9 个系统），`main_table_20260727/dev/` 是完整 dev 主表（5,922 行）。每个系统目录包含逐条 `*_details.csv` 和 `*_summary.json`；`restoration/` 下分别保存 Legacy (`v6`) 与 Unified (`r1`) 的结果。`FINAL_MAIN_TABLE_STATUS.json` 是 test 完整性标记。

`overnight_runs/entity_aux_lora_v1f_20260726/` 保存论文 primary Auxiliary 的 adapter、弱标签、训练配置和 dev restoration；`rules_v3_natural_multiround_20260725_r2/` 保存 native/weighted controls。`posthoc_delta32_and_ensemble_test_20260812/`、`lora_delta_mix_032_full_dev_20260812/`、`frozen_fair_test_seed20260820_ckpt4800_20260812/` 和两个 `entity_aux_seed_repro_audit_*` 目录只用于补充材料中的融合、seed、解码公平性和 test 审计。

不要将其他 seed sweep、failed decode 或历史 adapter 当作论文主结果；这些生成物已从整理后的仓库移除。

## 运行约定

阶段脚本中的路径默认指向原工作区。迁移到其他机器时，先修改 `PYTHON`、模型目录、manifest 目录和 `ROOT`，再按 `stage_prepare.sh`、训练、评估、恢复、主表的顺序运行。GPU 训练配置、超参数和验证命令见上级复现文档。
