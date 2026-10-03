# 任务二交付目录

训练、完整 dev、最终 test 及技术恢复均已完成。本目录只整理既有结果，没有重新训练或运行 test。

## 阅读顺序

1. reports/任务二_最终实验总结报告.md：最终报告。
2. results/dev/DEV_REPORT.md 与 results/test/FINAL_TEST_REPORT.md：完整对照。
3. reports/ERROR_ANALYSIS_20.md：20个任务二dev案例，未听音。
4. reports/verification.json、submission_provenance.json：核验范围与来源。

## 目录

- reports/：最终总结、错误案例、指标CSV和本地独立复算证据。
- code/train_dev/：训练和完整dev代码快照。
- code/test_original/：169151原始冻结test代码。
- code/test_recovery/：169202恢复代码；技术异常处理变更明确披露。
- model/task2_flan_t5_epoch1/：实际训练后一轮的完整Flan-T5权重及tokenizer，可用from_pretrained本地加载。这是全参数微调模型，不是LoRA adapter。
- configs/：训练配置、冻结计划、映射和基础模型身份。
- data/：train/dev文本配对、test manifest及保存的ASR预测；不包含音频文件本体。
- training/：1500步loss/梯度、训练行顺序、长度与重载证据。
- results/dev/：训练前后3类输入的12份逐条预测及指标。
- results/test/：三类输入四种系统的12份最终预测及指标。
- logs/、evidence/：作业日志、CUDA诊断、marker和Slurm历史查询。
- environment.json：实际训练环境版本。没有升级共享环境。

## 结果与协议限制

主系统在dev上固定为任务一ASR＋legacy rules。test的主系统WER为54.73%，Exact33.92%，实体F1 48.93%；T5＋gate为52.08%、33.08%、49.12%。不根据test重新选择主系统。

169151的oracle输出原样复用；169202仅完成尚未生成的两类ASR输入。Baseline第526条超256-token限制，raw记失败空预测、guarded使用原规则回退，保留在全部分母。报告承认这是test期间的技术协议补充，不声称原协议一次无故障完成。

## 不重新推理的复算

在本目录执行（Python标准库即可）：

```bash
python3 recompute_metrics.py
sha256sum -c SHA256SUMS
```

复算入口不加载模型、不生成预测、不更改已有文件，核对全部dev/test逐条计数与保存指标。已冻结评分代码包含在目录中。

如需完整训练复现，可参考code/train_dev/README.md及训练配置。原Slurm脚本保留实验绝对路径，以便追溯；迁移环境时需改路径并新建实验目录，不能直接把这些脚本理解成可在任意位置一键重跑。最终test不得因整理或验收重复执行。

未重复包含基础模型和音频，亦未复制约2GB优化器状态；需继续研究的训练状态仍位于submission_provenance.json记录的原路径。本交付包含训练后模型，足以加载并检查该恢复模型。
