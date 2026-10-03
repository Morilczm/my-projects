# 复现与文件来源

## 服务器连接

用户提供的 SSH 入口为端口 `2222` 的 Paracloud 集群。密码没有写入本作品集。服务器所有个人写操作应限制在：

```text
/data/home/scyb475/run/czm
```

共享复现仓库位于：

```text
/data/home/scyb475/run/zz
```

## 推荐阅读顺序

1. `guides/REPRODUCTION.md`：完整仓库结构、数据约定、原始大规模实验和论文结果。
2. `guides/INTERN_ASSESSMENT_TASK.md`：实习子集、验收要求和推荐路线。
3. `02_method_and_pipeline.md`：本作品集使用的两阶段实现。
4. `03_results.md`：冻结方案后的结果。
5. `evidence/task1/` 和 `evidence/task2/`：逐项配置、结果与审计文件。

## 环境

任务一复用共享 Python 3.10 环境，最终记录见 `evidence/task1/environment.json`。任务二环境记录为：

```text
torch 2.3.1+cu121
transformers 4.35.2
numpy 2.2.6
sentencepiece 0.2.1
safetensors 0.7.0
GPU NVIDIA A800-SXM4-80GB
CUDA 12.1
```

## 复现原则

- 先做 100 条 smoke test，再提交 Slurm GPU 作业。
- 训练、评估和恢复都写入 `run/czm` 下的新目录，不覆盖共享基模。
- 通过 manifest 的 `archive_path` 和 `archive_member` 读取共享音频，不复制音频归档。
- 通过绝对路径指向共享模型，不在本地或个人目录重复保存模型。
- train-only 弱标签只能由训练参考生成，不能使用 dev/test reference 选择规则或映射。
- test 前冻结模型、规则、gate 和解码配置；test 结果只做报告，不反向调参。

## 本地作品集的下载范围

已下载：论文补充材料、复现/实习手册、训练和评估源码、配置、汇总指标、逐条结果摘要、错误分析和哈希验证文件。

未下载：原始音频、完整数据集、Whisper 基模、Flan-T5 权重、优化器状态和大型中间运行目录。这样既保持作品集轻量，也避免在共享服务器上产生重复副本。

## 服务器来源映射

完整映射和 SHA-256 见 [`MANIFEST.json`](MANIFEST.json)。主要来源为：

```text
/data/home/scyb475/run/zz/REPRODUCTION.md
/data/home/scyb475/run/zz/INTERN_ASSESSMENT_TASK.md
/data/home/scyb475/run/czm/submit_task1
/data/home/scyb475/run/czm/submit_task2
```
