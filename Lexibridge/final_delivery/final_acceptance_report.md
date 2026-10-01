# LexiBridge AI Final Acceptance Report

## 1. 项目基本信息

LexiBridge AI / 智桥术语云，是面向中外合作办学课程的 AI 双语课程知识对齐平台。

## 2. 当前版本定位

当前版本可以定义为 local pilot-ready / course demonstration-ready，但不能定义为 production-ready。

## 3. 核心功能验收

已具备多格式资料解析、OCR、FormulaBlock、Evidence Retrieval、AlignmentRun、TerminologyCard、EvaluationRun、BackgroundJob、PilotFeedback、KnowledgeBaseVersion、AI Provider Governance 和 RetrievalBackend 抽象。

## 4. 教师端验收

教师可创建或选择课程、上传英文/中文资料、查看任务状态、触发 AlignmentRun、处理 Quality Control、查看学生反馈、导出课程术语表。

## 5. 学生端验收

学生可选择课程、搜索术语、查看证据和风险状态、收藏、标记掌握、提交反馈、上传个人资料并查看个人任务。

## 6. 管理端验收

管理员可查看用户、课程、全局任务、EvaluationRun、AI Provider、KnowledgeBaseVersion、Retrieval Experiment、日志、用量、Pilot Report 和 Production Readiness。

## 7. OCR / Formula OCR 验收

系统支持 OCR 状态记录、低置信风险标记和 FormulaBlock。无真实 Formula OCR provider 时不伪造 LaTeX，而是保留缺失风险状态。

## 8. Evidence Retrieval 验收

检索保留 hard filter、scope filter、permission filter、source governance，并支持 lexical、vector-ready、hybrid 和 reranker-ready 架构。

## 9. Alignment / QC 验收

AI 输出不能绕过 evidence gate。弱证据、缺证据、domain mismatch、OCR 低置信和 formula evidence missing 会进入 QC 或 needs_more_evidence。

## 10. Evaluation Harness 验收

EvaluationSet、EvaluationItem、EvaluationRun 可运行 smoke evaluation，并记录 extraction、evidence、alignment、false positive 和 no-evidence forced alignment 指标。

## 11. 异步任务验收

长任务进入 BackgroundJob，记录 queued、running、completed、failed、canceled、progress、event history、retry 和 cancel。

## 12. 安全与权限验收

测试覆盖认证、角色权限、文件上传安全、个人知识库隔离、release 包敏感文件检查和日志脱敏。

## 13. Demo 数据与试点包验收

Demo 数据覆盖 DS101、SP101、MATH101。Pilot Package 提供 runbook、教师/学生/管理员手册、授权说明、隐私风险提示、指标和试点报告模板。

## 14. 测试命令与结果

最终测试结果记录在 `final_test_report.md` 与 `docs/demo-test-report.md`。最新 full pytest 结果为 160 passed, 6 warnings；release package 测试为 116 passed, 1 warning。

## 15. 当前限制

当前仍使用 SQLite、本地文件存储、本地 worker、mock payment、mock email。没有真实 API key 时 AI 只能使用 none/mock/local。真实生产部署仍需 PostgreSQL、对象存储、生产队列、真实邮件服务、正式隐私协议、真实课程授权和持续监控。

## 16. 结论

当前版本可以定义为 local pilot-ready / course demonstration-ready，但不能定义为 production-ready。项目已经具备完整本地演示、试点准备和核心工程闭环，但真实生产部署仍需 PostgreSQL、对象存储、生产队列、真实邮件服务、正式隐私协议、真实课程授权和持续监控。
