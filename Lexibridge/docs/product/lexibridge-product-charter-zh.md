# LexiBridge-AI 产品总纲 v3

## 学生优先、证据驱动的双语概念学习产品

### 产品使命

LexiBridge 面向使用英语学习专业课程的中文母语学生。它解决的不是“这个英文词翻译成什么中文”，而是：

> 当前英文课程语境中讨论的专业概念是什么？它在独立中文知识资料中对应什么概念？这一关系有什么双侧证据？是否存在范围差异、多个候选或其他不确定性？

正式核心链路为：

英文课程资料与上下文 → 英文专业概念识别 → 独立中文知识证据检索 → 中文标准术语候选识别 → 中英语义配对 → 双侧证据资格判断 → 不确定性表达 → 学生概念解释 → 个人学习循环。

LexiBridge 是概念理解产品，不是词语翻译器、通用聊天机器人或通用 RAG 平台。

### 一个产品，多种学习空间

LexiBridge 只有一个学生核心产品。学生无需在登录时选择“个人模式”或“学校模式”，并可同时属于多个学习空间：

- `PERSONAL_WORKSPACE`：由学生本人管理，不依赖学校或教师。
- `MANAGED_COURSE_WORKSPACE`：由学校、学院、项目、课程团队、课程负责人或授权教师管理。

两类空间必须共用概念查询、解析、检索、对齐、结果展示、个人概念本和学习记录。空间差异只影响资料归属、证据来源、课程上下文、访问控制、治理、聚合分析和是否支持官方发布，不得产生第二套引擎或学生体验。

### Personal Workspace

个人空间可包含学生有权使用的英文教材、课件、讲义、阅读材料、中文参考资料，以及平台提供的开放许可或治理资料。其合同是：

- 默认仅本人可见；
- 所有查询结果默认 `NON_OFFICIAL`；
- 不需要 Instructor 或 Reviewer 审核；
- 学生可保存笔记、收藏、理解状态并删除自己的资料和记录；
- 私人资料不得自动成为公共知识库或训练数据。

个人空间是普通学生的主要入口。

### Managed Course Workspace

机构托管课程空间提供治理后的课程资料、课程结构、中文证据资料、成员关系、访问权限、课程学科语境和可选聚合分析/官方卡片。

它不意味着每次查询要人工审批，不意味着每个结果都是学校官方答案，也不要求英文课程教师阅读中文、维护中英术语表或逐条批准。学生普通查询仍产生个人、私有、非官方结果。

### 第一阶段学生交互

第一阶段的核心交互单位是“一个处于明确英文课程上下文中的专业概念”：

学生打开已解析英文资料 → 选中术语、专业短语或短句 → 系统取得有限附近上下文 → 识别核心概念 → 返回证据驱动的双语概念结果。

第一阶段不以自由聊天为主界面，不优先扩展任意问答、整篇总结、无边界生成或泛化论文助手。

### 结果的五个独立维度

每个结果必须分别表达，不得合并成一个模糊状态：

| 维度 | 值 | 含义 |
|---|---|---|
| `workspace_scope` | `PERSONAL`, `MANAGED_COURSE` | 资料、权限和课程上下文归属 |
| `visibility` | `PRIVATE`, `COURSE_SHARED` | 可见范围 |
| `authority` | `NON_OFFICIAL`, `OFFICIAL` | 内容权威性 |
| `alignment_status` | `READY`, `REVIEW_REQUIRED`, `NOT_READY` | 机器对齐和证据质量 |
| `publication_status` | `NOT_APPLICABLE`, `DRAFT`, `PUBLISHED`, `WITHDRAWN` | 正式课程内容发布状态 |

普通查询无论位于哪类空间，默认都是 `PRIVATE + NON_OFFICIAL + NOT_APPLICABLE`。只有经过 Reviewer 审核和版本化发布的课程卡片才能是 `MANAGED_COURSE + COURSE_SHARED + OFFICIAL`。

### 普通查询不需要人工批准

机器状态决定结果如何展示，不决定学生是否被允许学习：

- `READY` → `EVIDENCE_BACKED_RECOMMENDATION`：显示推荐概念、双侧证据、对应原因、相近概念区别和非官方标记。
- `REVIEW_REQUIRED` → `EVIDENCE_BACKED_ALTERNATIVES`：显示有限 evidence-backed 候选、冲突原因，`uncertain=true`；学生仍可查看、保存、记笔记和反馈。
- `NOT_READY` → `NO_RELIABLE_ALIGNMENT`：明确没有可靠对应；可显示英文解释及明确标记的 generated hint，但不得伪造标准中文术语或证据。

绝大多数查询应自动完成并作为个人非官方结果展示。少量高风险、争议或集中反馈进入 Reviewer 异常队列；极少量需要成为全班正式内容的概念才进入 Reviewer 审核和发布。

### 用户角色

#### Student

Student 是主要用户，可使用个人空间、加入托管课程、上传有权使用的资料、查询概念、查看证据和不确定性、保存学习记录、添加笔记、标记理解状态并反馈。Student 不能审核他人内容、发布官方内容、查看他人私人记录、绕过权限、配置 Provider 或修改机器 provenance。

#### Instructor

Instructor 是英文课程教师或课程负责人，主界面必须为英语。其职责是管理课程、英文资料、章节和英文上下文，并查看聚合的英文侧学习趋势。Instructor 不负责判断中文术语、阅读中文证据、选择中文候选、批准普通学生查询、维护中英术语表或配置 Provider。

#### Reviewer

Reviewer 是双语异常和正式内容审核角色，可由中方教师、双语助教、协调员、术语专家或授权内容人员承担。Reviewer 只处理高风险错配、多候选冲突、范围争议、集中错误反馈、矛盾证据及官方课程内容。

Task 12J-B 的能力正式归类为 **Reviewer Console（双语异常审核工作台）**，不得作为英文 Instructor 的日常主流程。

#### Admin

Admin 负责账户、权限、Provider、策略、审计、成本、日志和运行治理，不是产品主要用户。

### 中文证据和生成提示

任何中文标准术语结论必须由独立、许可清晰、可治理的中文资料支持。学校授权资料、开放许可资源、合法授权知识资料和学生仅本人使用的授权资料可以成为证据。

模型临时定义、翻译 Provider、Ollama、glossary、无来源网页片段、英文资料内嵌答案、评测 gold、人工英中映射和许可不明资料均不能成为独立中文证据。

Translation/Glossary/Ollama 只能产生：

```text
generated = true
no_evidence = true
provenance_type = GENERATED_HINT
```

它们不能成为 Chinese evidence、canonical Chinese term、READY 的唯一依据、QUALIFIED 对齐、OfficialCourseCard 或 publication evidence。

### 系统职责边界

- 文档解析与切分：保持标题—定义关系和 source/page/block/span provenance，过滤噪声。
- 跨语言检索：从英文概念和有限上下文检索独立中文证据，不宣布最终答案。
- 中文术语候选：只从中文证据识别候选。
- 双语配对：判断语义与概念范围对应，支持一对多、多对一、范围包含、部分重合、近义不等价和无法确认。
- 证据资格：决定自动推荐、展示多个候选或无法可靠对齐。
- LLM Provider：只组织已有证据为学生解释或草稿，不创造术语/citation/provenance，不绕过 qualification/readiness，不自动变为官方内容。

### 核心领域对象

`Workspace` 表示学习资料、权限和课程上下文。

`ConceptQuery` 表示学生在一个 workspace 中选取英文文本、有限上下文并发起的一次私人概念查询。

`AlignmentResult` 保存机器事实和判断：英文概念、中文候选、选中候选、双侧证据、机器状态、风险、reason code、模型/政策版本和 provenance。它不能被学生笔记或正式发布静默覆盖。

`PersonalLearningRecord` 属于 Student 并绑定 AlignmentResult，可存在于两类 workspace；默认 PRIVATE/NON_OFFICIAL，不要求人工审核，不会自动成为官方卡片。

`OfficialCourseCard` 只能存在于 Managed Course，必须关联 AlignmentResult 和 Reviewer decision，保留审核理由、课程范围、引用、发布版本、不可变快照及撤回状态。它不得覆盖 AlignmentResult 或个人笔记。

```text
ConceptQuery
  └─ AlignmentResult
       ├─ PersonalLearningRecord
       └─ OfficialCourseCard（可选）
```

不得将流程设计为“学生查询 → 等待教师审核 → 审核后才能查看”。

### 学生结果页面

两类 workspace 复用同一 Concept Result 页面，至少展示 English Concept、Recommended Chinese Concept、What It Means Here、Why They Align、English Evidence、Chinese Evidence、Alternatives、Do Not Confuse With、学生可理解的不确定性说明，以及保存/笔记/理解/困惑/反馈/请求复核操作。

页面不突出内部 score、policy、Prompt、Provider、audit ID、raw JSON 或管理配置。个人空间标为“个人学习结果，非课程官方答案”；托管课程中的普通结果也必须标为个人非官方结果；只有正式发布卡片显示 Reviewer、版本、发布时间和适用课程。

### 隐私和治理

- 私人资料默认仅本人可访问；
- 课程资料仅授权成员访问；
- 不跨学生、课程或机构泄露；
- 私人上传不自动训练模型；
- 个人查询和笔记不自动展示给 Instructor；
- 个人结果不自动转课程共享；
- 日志、测试、artifact 不保存完整私人资料；
- CI 仅用 synthetic、开放许可或明确授权 fixture；
- Instructor analytics 默认只用聚合数据。

### 产品架构

- LexiBridge Core：解析、layout chunk、KnowledgeChunk、检索、候选、配对、reranking、qualification、provenance、不确定性、结构化解释。
- Student Experience：My Workspace、My Courses、资料阅读、概念选择、Concept Result、个人概念本、笔记、历史和反馈。
- Managed Course Services：课程资料、中文证据、章节、成员、权限、课程上下文、聚合分析。
- Reviewer Console：异常队列、争议、反馈、官方卡片审核和版本化发布。
- Admin Console：账户、权限、Provider、policy、audit、成本、日志和运行状态。

### 非目标与优先级

LexiBridge 不是翻译工具、通用聊天/RAG、英文教师维护的词典、逐查询审批系统、无证据术语表或 Provider 管理产品。在有限学科/课程试点前不得宣称覆盖所有专业。

开发顺序：共享学生查询体验 → 个人空间端到端 → 单托管课程学生流程 → 真实课程/学生试点 → 个人概念本循环 → 相近概念学习辅助 → 中文证据治理 → 英语 Instructor 聚合分析 → Reviewer 异常与官方发布。

Task 12 的解析、检索、候选、配对、qualification、readiness、结构化 Provider、审计、幂等、draft、review 和 publication protection 必须复用，不得建立平行系统。

