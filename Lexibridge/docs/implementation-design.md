# LexiBridge AI Local MVP v0.8 实现文档

## 1. 项目定位

LexiBridge AI 是面向中外合作办学课程的 AI 双语课程知识对齐平台。当前交付版本是本地可运行的课程 Demo / Local MVP v0.8，不是完整生产系统。

核心目标不是“翻译一个词”，而是基于英文课程资料、英文知识库、中文知识库和学生个人资料，生成可追溯、有证据、有置信度、有质量控制状态的双语课程术语知识卡片。

核心链路：

```text
Document Upload
-> Document Parsing / OCR
-> Text Chunking
-> Term Extraction
-> English Evidence Retrieval
-> AI Translation Candidate
-> Chinese Evidence Retrieval
-> Semantic Alignment
-> Confidence Scoring
-> TerminologyCard
-> Search / Learning / Feedback
-> Quality Control
```

## 2. 技术栈

| 层级 | 当前实现 |
| --- | --- |
| 后端 | Flask |
| 数据库 | SQLite，本地文件数据库 |
| ORM | Flask-SQLAlchemy |
| 前端 | 单页 `frontend/index.html` + 原生 CSS/JS |
| 文件解析 | PyMuPDF、python-docx、python-pptx、文本读取 |
| OCR | `backend/services/ocr.py` 抽象层，支持 Tesseract/PaddleOCR/none/mock/auto |
| AI Provider | `backend/services/ai_providers.py` 抽象层，DeepSeek 为当前 live provider |
| 导出 | reportlab PDF |
| 支付/邮箱 | mock payment / mock email |

## 3. 目录结构

```text
LexiBridge-AI/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   └── services/
│       ├── ai_providers.py
│       ├── formula_detection.py
│       ├── formula_ocr.py
│       └── ocr.py
├── frontend/
│   ├── index.html
│   └── js/config.js
├── scripts/
│   ├── migrate_db.py
│   ├── run_backend.sh
│   └── package_release.sh
├── docs/
│   ├── implementation-design.md
│   ├── demo-test-report.md
│   └── project-structure-plan.md
├── README.md
├── .env.example
└── requirements.txt
```

交付包由 `scripts/package_release.sh` 生成，会排除 `.env`、数据库、uploads、venv、缓存、`.git` 和 Mac 元数据。

## 4. 后端模块说明

### 4.1 `backend/app.py`

当前 Local MVP 的主应用文件，包含：

- Flask app 初始化。
- SQLite/SQLAlchemy 模型。
- schema 兼容迁移辅助函数。
- 用户认证与权限校验。
- 文档上传、解析、切块、索引。
- 知识库检索。
- 术语抽取和术语卡片生成。
- 质量控制、反馈、会员、用量、后台管理 API。
- legacy 接口兼容层。

### 4.2 `backend/services/ocr.py`

OCR 抽象层。

| Provider | 行为 |
| --- | --- |
| `none` | 明确返回 OCR 不可用 |
| `mock` | 不伪造文字，只提示需要真实 OCR 引擎 |
| `tesseract` | 调用本地 Tesseract 命令行 |
| `paddle` | 调用本地 PaddleOCR 包 |
| `auto` | 优先 Tesseract，再 PaddleOCR，否则 mock unavailable |

关键规则：

- 图片和扫描 PDF 没有 OCR 结果时，不生成术语卡片。
- OCR 占位符字符串不会进入术语抽取。
- OCR confidence 低于 60 时，术语卡片不能自动通过。

### 4.3 `backend/services/ai_providers.py`

AI Provider 抽象层。

| Provider | 当前状态 |
| --- | --- |
| `DeepSeekProvider` | 已实现 live API 调用、术语抽取、证据对齐、学生回答 |
| `MockProvider` | 本地演示 fallback，不允许 auto approved |
| `OpenAIProvider` | placeholder，明确未实现 |
| `GeminiProvider` | placeholder，明确未实现 |
| `ClaudeProvider` | placeholder，明确未实现 |

关键规则：

- DeepSeek key 缺失或调用失败时，系统不伪装成真实 AI 成功。
- mock/local heuristic 结果写入 `ai_model` 和 `risk_note`。
- mock/local heuristic 生成的卡片进入 QC 或 `needs_more_evidence`。

## 5. 数据结构设计

当前数据库由 `scripts/migrate_db.py` 和 `backend/app.py` 中的模型共同维护。迁移脚本会创建表、补字段、写入测试账号、课程、会员套餐和 demo KB。

### 5.1 用户与认证

#### `User`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `username` | 用户名，唯一 |
| `email` | 邮箱，唯一 |
| `password_hash` | 哈希后的密码 |
| `role` | `student` / `teacher` / `admin` |
| `is_verified` | 邮箱是否已验证 |
| `verification_token` | 邮箱验证 token |
| `verification_token_expires_at` | 验证 token 过期时间 |
| `reset_token` | 密码重置 token |
| `reset_token_expires_at` | 重置 token 过期时间 |
| `created_at` | 创建时间 |
| `last_login_at` | 最近登录时间 |

#### `AuthToken`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | 用户 ID |
| `token` | Bearer token |
| `created_at` | 创建时间 |
| `expires_at` | 过期时间 |
| `revoked` | 是否已退出/吊销 |

关系：`User 1 -> N AuthToken`。

### 5.2 课程空间

#### `Course`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `name` / `course_name` | 课程名称 |
| `course_code` | 课程代码 |
| `semester` | 学期 |
| `description` | 课程说明 |
| `language_mode` | 语言模式，通常为 bilingual |
| `teacher_id` | 任课教师用户 ID |
| `created_at` | 创建时间 |

#### `CourseMember`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `course_id` | 课程 ID |
| `user_id` | 用户 ID |
| `role` / `role_in_course` | 在课程内角色 |
| `joined_at` | 加入时间 |

关系：`Course N <-> N User`，通过 `CourseMember` 关联。

### 5.3 文档与文本块

#### `Document`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `owner_user_id` | 上传者 ID |
| `course_id` | 课程 ID，可为空 |
| `scope_type` | `global` / `course` / `personal` |
| `filename` | 原始文件名 |
| `saved_filename` | 本地保存文件名 |
| `file_type` | pdf/docx/pptx/txt/png 等 |
| `language` | 文档语言 |
| `upload_time` | 上传时间 |
| `parsing_status` | `processing` / `parsed` / `failed` / `needs_ocr_engine` 等 |
| `ocr_required` | 是否触发 OCR |
| `ocr_provider` | OCR provider |
| `ocr_status` | OCR 状态 |
| `ocr_error` | OCR 错误信息 |
| `source_type` | teacher_upload / student_upload 等 |

#### `DocumentChunk`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `document_id` | 文档 ID |
| `course_id` | 课程 ID，可为空 |
| `user_id` | chunk 所属用户 |
| `language` | chunk 语言 |
| `page_number` | PDF 页码 |
| `slide_number` | PPT 页码 |
| `section_title` | 章节标题 |
| `content` | 解析后的文本内容 |
| `source_type` | 来源类型 |
| `source_location` | 页码/幻灯片/段落位置 |
| `ocr_confidence` | OCR 置信度 |
| `ocr_provider` | OCR provider |
| `ocr_status` | OCR 状态 |
| `ocr_error` | OCR 错误信息 |
| `created_at` | 创建时间 |

关系：`Document 1 -> N DocumentChunk`。

### 5.4 知识库

#### `KnowledgeSource`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `name` | 知识源名称 |
| `language` | 语言 |
| `discipline` | 学科 |
| `source_type` | textbook / lecture_notes / teacher_upload / student_upload / platform_seed 等 |
| `access_method` | manual_upload / api / crawler placeholder / mock_source 等 |
| `license_status` | authorized / open_licensed / public_domain / restricted / unknown |
| `allow_full_text_indexing` | 是否允许全文索引 |
| `allow_student_search` | 是否允许学生检索 |
| `allow_derivative_cards` | 是否允许生成派生术语卡 |
| `created_by` | 创建者 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

#### `KnowledgeBaseVersion`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `kb_scope` | global / course / personal |
| `course_id` | 课程 ID，可为空 |
| `version_name` | 版本名 |
| `description` | 版本说明 |
| `source_count` | 知识源数量 |
| `chunk_count` | 知识块数量 |
| `created_at` | 创建时间 |
| `created_by` | 创建者 |
| `is_active` | 是否当前启用 |

#### `KnowledgeChunk`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `source_id` | 知识源 ID |
| `document_id` | 来源文档 ID |
| `course_id` | 课程 ID，可为空 |
| `course` | legacy 课程名 |
| `title` | 来源标题 |
| `language` | en / zh / bilingual |
| `discipline` | 学科 |
| `chapter` | 章节 |
| `page_number` / `source_page` | 页码或来源位置 |
| `content` | 知识片段内容 |
| `keywords` | 关键词 |
| `source_citation` | 引用来源 |
| `knowledge_base_type` | `en_course_kb` / `zh_course_kb` / `student_personal_kb` 等 |
| `owner_user_id` | 个人知识库所属用户 |
| `visibility` | global / course / private |
| `created_at` | 创建时间 |

知识库边界：

- `global`：平台级知识库，Admin 管理。
- `course`：课程知识库，Teacher/Admin 管理，学生加入课程后可检索。
- `personal`：学生个人知识库，默认 private，只能本人检索。

### 5.5 术语卡片与学习记录

#### `TerminologyCard`

核心产品表。

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `scope_type` | course / personal |
| `course_id` | 课程 ID，可为空 |
| `owner_user_id` | 个人卡片所属用户，可为空 |
| `english_term` | 英文术语 |
| `final_chinese_term` | 最终中文术语 |
| `ai_translation_candidate` | AI 候选中文术语 |
| `courseware_sentence` | 课件或资料中的上下文句子 |
| `english_kb_evidence` | 英文证据 |
| `chinese_kb_evidence` | 中文证据 |
| `concept_explanation` | 概念解释 |
| `alignment_reason` | 对齐理由 |
| `confidence_score` | 0-100 置信度 |
| `status` | `auto_approved` / `pending_quality_control` / `approved` / `rejected` / `needs_more_evidence` / `conflict_detected` |
| `source_document_id` | 来源文档 ID |
| `english_evidence_chunk_id` | 英文证据 chunk ID |
| `chinese_evidence_chunk_id` | 中文证据 chunk ID |
| `ai_model` | DeepSeek / local_heuristic / mock 等 |
| `risk_note` | 风险提示 |
| `feedback_count` | 反馈数量 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

自动通过规则：

- `confidence_score >= 85`
- 英文证据存在
- 中文证据存在
- OCR confidence 不低于 60
- AI provider 不是 mock/local heuristic
- 没有冲突或证据不足风险

否则进入 `pending_quality_control` 或 `needs_more_evidence`。

#### `Term`

legacy 表，保留兼容旧接口。新功能以 `TerminologyCard` 为核心，旧 `Term` 通过 `sync_term_to_card()` 同步到卡片表。

#### `StudentTermRecord`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | 学生 ID |
| `term_id` | TerminologyCard ID |
| `is_favorite` | 是否收藏 |
| `is_mastered` | 是否已掌握 |
| `last_viewed_at` | 最近查看时间 |

#### `Feedback`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | 反馈用户 |
| `term_id` | 对应术语卡片或 legacy term |
| `course_id` | 课程 ID |
| `feedback_content` | 反馈内容 |
| `status` | open / resolved |
| `created_at` | 创建时间 |
| `resolved_at` | 解决时间 |

反馈达到阈值后，术语卡片进入 QC。

### 5.6 会员、用量与账单

#### `SubscriptionPlan`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `name` | Free / Basic / Pro |
| `price_monthly` | 月价格 |
| `monthly_pages` | 每月解析页额度 |
| `monthly_ai_calls` | 每月 AI/search 额度 |
| `export_enabled` | 是否允许导出 |
| `description` | 套餐说明 |
| `is_active` | 是否启用 |

默认套餐：

| Plan | Price | Pages | AI/Search | Export |
| --- | ---: | ---: | ---: | --- |
| Free | 0 | 5 | 20 | false |
| Basic | 10 | 100 | 300 | true |
| Pro | 39 | 500 | 2000 | true |

#### `UserSubscription`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | 用户 ID |
| `plan_id` | 套餐 ID |
| `start_date` | 开始时间 |
| `end_date` | 结束时间 |
| `status` | active / replaced / expired |
| `auto_renew` | 是否自动续费 |

#### `UsageRecord`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | 用户 ID |
| `action_type` | document_parse_page / ocr_page / ai_alignment / term_search / knowledge_search |
| `units_used` | 消耗数量 |
| `related_document_id` | 关联文档 |
| `related_term_id` | 关联术语 |
| `created_at` | 创建时间 |

#### `BillingRecord`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `user_id` | 用户 ID |
| `plan_id` | 套餐 ID |
| `amount` | 金额 |
| `payment_method` | 当前为 mock_payment |
| `payment_status` | paid 等 |
| `created_at` | 创建时间 |

### 5.7 任务与日志

#### `IngestionJob`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `source_id` | 知识源 ID |
| `document_id` | 文档 ID |
| `status` | running / completed / failed |
| `started_at` | 开始时间 |
| `finished_at` | 结束时间 |
| `error_message` | 错误信息 |
| `processed_pages` | 处理页数 |
| `created_by` | 创建者 |

#### `SystemLog`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键 |
| `level` | info / warning / error |
| `module` | auth / ocr / ai_provider / mock_payment 等 |
| `message` | 日志消息 |
| `created_at` | 创建时间 |

## 6. 权限模型

| 角色 | 权限范围 |
| --- | --- |
| Student | 加入课程、查看已通过课程卡片、个人工作区上传、收藏、掌握、反馈、查看订阅与用量 |
| Teacher | 创建/管理自己课程、上传课程资料、查看课程 KB、处理课程 QC、查看学生反馈 |
| Admin | 用户、课程、知识源、会员、日志、用量、全局配置管理 |

关键规则：

- 未登录用户不能访问核心数据 API。
- Student 不能访问 Admin API。
- Teacher 不能访问全站用户权限管理。
- Student A 不能查看 Student B 的 personal 文档、chunk、card。
- Teacher 默认不能查看学生个人资料。
- 非课程成员不能查看该课程卡片。

## 7. 检索与对齐策略

当前检索是 SQLite + keyword/simple similarity，不是生产级向量数据库。

检索规则：

- 不再使用“没有结果就返回最新 chunk”的 fallback。
- 分数低于阈值时返回空证据。
- 英文证据优先 course English KB，再 global English KB。
- 中文证据优先 course Chinese KB，再 global Chinese KB。
- personal workflow 只检索当前用户自己的 personal KB。

证据不足时：

- 不自动通过。
- 卡片状态为 `needs_more_evidence` 或 `pending_quality_control`。
- 前端展示风险提示。

## 8. 文档解析策略

| 文件类型 | 策略 |
| --- | --- |
| TXT / Markdown | 直接读取文本 |
| DOCX | 提取段落和表格 |
| PPTX | 提取幻灯片文本和表格 |
| Digital PDF | PyMuPDF 按页抽取文本 |
| Scanned PDF | 文本过少的页渲染为图片后 OCR |
| JPG / PNG | 直接 OCR |

AI 不直接读取原始文件，只接收 `DocumentChunk.content`。

## 9. 主要 API

### Auth

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET/POST /api/auth/verify-email`
- `POST /api/auth/password-reset/request`
- `POST /api/auth/password-reset/confirm`
- `GET /api/auth/me`

### Course

- `GET/POST /api/courses`
- `GET /api/courses/mine`
- `POST /api/courses/<id>/join`

### Document

- `POST /api/documents/upload`
- `GET /api/documents`
- `GET /api/documents/<id>/chunks`

### Knowledge

- `GET/POST /api/knowledge/sources`
- `GET/POST /api/knowledge/versions`
- `GET /api/knowledge/search`

### Terminology

- `POST /api/alignment/run`
- `GET /api/terminology/cards`
- `GET /api/terminology/cards/<id>`
- `POST /api/terminology/cards/<id>/favorite`
- `POST /api/terminology/cards/<id>/mastered`
- `POST /api/terminology/cards/<id>/feedback`
- `GET /api/terminology/cards/export`

### Quality Control

- `GET /api/quality-control`
- `POST /api/quality-control/<card_id>/approve`
- `POST /api/quality-control/<card_id>/edit`
- `POST /api/quality-control/<card_id>/needs-more-evidence`
- `POST /api/quality-control/<card_id>/reject`

### Subscription/Admin

- `GET /api/subscription/plans`
- `GET /api/subscription/me`
- `POST /api/subscription/mock-payment`
- `GET /api/usage/me`
- `GET /api/admin/users`
- `GET /api/admin/usage`
- `GET /api/admin/billing`
- `GET /api/admin/logs`
- `GET /api/admin/ingestion-jobs`

## 10. 初始化与迁移

运行：

```bash
python scripts/migrate_db.py
```

会执行：

- `db.create_all()`
- `ensure_schema_columns()` 兼容补字段
- seed 三类用户
- seed 课程
- seed Free/Basic/Pro 套餐
- seed demo knowledge base

测试账号：

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@lexibridge.local` | `Admin1234` |
| Teacher | `teacher@lexibridge.local` | `Teacher1234` |
| Student | `student@lexibridge.local` | `Student1234` |

## 11. OCR、混合 PDF 与 FormulaBlock

文档接入层现在区分四类对象：

- `Document`：上传文件主记录。
- `DocumentChunk`：数字 PDF/DOCX/PPTX/TXT 文本，或真实普通 OCR 识别出来的文本。
- 图片区域：PDF 页面中的 image block 会保留 page、bbox 和派生图片路径。
- `FormulaBlock`：图片型公式识别状态，独立保存，不进入术语抽取。

混合 PDF 每页都会执行：

1. 抽取可复制 digital text，保存为普通 `DocumentChunk`。
2. 即使页面已有 digital text，也继续扫描页面 image blocks。
3. 将符合尺寸阈值的图片区域按 `PDF_OCR_DPI` 渲染到 `uploads/derived/document_<id>/`。
4. 对图片区域执行普通 OCR。
5. 使用启发式公式检测判断是否创建 `FormulaBlock` 并调用 Formula OCR provider。

普通 OCR 与公式 OCR 是两个系统：

- 普通 OCR：`OCR_PROVIDER=none|tesseract|paddle|mock|auto`，用于中英文文字。
- 公式 OCR：`FORMULA_OCR_PROVIDER=none|mock|mathpix|local_latex`，用于公式 LaTeX。

`none/mock` 不伪造结果。没有公式 OCR provider 时，公式区域保存为：

```text
FormulaBlock.status = needs_formula_ocr_engine
```

`FormulaBlock` 字段包括：

```text
id, document_id, course_id, owner_user_id, scope_type,
page_number, slide_number, bbox_json, image_path,
latex, plain_text, provider, confidence, status, error,
quality_flags_json, created_at
```

术语抽取隔离规则：

- `[OCR_REQUIRED]`、`[OCR_FALLBACK]`、`[FormulaBlock #id]` 不进入抽取。
- LaTeX-like token、`int`、`sqrt`、`frac`、`theta`、`lambda`、`x^2` 等公式噪声不生成 `english_term`。
- 公式可以作为证据状态展示，但不能直接变成术语卡片核心词。

状态约定：

- Document: `processing`, `parsed`, `parsed_with_warnings`, `failed`, `needs_ocr_engine`, `needs_formula_ocr_engine`
- OCR: `not_required`, `ok`, `low_confidence`, `ocr_unavailable`, `ocr_failed`, `empty_result`
- Formula OCR: `not_required`, `ok`, `needs_formula_ocr_engine`, `formula_ocr_failed`, `low_confidence`, `no_formula_detected`

## 12. 当前限制

当前版本仍然是 Local MVP：

- 没有真实云部署。
- 没有真实支付。
- 没有真实 SMTP。
- 没有真实向量数据库。
- 没有自动抓取教材。
- 没有 ByrDocs、出版社 API 或学校图书馆连接器。
- OpenAI/Gemini/Claude 只是 placeholder。
- OCR 需要本机安装 Tesseract 或 PaddleOCR；未安装时不会伪造文字。
- Mock/local AI 只用于演示流程，不能代表真实专业审核。

## 13. 交付文件夹

当前干净交付包由以下命令生成：

```bash
bash scripts/package_release.sh
```

输出：

```text
dist/LexiBridge-AI-Local-MVP-v0.8/
dist/LexiBridge-AI-Local-MVP-v0.8.zip
```

该交付包不包含：

- `.env`
- 数据库文件
- 上传文件
- 虚拟环境
- `.git`
- 缓存目录
- Mac 系统元数据
