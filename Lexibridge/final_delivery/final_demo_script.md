# Final Demo Script

## 一句话定位

LexiBridge AI 不是普通翻译网站，而是面向中外合作办学课程的 AI 双语课程知识对齐平台。它通过课程资料解析、证据检索、术语对齐、教师审核和学生反馈，把英文专业术语与中文课程知识建立可追溯的连接。

## 教师端演示

1. 登录教师账号。
2. 选择 demo 课程 `SP101 - Signal Processing Basics`。
3. 上传英文课程资料。
4. 上传中文参考资料。
5. 查看后台任务状态。
6. 触发 AlignmentRun。
7. 查看术语生成统计。
8. 打开 Quality Control。
9. 查看 Fourier Transform 术语卡。
10. 展示英文证据、中文证据、公式证据、score breakdown。
11. Approve 一张术语卡。
12. Mark needs more evidence 一张术语卡。

## 学生端演示

1. 登录学生账号。
2. 进入课程。
3. 搜索 Fourier Transform。
4. 查看傅里叶变换。
5. 查看证据来源和风险状态。
6. 收藏术语。
7. 标记掌握。
8. 提交反馈。
9. 上传个人资料。
10. 确认个人资料只对自己可见。

## 管理员端演示

1. 登录管理员账号。
2. 查看全局任务。
3. 查看 EvaluationRun。
4. 查看 AI Provider 状态。
5. 查看 KnowledgeBaseVersion。
6. 查看 Retrieval Experiment。
7. 查看 Pilot Report。
8. 查看 Production Readiness。

## 课程学习成果说明

项目从翻译网站转向知识对齐平台，体现了问题定义的深化。

Computational Thinking:

- Decomposition: OCR、retrieval、alignment、evaluation、feedback、deployment readiness。
- Abstraction: Document、KnowledgeChunk、TerminologyCard、EvaluationItem、BackgroundJob。
- Algorithmic Thinking: evidence score、confidence score、state machine、auto-approved gate、hard filter。
- Evaluation: smoke set、gold terms、retrieval regression、pilot feedback。
- Iteration: PR-1 到 PR-16 从功能 demo 迭代到交付包。

Design Thinking:

- Empathize: 学生术语理解困难，教师整理术语表成本高。
- Define: 问题不是翻译，而是课程知识对齐。
- Ideate: 教师端、学生端、知识库、AI 对齐、反馈闭环。
- Prototype: Local MVP 和 demo 数据。
- Test: Evaluation Harness、Demo Flow、PilotFeedback、Retrieval Experiment。
