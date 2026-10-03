# 航空语音识别与统一文本恢复

这是一个围绕航空通话处理的科研项目作品集。项目把音频到规范文本的任务拆成两个阶段：

```text
航空录音 -> spoken-form 语音识别 -> canonical 规范文本恢复
```

作品集同时保留论文背景、集群复现材料和个人在实习子集上的两阶段实验结果。原始音频、完整数据集、共享基模和约 945 MB 的 Flan-T5 训练权重没有复制到本目录，复现时通过服务器原路径引用。

## 快速浏览

| 文件 | 内容 |
|---|---|
| `01_project_overview.md` | 研究问题、项目范围和成果摘要 |
| `02_method_and_pipeline.md` | 数据、两阶段方法、模型和评价协议 |
| `03_results.md` | 任务一、任务二的 dev/test 结果与解释 |
| `04_reproduction.md` | 集群路径、环境、复现步骤和作品集文件来源 |
| `05_limitations_and_next_steps.md` | 局限、可复核性边界和后续工作 |
| `reports/` | 用户提供的论文、创新点总结和实验报告 |
| `guides/` | 集群上的 `REPRODUCTION.md`、实习手册和数据子集说明 |
| `code/` | 从个人 `run/czm` 目录选取的训练、推理和评估代码 |
| `evidence/` | 结果表、配置、哈希、验证记录和错误分析 |
| `MANIFEST.json` | 本地文件、来源路径、大小和 SHA-256 |

## 核心结果

### 任务一：Whisper Decoder-only LoRA

- 数据：冻结的 12,000 条 train、1,200 条 dev、1,200 条 test 子集。
- 方法：冻结航空 Whisper 基模，仅训练 Decoder 注意力投影上的 rank-8 LoRA；个人正式实验未使用论文中的实体辅助损失。
- test spoken WER：`60.34% -> 50.14%`。
- test Exact：`22.75% -> 34.25%`。
- entity micro F1：`54.33% -> 46.52%`，说明整体 WER 改善不等于关键实体可靠性提高。

### 任务二：文本规范化

- 训练：`google/flan-t5-base`，1 epoch、1,500 步，输入 spoken-form，目标 canonical 文本。
- dev 依据预先冻结的主指标选择“任务一 ASR + legacy rules”。
- 主方案 test：canonical WER `54.73%`、Exact `33.92%`、entity F1 `48.93%`。
- T5 + gate test：canonical WER `52.08%`、Exact `33.08%`、entity F1 `49.12%`，作为固定对照保留，未按 test 重新选型。

## 研究边界

数据来自结构化航空英语课程录音和课程预期读法，不是实时空管无线电，也不是逐条人工听写金标准。实体指标是固定规则解析得到的结构诊断。任务二 test 曾发生超长输入恢复，相关失败、复用和分母处理均在 `evidence/task2/verification.json` 与报告中披露。

## 复现入口

先阅读 [`04_reproduction.md`](04_reproduction.md)，再查看 `guides/REPRODUCTION.md` 和 `guides/INTERN_ASSESSMENT_TASK.md`。代码中的模型、数据和归档路径指向集群共享目录；不要把大型数据和模型复制进作品集。
