# Frontend Workflow Design

LexiBridge AI 当前前端仍是原生 `frontend/index.html` 单页应用。PR-7 的目标不是切换框架，而是把功能堆叠整理成角色工作台，让课程 Demo 能按真实工作流演示。

## Top Status Bar

登录后顶部状态栏显示：

- 当前用户 / User
- 当前角色 / Role
- 当前课程 / Current Course
- AI Provider 状态 / AI Provider Status
- OCR Provider 状态 / OCR Provider Status
- Formula OCR Provider 状态 / Formula OCR Provider Status
- 后台任务数量 / Background Job Count
- 当前套餐与剩余额度 / Plan and Remaining Quota

Mock/local AI 会显示为演示或本地启发式状态，不能被视觉上包装成 live AI。

## Diagnostics

登录后的通用导航包含 Diagnostics 页面，用于课程演示和排查：

- AI Provider：显示 provider、model、prompt version、retrieval version，以及 live/mock/local 状态。
- OCR Provider：显示普通文字 OCR provider、语言配置和置信度阈值。
- Formula OCR：显示公式 OCR provider 和阈值。未配置时明确提示只标记公式区域，不伪造 LaTeX。
- Background Jobs：显示 queued/running/failed 数量并跳转到 Job Status。
- OpenAPI：提示前端核心 API 调用需要同步到 `docs/openapi.yaml`。
- Current Limits：明确当前仍是 Local MVP，没有真实支付、真实 SMTP、生产向量数据库或云部署。

## Student Workflow

学生默认进入 Student Workspace：

1. 选择已加入课程。
2. 进入 Terminology Search 检索课程术语。
3. 查看 TerminologyCard 的英文证据、中文证据、置信度、状态、risk note 和 provider。
4. 收藏术语、标记已掌握、提交反馈。
5. 在 Personal Upload 上传个人资料。
6. 在 Job Status 查看个人文档解析任务。
7. 在 Subscription & Usage 查看套餐、剩余额度和 mock payment。
8. Basic / Pro 用户可以按当前课程或筛选结果导出 PDF 复习资料。

个人资料页面明确提示：个人资料只对当前学生可见，不进入课程公共知识库。

## Teacher Workflow

教师默认进入 Teacher Workspace：

1. 选择或创建课程。
2. 在 Courseware Upload 上传英文课程资料、中文课程资料或补充参考资料。
3. 上传后查看 `document_id`、`job_id` 和后台 job 状态。
4. 在 Documents & Jobs 等待文档解析完成。
5. 对已解析课程文档触发 AlignmentRun。
6. 在 Alignment Runs 查看 `term_count`、`card_created_count`、`auto_approved_count`、`qc_count`、`needs_evidence_count` 和失败数。
7. 在 Quality Control 按状态或风险筛选卡片。
8. 查看卡片证据快照、score breakdown、quality flags、AI provider、risk note。
9. 执行 Approve、Edit & Approve、Needs More Evidence、Reject。
10. 在 Student Feedback 查看学生反馈并标记已处理。
11. 使用 Course Terminology Export 按当前课程导出课程术语表。

教师不是逐条审核者，重点处理低置信度、证据不足、错配、OCR 低置信和公式证据缺失。

## Admin Workflow

管理员默认进入 Admin Workspace：

1. 查看用户、课程、全局任务、EvaluationRun、系统日志和用量。
2. 在 Job Status 查看所有后台任务并进行 cancel / retry。
3. 在 Evaluation Runs 查看指标、release gate 和报告摘要。
4. 在 Subscription Plans 页面查看全局 UsageRecord 和 Mock Billing 记录。
5. 在 Knowledge Sources / KB Versions 管理知识源与版本记录。

## Job Status Display

所有长任务统一显示：

- `queued`
- `running`
- `completed`
- `failed`
- `retrying`
- `canceled`

每个 job 显示进度百分比、progress message、关联 document/alignment/evaluation id，以及失败错误。可取消排队或运行任务，可重试失败任务。

## Terminology Card Badges

`TerminologyCard.status` 使用以下用户可读标签：

- `auto_approved`: AI 自动通过 / Auto Approved
- `approved`: 教师已审核 / Teacher Approved
- `pending_quality_control`: 待教师审核 / Needs Review
- `needs_more_evidence`: 证据不足 / Needs Evidence
- `conflict_detected`: 存在冲突 / Conflict
- `rejected`: 已驳回 / Rejected
- `archived`: 已归档 / Archived

`alignment_status` 使用以下标签：

- `exact_match`: 概念一致 / Exact Match
- `accepted_translation`: 译名可接受 / Accepted Translation
- `partial_match`: 部分匹配 / Partial Match
- `no_en_evidence`: 缺少英文证据 / Missing English Evidence
- `no_zh_evidence`: 缺少中文证据 / Missing Chinese Evidence
- `domain_mismatch`: 领域错配 / Domain Mismatch
- `ocr_low_confidence`: OCR 低置信 / OCR Low Confidence
- `formula_evidence_missing`: 公式证据缺失 / Formula Evidence Missing
- `unverified_translation`: 未验证译名 / Unverified Translation
- `invalid_term_candidate`: 无效术语候选 / Invalid Term Candidate

Pending、needs evidence、mock/local provider 的结果都有明显风险提示。

## Error Handling

前端统一通过 `api()` 调用后端，并将核心错误码映射成中英文提示：

- `AUTH_REQUIRED`
- `TOKEN_EXPIRED`
- `PERMISSION_DENIED`
- `VALIDATION_ERROR`
- `FILE_TOO_LARGE`
- `UNSUPPORTED_FILE_TYPE`
- `OCR_UNAVAILABLE`
- `FORMULA_OCR_UNAVAILABLE`
- `AI_PROVIDER_FAILED`
- `INTERNAL_ERROR`

错误不只写入 console，而是显示到页面消息区。

## Known UI Limits

- 当前仍是原生 HTML/CSS/JS 单页应用，没有 React/Vue 构建链。
- 当前没有完整前端端到端自动化测试，PR-7 先提供静态契约测试。
- 状态面板依赖后端已有 API，不实现实时 WebSocket 推送。
- 部分教师操作使用浏览器 `prompt()` 收集原因或修改内容，适合课程 Demo，不是最终生产交互。
