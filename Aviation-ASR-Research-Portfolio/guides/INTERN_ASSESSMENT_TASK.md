# 航空语音识别与统一文本恢复实习生考核任务书

版本：`v1.0 / 2026-09-11`

## 1. 项目背景

本项目基于航空英语课程录音，目标是构建一个从语音到规范化文本的轻量系统。输入是航空通信录音，输出分为两个层次：

```text
语音 -> spoken-form 识别文本 -> canonical 恢复文本
```

spoken-form 保留口语表达，例如 `one one niner decimal seven`；canonical 文本将数字、呼号、跑道、频率等转换为任务要求的书面形式，例如 `119.7`。两者不能混为一个指标：任务一主要评价语音识别，任务二评价完整的语音到恢复文本链路。

本考核不要求复现论文中的 `large-v3 + entity auxiliary head` 全部细节。重点是：能否读懂数据合同，建立可靠 baseline，完成小规模领域适配，设计可控的文本恢复模块，并用正确的实验协议证明改进确实来自模型或方法。

## 2. 总体任务结构

| 阶段   | 内容                                                         | 是否必做 |
| ------ | ------------------------------------------------------------ | -------- |
| 入门   | 集群、仓库、数据、baseline 和评估流程                        | 必做     |
| 任务一 | 领域 ASR：输入语音，输出 spoken-form 文本                    | 必做     |
| 挑战一 | ASR 模型直接学习 canonical text restoration                  | 选做挑战 |
| 任务二 | ASR + 轻量文本模型，或 audio-text model，输出 canonical text | 必做     |
| 挑战二 | 在任务二结果不明显退化的情况下优化响应时间                   | 选做挑战 |

推荐的主路线是：

```text
jlvdoorn/whisper-large-v3-atco2-asr 或 Whisper-small.en
  -> LoRA 领域适配
  -> ASR spoken-form hypothesis
  -> Flan-T5-base / Qwen2.5-0.5B 的保守文本恢复
  -> 实体一致性检查与回退
```

如果资源有限，优先完成 `Whisper-small.en + LoRA` 和 `Flan-T5-base`；如果集群有 40GB 以上 GPU，可使用 `whisper-large-v3-atco2-asr + LoRA` 作为主实验。

## 3. 入门：熟悉集群和仓库

### 3.1 工作目录和重要文档

```bash
cd /data/home/scyb475/run/zz
```

首先阅读：

1. `REPRODUCTION.md`：论文工作整体结构、数据合同、模型和复现协议。
2. `atc_entity_pipeline_20260723/README.md`：训练、评估、恢复和主表脚本说明。
3. `Rule_Guided_Weak_Supervision_for_Entity_Aware_Aviation_Speech_Recognition_and_Unified_Text_Restoration.pdf`：方法、指标和最终实验。
4. `MMAsia2026_Final_Supplement_20260815.pdf`：超参数、弱标签、恢复诊断和实体类型分析。
5. `data_relationship_audit/intern_assessment_subset_20260911/README.md`：本次考核子集。
6. `atc_entity_pipeline_20260723/main_table_20260727/test/MAIN_TABLE_TEST.md`：论文主表的结果解释和数量级参考。

### 3.2 环境检查

推荐使用已有 Python 环境；若环境路径不同，只需替换 `PYTHON` 变量。

```bash
export PROJECT_ROOT=/data/home/scyb475/run/zz
export PYTHON=/data/home/scyb475/run/zz/envs/whisperatc/bin/python
export PYTHONPATH="$PROJECT_ROOT/atc_entity_pipeline_20260723/src_entity_aux:$PROJECT_ROOT/atc_entity_pipeline_20260723/src:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false

"$PYTHON" - <<'PY'
import torch, transformers, peft, pandas
print("torch", torch.__version__, "cuda", torch.cuda.is_available())
print("transformers", transformers.__version__)
print("peft", peft.__version__)
print("pandas", pandas.__version__)
PY
nvidia-smi
```

提交 GPU 作业前先执行：

```bash
bash atc_entity_pipeline_20260723/check_cluster_submit_quota.sh
squeue -u "$USER"
```

不要在登录节点进行完整音频解码、训练或大规模推理。小规模代码检查可以在登录节点完成，正式运行使用 Slurm GPU 节点。

### 3.3 检查本次子集

```bash
SUBSET=$PROJECT_ROOT/data_relationship_audit/intern_assessment_subset_20260911
zcat "$SUBSET/train_manifest.csv.gz" | head
cat "$SUBSET/subset_summary.json"
```

确认 `archive_path` 指向当前集群可访问的音频归档。如果路径发生变化，应在本地复制 manifest 后批量修正路径，不要改变 `sql_id`、`archive_member` 或文本字段。

### 3.4 跑通 baseline

baseline 入口是 `eval_v3_entity_confidence.py`。它会生成逐条 CSV 和汇总 JSON，包含 spoken reference、hypothesis、WER、Exact、空输出、失败行和置信度。

先做 100 条 smoke test：

```bash
MODEL=/data/home/scyb475/run/model/WhisperATC/whisper-large-v3-atco2-asr
OUT=$PROJECT_ROOT/intern_runs/baseline_smoke
mkdir -p "$OUT"

"$PYTHON" "$PROJECT_ROOT/atc_entity_pipeline_20260723/src_entity_aux/eval_v3_entity_confidence.py" \
  --manifest "$SUBSET/test_manifest.csv.gz" \
  --model "$MODEL" \
  --output-dir "$OUT" \
  --name whisper_atco2_baseline_smoke \
  --limit 100 \
  --max-new-tokens 128
```

然后对完整考核 test 子集运行同一模型。baseline 必须保存：模型路径、代码版本、命令、GPU 型号、解码参数、运行时间和失败行数。

baseline 的 spoken-form 参考为 `transcription_n`，不要用 `excel_original_text` 计算任务一 WER。

## 4. 本次考核数据集

### 4.1 数据规模

本次冻结子集位于：

```text
data_relationship_audit/intern_assessment_subset_20260911/
```

| Split |   行数 | 用途                               | 是否允许用于调参 |
| ----- | -----: | ---------------------------------- | ---------------- |
| train | 12,000 | ASR/恢复模型训练                   | 允许             |
| dev   |  1,200 | 超参数、checkpoint、规则和系统选择 | 允许             |
| test  |  1,200 | 最终一次性报告                     | 不允许           |

源数据来自论文使用的 v3 数据集：48,098 train、5,922 dev、4,487 test。考核子集只在各自源 split 内稳定抽样，不会把原始 train/dev/test 混合。

### 4.2 目标文本

任务一使用：

```text
audio -> transcription_n
```

这是 spoken-form 目标，例如口语数字、字母和单位仍以 spoken form 表示。

任务二使用：

```text
audio -> transcription_n -> canonical reference
```

canonical reference 来源于 `excel_original_text`，评估时应使用已有规范化/去占位符逻辑。数据中的 `(call sign)`、`(control unit)` 等课程占位符是元数据，不应被当作需要朗读的词。提交报告时必须明确说明自己的 canonical normalization 规则。

### 4.3 数据使用边界

- test reference 不能参与模型训练、prompt 构造、规则映射、阈值选择、checkpoint 选择或速度优化。
- 可以使用 train 的 spoken/canonical 配对训练恢复模型。
- 可以使用 dev reference 选择配置，但必须保留选择过程和候选结果。
- entity-positive 是规则生成的弱信号，不是独立人工标注；不能把 Entity F1 宣称为人工 NER F1。
- 不得通过随机切分原始音频重新制造 train/dev/test。

## 5. 任务一：领域 ASR

### 5.1 目标

输入录音，输出 spoken-form 识别文本。目标是相对于对应 baseline 降低 spoken WER，同时尽量提高航空实体的保留能力。

至少报告：

- corpus WER；
- normalized sentence exact match；
- entity-value micro Precision/Recall/F1；
- 呼号、跑道、航向、频率、距离、时间等实体的分类 F1；
- 空输出率、失败行数；
- 推理速度和峰值显存。

### 5.2 路线 A：领域 Whisper LoRA（推荐）

基础模型：

```text
/data/home/scyb475/run/model/WhisperATC/whisper-large-v3-atco2-asr
```

该模型在论文 test 上的 domain-base 结果为 WER `0.5679`、Entity F1 `52.43`，但它是大模型；考核时只训练 LoRA，不需要更新基础模型。

建议配置：

```text
LoRA rank: 8
LoRA alpha: 16
LoRA dropout: 0.05
target modules: decoder q_proj, k_proj, v_proj, out_proj
learning rate: 1e-4
micro-batch: 1
gradient accumulation: 8
fp16/bf16: enabled
max new tokens: 128
decoding: greedy
```

可以从 `stage_entity_aux_full_train.sh` 和 `src_entity_aux/train_entity_weighted_lora.py` 了解训练结构，但不要求实现 auxiliary head。实习生必须把脚本改为本次子集路径，并把训练配置写入 JSON。

### 5.3 路线 B：小模型领域适配（资源优先）

使用 `openai/whisper-small.en` 或 `openai/whisper-base.en`，通过 LoRA 或全量 decoder 微调。推荐先完成 `small.en + LoRA`：

- 约 2.4 亿参数，显存和训练时间显著低于 large-v3；
- Transformers/PEFT 支持成熟；
- 仍然保留 Whisper 的生成式解码能力；
- 容易进行 rank、prompt、采样策略和实体加权消融。

该路线不能直接与 domain-base 的绝对数值公平比较。报告应同时给出 zero-shot small、adapted small，并把 large ATCO2 作为外部参考或教师候选。

### 5.4 可选消融

任选一项即可：

1. rank 4 vs rank 8；
2. decoder-only vs encoder+decoder LoRA；
3. 无 prompt vs English transcription prompt；
4. 普通 token loss vs entity-token weighting；
5. 随机行采样 vs 按 `text_group_key` 控制重复；
6. greedy vs beam search。

实体 token weighting 的实现可以参考 `src_entity_aux/train_entity_weighted_lora.py`，但弱标签必须只从 train manifest 生成。

### 5.5 任务一验收

合格提交必须：

- 跑通 baseline 和至少一个领域适配模型；
- 在 dev 上报告训练前后对比；
- 在 test 上只进行一次最终评估；
- 保存 adapter、配置、训练日志摘要、逐条结果和汇总指标；
- 对至少 10 个错误进行分类分析。

不硬性规定必须达到论文 large-v3 数值。更重要的是结果可复现、指标计算正确、实体错误分析可信。

## 6. 挑战一：ASR 直接输出恢复文本

### 6.1 目标

训练 ASR 模型直接学习：

```text
audio -> canonical reference
```

这不是把 spoken-form 当作输出后再运行规则，而是让语音模型的 decoder 直接生成书面化文本。

### 6.2 路线

#### 路线 A：canonical-only 微调

将训练目标从 `transcription_n` 替换为规范化后的 `excel_original_text`，使用与任务一相同的语音模型和 LoRA 配置。必须同时保留 spoken-ASR 模型作为对照。

风险：模型可能直接丢失呼号、数字证据，或者把恢复规则和声学识别混为一体。需要报告 spoken WER 和 canonical WER，而不是只报告 canonical 指标。

#### 路线 B：多任务/提示词条件生成

使用不同 prompt 区分任务：

```text
transcribe spoken aviation:
restore aviation text:
```

同一模型交替学习 spoken target 和 canonical target。也可以采用先 spoken ASR、再 canonical continuation 的格式，但必须避免标签泄漏，并说明 decoder target 的拼接方式。

#### 路线 C：两阶段训练

先用 spoken target 完成任务一 LoRA，再用较小学习率和 canonical target 做第二阶段适配。该路线实现简单，但要监控灾难性遗忘。

### 6.3 挑战一验收

至少与以下系统比较：

1. spoken ASR + 规则恢复；
2. 直接 canonical ASR；
3. 任务一模型的 spoken 输出作为恢复模型输入。

必须报告：spoken WER、canonical WER、canonical Exact、实体一致性和内容删除/新增错误。若直接 canonical ASR 的 canonical WER 下降但呼号召回明显下降，应如实分析，而不是只展示单一最佳指标。

## 7. 任务二：完整文本恢复

### 7.1 推荐主路线：ASR + 轻量文本模型

系统结构：

```text
audio
  -> Whisper baseline 或任务一 ASR
  -> spoken hypothesis
  -> 轻量文本模型
  -> canonical candidate
  -> entity consistency gate / fallback
```

推荐模型顺序：

1. `google/flan-t5-base`：约 250M 参数，最适合作为必做模型；
2. `Qwen/Qwen2.5-0.5B-Instruct`：适合 LoRA/QLoRA，作为轻量 LLM 路线；
3. `Qwen2.5-1.5B-Instruct`：资源允许时的增强版本；
4. Qwen2-Audio 等 7B 级 audio-text model：只建议作为挑战路线，不作为必做依赖。

Flan-T5 是 text-to-text 模型，不是聊天式 LLM，但对“短文本规范化/编辑”比自由生成式聊天模型更容易控制。若选择 Qwen，必须限制输入输出长度、使用确定性解码，并处理模型可能输出解释文字的问题。

### 7.2 恢复训练数据

训练样本由同一行 manifest 构造：

```text
source = transcription_n
target = canonical_normalize(excel_original_text)
```

建议同时构造三种 dev 输入：

1. `oracle spoken`：直接输入 `transcription_n`，隔离恢复能力；
2. `baseline ASR`：输入未微调 ASR hypothesis；
3. `task1 ASR`：输入领域适配后的 hypothesis。

这三种输入必须分开报告，否则无法判断提升来自恢复模型还是 ASR。

### 7.3 推荐的保守恢复格式

不要一开始让 LLM 无约束重写整句。可以使用短指令：

```text
Convert the aviation spoken-form transcript to canonical written text.
Preserve unsupported words and do not invent entities.
Input: one one niner decimal seven
Output:
```

或训练结构化编辑：

```json
{"edits":[{"source":"one one niner decimal seven","target":"119.7","type":"frequency"}]}
```

程序验证编辑后再应用，不能直接信任模型输出。

### 7.4 必须实现的安全约束

至少实现以下三项：

- 不允许无证据新增数字、字母串、频率或呼号；
- 无法解析或规则冲突时复制输入片段，而不是强制转换；
- 输出为空、过长、包含解释文字或实体数量异常时回退到规则输出/原 hypothesis。

可以参考 `atc_entity_pipeline_20260723/src_entity_aux/unified_restoration_head.py` 和 `atc_itn_v6/normalizer.py`，但需要在报告中区分“已有规则代码复用”和“自己训练的模型能力”。

### 7.5 任务二评价

必须报告四个层级：

| 层级               | 输入 -> 输出                  | 作用                   |
| ------------------ | ----------------------------- | ---------------------- |
| ASR                | audio -> spoken reference     | 语音识别能力           |
| Oracle restoration | spoken reference -> canonical | 恢复模型上限           |
| Noisy restoration  | ASR hypothesis -> canonical   | 恢复模型抗识别错误能力 |
| End-to-end         | audio -> canonical            | 最终目标               |

核心指标：canonical corpus WER、canonical Exact、entity-value F1、实体删除率、实体错误新增率、规则回退率。

## 8. 挑战二：响应时间优化

只有在任务二结果稳定后进行。禁止用降低质量的方式换取一个没有基线的速度数字。

至少比较优化前后：

- 单条端到端 latency：p50、p95；
- Real-Time Factor；
- 吞吐量（条/秒）；
- 峰值 GPU 显存；
- canonical WER 和 Entity F1。

可选技术路线：

1. ASR 模型和文本模型只加载一次，避免每条音频重复初始化；
2. 音频批处理、动态 padding 和按时长分桶；
3. Whisper 使用 greedy decoding、`max_new_tokens=128`，避免无必要 beam；
4. fp16/bf16、8-bit optimizer 或 8-bit/4-bit 推理；
5. 文本恢复模型批量推理；
6. 对重复 spoken hypothesis 做缓存；
7. 规则可确定恢复的样本跳过 LLM；
8. 只有低置信度或实体冲突样本调用 LLM，形成级联系统。

每次优化都要用相同的 100～200 条固定 dev benchmark、相同 GPU 和预热策略。不能用 test 选择速度阈值。

## 9. 评分建议

总分 100 分，挑战部分可额外加 20 分。

| 项目                         | 分值 |
| ---------------------------- | ---: |
| 集群、仓库和数据理解         |   10 |
| baseline 正确运行与记录      |   15 |
| 任务一 ASR 适配              |   20 |
| 训练/评估可复现性            |   15 |
| spoken 与 canonical 指标实现 |   15 |
| 任务二恢复系统               |   15 |
| 错误分析和工程文档           |   10 |
| 挑战一：ASR 直出恢复         |  +10 |
| 挑战二：响应时间优化         |  +10 |

评分不以“是否超过论文 large-v3”作为主要标准。小模型若能在资源受限条件下稳定改善 baseline、保持实体、给出可信的误差解释，应得到高评价。

## 10. 最终交付物

有完整的、可复现的记录即可，下面列表不严格要求。

提交一个独立目录或 Git 分支，至少包含：

```text
README.md
requirements.txt 或 environment.yml
configs/
src/train_asr.py
src/infer_asr.py
src/train_restoration.py
src/infer_pipeline.py
src/evaluate.py
scripts/run_baseline.sh
scripts/run_train.sh
scripts/run_eval.sh
results/dev_summary.json
results/test_summary.json
results/error_analysis.md
report.md
```

模型权重只需提交 LoRA adapter 或轻量恢复模型 adapter，不提交基础模型和音频。每个结果必须记录：命令、配置、代码 commit/hash、数据 manifest SHA-256、随机种子、GPU、运行时间、显存和是否使用 test。

## 11. 最低合格标准

1. 能在本次冻结子集上独立跑通 baseline。
2. 至少完成一个可复现的 ASR 领域适配实验。
3. 正确区分 spoken WER 和 canonical WER。
4. 任务二至少完成 oracle restoration 和 end-to-end restoration 两种评估。
5. 不使用 test reference 进行选择。
6. 提交结果可以由另一条命令重新计算。
7. 能解释至少 30 个错误案例，覆盖普通词、数字/实体、ASR 错误和恢复错误。
