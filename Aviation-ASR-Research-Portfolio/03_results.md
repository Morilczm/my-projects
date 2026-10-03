# 实验结果

## 任务一：ASR

### 完整 dev

| 指标 | Baseline | Decoder LoRA |
|---|---:|---:|
| spoken WER | 47.29% | 43.29% |
| Exact | 21.67% | 29.00% |
| entity micro P | 95.97% | 56.18% |
| entity micro R | 66.30% | 67.13% |
| entity micro F1 | 78.42% | 61.17% |

### 最终 test

| 指标 | Baseline | Decoder LoRA |
|---|---:|---:|
| spoken WER | 60.34% | 50.14% |
| Exact | 22.75% | 34.25% |
| entity micro P | 96.30% | 50.61% |
| entity micro R | 37.84% | 43.04% |
| entity micro F1 | 54.33% | 46.52% |

解读：LoRA 显著降低普通词错误并提高整句 Exact，但预测了更多错误实体，尤其是呼号误报。航空场景不能只用整体 WER 判断是否更安全。

## 任务二：文本恢复

### dev 选择

在 task1 ASR 输入上，legacy rules 的 WER 为 46.67%，优于训练后 T5 raw 的 47.03% 和 guarded 的 47.97%，因此 test 前冻结主方案为“任务一 ASR + legacy rules”。

### 最终 test

| 输入 | 系统 | WER | Exact | entity F1 |
|---|---|---:|---:|---:|
| oracle spoken | trained T5 raw | 2.84% | 79.83% | 72.97% |
| oracle spoken | trained T5 + gate | 2.69% | 88.25% | 100.00% |
| oracle spoken | legacy rules | 3.20% | 90.83% | 100.00% |
| task1 ASR | trained T5 raw | 52.38% | 33.17% | 39.07% |
| task1 ASR | trained T5 + gate | 52.08% | 33.08% | 49.12% |
| task1 ASR | legacy rules | 54.73% | 33.92% | 48.93% |

解读：T5 在干净 spoken 输入上学会了很多格式转换，但在真实 ASR 噪声下会出现数值替换、实体删除和自由改写。gate 提高了实体保留，却不一定提高整句 Exact；主方案遵循 dev 规则冻结，而不是根据 test 指标重新选择。

## 结果可信度证据

- `evidence/task1/final_test_comparison.json`：任务一最终对照和历史使用披露。
- `evidence/task1/entity_metrics.csv`：实体类别计数及 P/R/F1。
- `evidence/task2/verification.json`：12 份预测各 1,200 行、独立词错误复算、哈希和异常恢复记录。
- `evidence/task2/test_metrics.csv`：任务二全部输入/系统组合。
- `evidence/task1/ERROR_ANALYSIS_10.md`、`evidence/task2/ERROR_ANALYSIS_20.md`：文本层错误案例。
