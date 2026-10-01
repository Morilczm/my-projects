# LexiBridge AI Pilot Package Summary

## 文件列表
- `README.md`: 试点包入口、角色阅读路径和使用边界。 Status: `present`.
- `pilot_runbook.md`: 试点负责人组织 Phase 0-5 的总流程。 Status: `present`.
- `teacher_manual.md`: 教师创建课程、上传资料、QC、反馈和导出操作。 Status: `present`.
- `student_manual.md`: 学生搜索术语、查看证据、收藏、掌握、反馈和个人资料上传。 Status: `present`.
- `admin_manual.md`: 管理员查看用户、任务、Evaluation、AI、KB、检索和报告。 Status: `present`.
- `data_authorization_guide.md`: 课程资料授权、source governance 和 restricted 来源边界。 Status: `present`.
- `privacy_and_risk_notice.md`: 隐私、AI/OCR 风险、非生产部署和教师审核边界。 Status: `present`.
- `pilot_metrics.md`: 使用、质量、教师侧、学生侧试点评价指标。 Status: `present`.
- `pre_pilot_checklist.md`: 试点前环境、权限、Evaluation、KB、备份和授权检查。 Status: `present`.
- `during_pilot_log_template.md`: 试点中每日/每次记录模板。 Status: `present`.
- `post_pilot_report_template.md`: 试点复盘报告结构。 Status: `present`.
- `consent_notice_template.md`: 参与者知情说明模板。 Status: `present`.
- `course_material_inventory_template.md`: 课程资料盘点和授权记录模板。 Status: `present`.
- `teacher_feedback_form.md`: 教师反馈采集表。 Status: `present`.
- `student_feedback_form.md`: 学生反馈采集表。 Status: `present`.
- `known_limitations.md`: 当前 local pilot-ready 限制。 Status: `present`.
- `demo_vs_real_pilot.md`: Demo 与真实试点差异。 Status: `present`.
- `final_presentation_materials_index.md`: 课程报告、PPT、Poster 可用材料索引。 Status: `present`.

## 试点流程摘要
- Phase 0: 完成环境、账号、授权、备份和基线测试。
- Phase 1: 导入英文/中文资料并构建课程知识库。
- Phase 2: 触发术语对齐，教师处理 QC 和风险卡片。
- Phase 3: 学生搜索术语、查看证据、收藏、掌握并提交反馈。
- Phase 4: 处理反馈，将关键问题转 EvaluationItem 或 Iteration Backlog。
- Phase 5: 生成 Pilot Report，决定下一轮资料补充和工程迭代。

## 试点成功指标
- `no_evidence_forced_alignment_rate = 0`。
- 学生能搜索并理解课程核心英文术语。
- 教师能通过 evidence、score breakdown、risk_note 判断术语可信度。
- 学生 personal 资料不进入课程公共知识库。
- 高严重度反馈能进入 QC、Evaluation 或 Backlog。

## 当前限制
- 项目是 local pilot-ready，不是 production-ready。
- Demo 数据是自造资料，不代表真实课程复杂度。
- 真实课程资料必须由教师确认授权。
- 术语输出必须结合 evidence、risk_note 和教师审核状态使用。

## 下一步行动
- 按 `pre_pilot_checklist.md` 完成试点前检查。
- 使用 `pilot_runbook.md` 组织 1-3 门课程的小范围试点。
- 试点结束后用 `post_pilot_report_template.md` 复盘。
