# LexiBridge AI / 智桥术语云最终项目摘要

LexiBridge AI / 智桥术语云的最终定位是一个 AI 双语课程知识对齐平台，服务于中外合作办学场景中的英文专业课程学习。项目的原始问题来自学生阅读英文课件、英文教材时对专业术语理解不稳定：学生既需要知道英文术语的中文表达，也需要知道这个表达是否符合课程语境、是否有中英文证据、是否经过教师审核。

项目早期更接近一个 AI 翻译网站，重点是把英文术语翻译成中文。但在期中展示和后续课程学习之后，我们重新定义了问题：真正困难不是“某个词怎么翻译”，而是“英文课程语境中的专业概念如何与中文教材、中文课程知识和学生已有认知对齐”。因此项目方向从翻译工具转向知识对齐平台。这个转变也决定了后续系统不再只追求生成答案，而是强调证据检索、状态机、风险提示、教师审核和评估回归。

项目的目标用户包括英方/中方教师、中外合作办学学生和系统管理员。教师端负责创建课程、上传英文课程资料和中文参考资料、查看后台任务、触发术语对齐、处理 Quality Control、处理学生反馈并导出课程术语表。学生端负责搜索课程术语、查看中文解释和证据来源、收藏术语、标记掌握、提交反馈，以及上传个人资料用于个人知识库。管理员端负责查看用户、课程、任务、日志、EvaluationRun、AI Provider、KnowledgeBaseVersion、Retrieval Experiment 和 Production Readiness。

系统核心流程是：课程资料上传后进入后台任务，完成解析、OCR 和 FormulaBlock 识别；文档内容进入课程知识库并形成 KnowledgeChunk；检索模块根据课程、语言、scope、owner、source authorization 等 hard filter 查找中英文证据；alignment 模块生成 TerminologyCard，并写入 alignment_status、confidence_score、evidence snapshot、quality flags 和 risk_note；教师在 QC 页面审核高风险或证据不足卡片；学生使用术语卡并提交反馈；反馈可以进入 QC、EvaluationItem 或 IterationBacklog，形成持续迭代闭环。

技术架构上，项目包括 Flask 后端、原生前端、SQLite 本地数据库、StorageService、本地异步任务队列、OCR/FormulaBlock 管线、Evidence Retrieval、AlignmentRun、Evaluation Harness、AI Provider Governance、KnowledgeBaseVersion、RetrievalBackend 抽象和 PilotFeedback。项目还建立了 OpenAPI 契约、安全隐私测试、文件上传安全测试、个人知识库隔离测试、迁移脚本、release package 检查、备份恢复、成本控制和生产风险边界。

当前能力已经覆盖 local demo 和小范围试点准备：可以运行 demo 数据、生成术语卡、展示证据与风险、执行教师 QC、支持学生反馈、运行 Evaluation、生成 pilot report，并提供教师/学生/管理员手册。当前限制也必须明确：系统仍是 local pilot-ready，不是 production-ready；SQLite、本地文件存储、本地 worker、mock payment、mock email 和本地 provider 都不能作为生产能力；真实课程资料需要教师确认授权；术语输出仍需结合 evidence、risk_note 和教师审核状态使用。

下一步计划包括：先选择一门真实课程进行小范围试点，收集教师授权资料和学生反馈；随后升级 PostgreSQL、对象存储和生产队列；再接入真实 embedding provider、向量数据库和 reranker；最后完善账号体系、邮件、隐私协议、监控告警和更大规模的课程 gold set。
