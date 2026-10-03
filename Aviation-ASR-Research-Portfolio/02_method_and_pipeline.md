# 方法与流水线

## 数据与路径

服务器上的实习子集：

```text
/data/home/scyb475/run/zz/data_relationship_audit/intern_assessment_subset_20260911
```

| 划分 | 数量 | 用途 |
|---|---:|---|
| train | 12,000 | ASR LoRA 和文本恢复训练 |
| dev | 1,200 | 模型、规则和 gate 选择 |
| test | 1,200 | 冻结方案后的最终评估 |

共享基模：

```text
/data/home/scyb475/run/model/WhisperATC/whisper-large-v3-atco2-asr
```

个人目录：

```text
/data/home/scyb475/run/czm
```

## 阶段 A：spoken-form ASR

目标是从音频生成课程预期的 spoken-form 转写 `transcription_n`。正式 LoRA 配置为：

| 参数 | 设置 |
|---|---|
| 基模 | `whisper-large-v3-atco2-asr` |
| LoRA 位置 | Decoder self/cross attention 的 `q/k/v/out_proj` |
| rank / alpha / dropout | `8 / 16 / 0.05` |
| 学习率 | `1e-4` |
| micro-batch / 梯度累积 | `1 / 8` |
| 训练轮数 | 1，12,000 条，1,500 steps |
| 精度 | fp16 |
| 解码 | greedy，`max_new_tokens=128` |

LoRA adapter 位于服务器：

```text
/data/home/scyb475/run/czm/adapters/train_full_163783
```

训练侧规则生成了弱实体标签，但个人任务一正式训练仅使用 Whisper 原生 ASR 损失，未加入论文中的实体辅助分类头或实体加权损失。弱标签主要用于数据检查，冻结实体规则用于评估诊断；推理时仍输出普通 spoken-form 文本。

## 阶段 B：canonical 文本恢复

输入条件分为：

1. oracle spoken：直接使用参考 spoken-form，隔离恢复模型能力；
2. baseline ASR：使用未适配 Whisper 的输出；
3. task1 ASR：使用 LoRA Whisper 的输出，观察串联噪声。

恢复系统比较：

- 训练后的 Flan-T5 raw 输出；
- T5 输出经过实体一致性检查和规则回退的 guarded 输出；
- 已有 legacy rules；
- conservative rules 对照。

gate 要求候选输出的结构和实体集合满足约束，否则回退到保守规则。它能减少删除和不受控改写，但不能从 ASR 输入中恢复已经丢失或错误的声学证据。

## 评价层次

```text
ASR:                audio -> spoken reference
Oracle restoration: spoken reference -> canonical reference
Noisy restoration:  ASR hypothesis -> canonical reference
End-to-end:         audio -> canonical reference
```

评价包括 corpus WER、规范化句子 Exact、规则解析的 entity-value micro P/R/F1，以及实体删除、新增、回退率。实体分数是固定规则的结构诊断，不等同于人工 NER 金标准。
