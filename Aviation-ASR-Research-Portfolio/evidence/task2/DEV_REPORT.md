# 任务二：完整一轮训练与 dev 结果

训练 12,000 条、1 epoch、1,500 步，完整 dev 每类输入 1,200 条。原始输出与检查后输出分开报告。未使用 test。

| 输入 | 系统 | WER % | Exact % | 实体 F1 % | 回退 % |
|---|---|---:|---:|---:|---:|
| oracle | pretrained_raw_model | 20.87 | 64.25 | 0.00 | 0.00 |
| oracle | pretrained_guarded_model | 6.58 | 86.50 | 97.01 | 31.42 |
| oracle | trained_raw_model | 3.75 | 83.67 | 76.88 | 0.00 |
| oracle | trained_guarded_model | 5.03 | 87.75 | 97.01 | 18.50 |
| oracle | copy | 21.53 | 64.75 | 0.00 | 0.00 |
| oracle | legacy_rules | 1.66 | 94.58 | 98.50 | 0.00 |
| oracle | conservative_rules | 5.04 | 87.75 | 97.01 | 0.00 |
| baseline_asr | pretrained_raw_model | 63.38 | 19.92 | 0.00 | 0.00 |
| baseline_asr | pretrained_guarded_model | 52.51 | 23.58 | 79.69 | 31.00 |
| baseline_asr | trained_raw_model | 49.13 | 23.00 | 50.60 | 0.00 |
| baseline_asr | trained_guarded_model | 50.64 | 23.58 | 79.69 | 26.83 |
| baseline_asr | copy | 64.05 | 20.08 | 0.00 | 0.00 |
| baseline_asr | legacy_rules | 51.36 | 23.58 | 80.21 | 0.00 |
| baseline_asr | conservative_rules | 50.64 | 23.58 | 79.69 | 0.00 |
| task1_asr | pretrained_raw_model | 64.09 | 23.75 | 0.00 | 0.00 |
| task1_asr | pretrained_guarded_model | 49.10 | 28.50 | 68.73 | 38.67 |
| task1_asr | trained_raw_model | 47.03 | 28.17 | 52.02 | 0.00 |
| task1_asr | trained_guarded_model | 47.97 | 28.58 | 68.73 | 15.25 |
| task1_asr | copy | 63.25 | 24.42 | 0.00 | 0.00 |
| task1_asr | legacy_rules | 46.67 | 29.08 | 68.62 | 0.00 |
| task1_asr | conservative_rules | 47.97 | 28.58 | 68.73 | 0.00 |

规则实体非人工 NER；复制 spoken 文本的 canonical 实体解析覆盖有限。相同输入和相同评分下比较模型增益，不将任务一 spoken F1 与本表直接相减。

checkpoint 尚未据完整 dev 复核选定为最终方案。本作业不执行 test 或自动训练更多 epoch。
