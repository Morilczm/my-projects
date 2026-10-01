# Final Course Report Materials

## 项目背景

中外合作办学学生经常同时面对英文课件、英文教材和中文专业知识。困难不只是把一个英文单词翻译成中文，而是判断该英文术语在课程语境中对应哪个中文专业概念、证据是否可靠、是否与教师课堂讲解一致。

## 问题重新定义

项目早期更接近一个 AI 翻译网站，但在期中展示和课程学习之后，我们意识到真正的问题不是“单个英文词怎么翻译”，而是“英文课程语境中的专业概念如何与中文教材、中文课程知识和学生已有认知对齐”。因此项目方向从翻译工具转向知识对齐平台。

In short, the project evolved from translation to knowledge alignment.

## Computational Thinking 体现

### Decomposition

系统被拆成文档解析、OCR、Formula OCR、KnowledgeChunk、Evidence Retrieval、Alignment、Evaluation、Feedback Loop、Deployment Readiness。

### Abstraction

核心抽象包括 Document、DocumentChunk、FormulaBlock、KnowledgeBaseVersion、KnowledgeChunk、TerminologyCard、EvaluationItem、BackgroundJob。术语卡不是翻译字符串，而是带证据、状态、置信度、风险标签和审核历史的结构化对象。

### Algorithmic Thinking

系统使用 evidence_score、confidence_score、auto-approved gate、state machine、retrieval hard filter、hybrid score fusion。AI 输出只是输入之一，最终状态由规则、证据和风险门禁决定。

### Evaluation

项目引入 smoke set、gold terms、no_evidence_forced_alignment_rate、retrieval regression、pilot feedback。评估不是 AI 自评，而是固定样例和负例检验。

### Iteration

PR-1 到 PR-16 展示了从 OCR 修复、检索重构、状态机、Evaluation、安全、异步任务、工作流、demo、部署准备、反馈闭环、知识库版本化、RAG 接口，到最终交付包的迭代路线。

## Design Thinking 体现

### Empathize

学生看不懂英文术语，教师整理术语表成本高，通用 AI 缺少课程证据。

### Define

问题不是翻译，而是课程知识对齐。

### Ideate

设计教师端、学生端、知识库、AI 对齐、反馈闭环。

### Prototype

构建 Local MVP、Demo 数据和三角色工作台。

### Test

通过 Evaluation Harness、Demo Flow、PilotFeedback、Retrieval Experiment 检验系统。

## 项目成熟之处

项目从功能堆叠变为系统闭环；从“AI 生成答案”变为“证据约束 + 人工审核 + 评估回归”；从“展示型 demo”变为“local pilot-ready”；从“单次开发”变为“持续反馈迭代”。
