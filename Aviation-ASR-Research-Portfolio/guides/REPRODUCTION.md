# 论文工作仓库说明与复现指南

本仓库对应论文 **Rule-Guided Weak Supervision for Entity-Aware Aviation Speech Recognition and Unified Text Restoration** 及其补充材料。仓库已经按论文最终实验协议整理：保留论文正文、补充材料、v3 数据审计、最终模型/配置、主表逐条结果、必要的基线代码和有解释价值的探索审计；删除未进入论文的中间 checkpoint、重复预测、失败尝试、日志和缓存。

面向实习生的小项目任务书见 [`INTERN_ASSESSMENT_TASK.md`](INTERN_ASSESSMENT_TASK.md)，冻结考核子集见 [`data_relationship_audit/intern_assessment_subset_20260911/`](data_relationship_audit/intern_assessment_subset_20260911/)。

## 1. 论文结果与仓库入口

| 论文内容 | 仓库入口 |
|---|---|
| 论文正文 | `Rule_Guided_Weak_Supervision_for_Entity_Aware_Aviation_Speech_Recognition_and_Unified_Text_Restoration.pdf` |
| 补充材料 | `MMAsia2026_Final_Supplement_20260815.pdf` |
| 最终 test 主表（4,487 条） | `atc_entity_pipeline_20260723/main_table_20260727/test/MAIN_TABLE_TEST.md` |
| 最终 dev 主表（5,922 条） | `atc_entity_pipeline_20260723/main_table_20260727/MAIN_TABLE_DEV.md` |
| 主表机器可读汇总 | `atc_entity_pipeline_20260723/main_table_20260727/test/main_table_test_summary.json` |
| 训练/评估主代码 | `atc_entity_pipeline_20260723/src_entity_aux/` |
| 受约束文本恢复 | `atc_entity_pipeline_20260723/src_entity_aux/unified_restoration_head.py` |
| Legacy aviation ITN | `atc_itn_v6/` |
| 数据与划分审计 | `data_relationship_audit/dataset_v3_audio_dedup_20260720/` |
| 规则弱标签 | `atc_entity_pipeline_20260723/weak_labels_v2_shared_rules/` |
| 融合/路由补充结果 | `atc_entity_pipeline_20260723/overnight_runs/posthoc_delta32_and_ensemble_test_20260812/` |

正文 Table 2 的最终 Auxiliary 行为 `entity_aux_lora_v1f_20260726` 的 primary checkpoint；consolidated/fusion 行及补充材料 Tables S1-S3 使用 `posthoc_delta32_and_ensemble_test_20260812`。不要把 post-hoc fusion 结果改写成 primary Auxiliary 的结果。

## 2. 目录结构

```text
.
├── atc_entity_pipeline_20260723/
│   ├── src_entity_aux/                 # 最终训练、推理、实体评估、恢复和主表脚本
│   ├── stage_*.sh                      # 可复用的 Slurm 阶段脚本
│   ├── main_table_20260727/            # 完整 dev/test 主表及逐条详情
│   ├── overnight_runs/                  # 论文采用的 run 与必要探索审计
│   ├── weak_labels_v2_shared_rules/    # train-only 弱标签及审计
│   └── README.md                        # pipeline 级技术说明
├── data_relationship_audit/             # v3 manifest、去重、泄漏与字段关系审计
├── atc_itn_v6/                          # 固定 aviation ITN 与评估器
├── atc_lora_private/                     # 旧版 LoRA manifest，用于 legacy overlap 审计
├── transcription_rule_extraction/       # 训练规则提取和规则证据
├── whisper_atc_baselines/               # Whisper/faster-whisper 基线脚本及结果
├── w2v2-air-traffic/                    # XLS-R 基线脚本及结果
├── recordingRecord_20251226_matching/   # 基线结果与课程文本的对齐表
├── original_text_restoration_metrics/   # 早期 restoration 基线审计
└── *.pdf                                # 论文和补充材料
```

原始音频、Whisper/XLS-R 基座模型和 Python 环境不随本目录分发。清理后的脚本仍使用可配置的绝对路径；运行前应修改脚本中的 `ROOT`、`MODEL`、`MANIFEST` 和 `PYTHON`，或建立与原工作区等价的路径。

## 3. 数据合同

权威数据为 `data_relationship_audit/dataset_v3_audio_dedup_20260720/` 下的 gzip manifest：

| split | 行数 | 用途 |
|---|---:|---|
| train | 48,098 | LoRA 训练与 train-only 规则弱标签 |
| dev | 5,922 | 配置选择、诊断和 restoration 分析 |
| test | 4,487 | 冻结正式评估 |

训练目标是 manifest 的 `transcription_n`（spoken-form）；canonical reference 仅用于恢复评估。弱标签只从 train reference 生成，dev/test reference 不参与规则、映射或模型选择。先阅读 `DATASET_V3_AUDIO_DEDUP_REPORT.md` 和 `manifest_summary.json`，确认音频、文本组和 split 没有跨集合泄漏。

## 4. 环境

推荐使用原工作区的 Python 3.10 GPU 环境（单张 A800，半精度）。核心依赖包括 PyTorch、Transformers、PEFT、torchaudio、datasets、jiwer、pandas、openpyxl 和 CUDA 音频解码工具。示例：

```bash
cd /data/home/scyb475/run/zz
PYTHON=/data/home/scyb475/run/zz/envs/whisperatc/bin/python
export PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1 TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$PWD/atc_entity_pipeline_20260723/src_entity_aux:${PYTHONPATH:-}"
"$PYTHON" -m pip install torch transformers peft torchaudio datasets jiwer pandas openpyxl
```

模型目录（示例）为 `/data/home/scyb475/run/model/WhisperATC/whisper-large-v3-atco2-asr`；基线模型和音频必须由使用者自行准备。训练配置：decoder-only rank-8 LoRA，作用于 `q_proj/k_proj/v_proj/out_proj`，learning rate `1e-4`，micro-batch `1`，gradient accumulation `8`，`6,013` optimizer steps，seed `20260725`，greedy decoding，English transcription prompt，最多 `128` 个新 token。Entity Weighting 使用实体 token 权重 `1.5`；Auxiliary 使用 `lambda_ent=0.2`、非实体权重 `0.25`。

## 5. 从头复现

### 5.1 生成 train-only 弱标签

```bash
cd /data/home/scyb475/run/zz/atc_entity_pipeline_20260723
python3 src_entity_aux/build_entity_weak_labels.py \
  --manifest ../data_relationship_audit/dataset_v3_audio_dedup_20260720/train_manifest.csv.gz \
  --output-dir weak_labels_v2_shared_rules
```

生成结果应包含约 48,098 条训练记录和 17,076 个 span；以 `weak_label_summary.json` 中的精确统计为准。

### 5.2 训练三个受控适配器

已有可审计的最终输入和输出位于：

```text
overnight_runs/rules_v3_natural_multiround_20260725_r2/        # native + weighted control
overnight_runs/entity_aux_lora_v1f_20260726/                    # Auxiliary（论文 primary）
```

若重新训练，使用对应的 `stage_*_full_train.sh`，并将脚本中的根目录、模型路径和 manifest 改为本机路径：

```bash
RUN_ID=rules_v3_natural_multiround_20260725_r2 \
  bash stage_entity_aux_full_train.sh
RUN_ID=entity_aux_lora_v1f_20260726 \
  bash stage_entity_aux_full_train.sh
```

训练后应检查 `full/models/*/*_summary.json`：`rows=48098`、`optimizer_steps=6013`、decoder-only LoRA、`unit_weight_loss_invariant=passed`。

### 5.3 评估 ASR、实体和恢复

评估阶段使用 `stage_entity_aux_full_eval.sh`；恢复阶段使用 `stage_entity_aux_full_restoration.sh`。通用 Python 入口分别是：

```bash
python3 src_entity_aux/eval_v3_entity_confidence.py ...
python3 src_entity_aux/compare_controlled_entity_runs.py ...
python3 src_entity_aux/evaluate_restoration_full_dev.py ...
```

Legacy ITN 由 `atc_itn_v6/cli.py` 调用；Unified/Schema-constrained restoration 使用 `src_entity_aux/unified_restoration_head.py`，并读取 `entity_aux_lora_v1f_20260726/inputs/restoration/train_restoration_config.json`。该配置中的 callsign 映射和规则均来自 train groups；不应用 test reference 重新生成。

### 5.4 生成主表

主表脚本会验证 split、行数、失败行和 `test_used` 标记：

```bash
python3 src_entity_aux/build_main_table_from_specs.py \
  --specs main_table_20260727/test/main_table_test_specs.json \
  --output-dir main_table_20260727/test
```

也可直接核对已保存的 `MAIN_TABLE_TEST.md`、`main_table_test_summary.json` 和 `FINAL_MAIN_TABLE_STATUS.json`。正式 test 结果必须保持 4,487 行；dev 必须保持 5,922 行。

## 6. 论文采用结果

最终 test 主表的关键数值如下（WER 为比例，Exact/F1 为百分比）：

| 系统 | ASR Exact | ASR WER | Entity F1 | Unified Exact | Unified WER |
|---|---:|---:|---:|---:|---:|
| Whisper ATCO2 domain base | 22.44 | 0.5679 | 52.43 | 32.85 | 0.5857 |
| + matched LoRA | 33.96 | 0.5593 | 67.11 | 33.36 | 0.6192 |
| + entity-token weighting | 34.28 | 0.5418 | 67.88 | 33.63 | 0.5971 |
| + entity-auxiliary LoRA | 33.56 | 0.5255 | 67.76 | 32.85 | 0.5857 |

补充材料中的 fusion（`0.68*Delta_0725 + 0.32*Delta_0820`）是后验探索结果：ASR WER `0.4980`、Entity F1 `65.29`，并在 S1-S3 中明确标为 post-hoc。

## 7. 保留的探索与审计

为便于复核研究决策，保留了 `lora_delta_mix_032_full_dev_20260812`、`posthoc_delta32_and_ensemble_test_20260812`、`frozen_fair_test_seed20260820_ckpt4800_20260812`、两个 `entity_aux_seed_repro_audit_*` 以及规则/错误分析报告。这些目录用于解释融合、seed 稳定性、解码公平性和实体类型误差，不应当作为新的 confirmatory 主表。

## 8. 清理记录

已删除：Python `__pycache__`/`.pyc`、Slurm stdout/stderr 与运行日志、ffmpeg 失败尝试、临时锁文件、未进入论文的 overnight 中间 run，以及仓库内无依赖的 SLAM-LLM/WhisperATC 外部源码副本。早期 `entity_aware_framework_20260721`、`private_atc_v2_asr_baseline` 和空的 `radiolingo_eval` 也已移除；它们的结论已由主表/审计结果覆盖。保留的 CSV/JSON 明细是论文主表、补充表或明确标注的审计输入；它们可以直接用于重新计算指标。
