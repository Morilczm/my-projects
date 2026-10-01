def test_retrieval_regression_detects_positive_and_negative_cases(app_module):
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        version = app_module.create_knowledge_base_version(course.id, "course", None, "regression")
        version.status = "published"
        version.is_active = True
        source = app_module.KnowledgeSource(
            name="Regression Source",
            source_title="Regression Source",
            course_id=course.id,
            scope_type="course",
            language="zh",
            authorization_status="allowed_for_course_use",
            status="active",
            allow_derivative_cards=True,
            version_introduced_id=version.id,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(source)
        app_module.db.session.flush()
        app_module.db.session.add(app_module.KnowledgeChunk(
            document_id=0,
            knowledge_base_version_id=version.id,
            knowledge_source_id=source.id,
            source_id=source.id,
            course_id=course.id,
            scope_type="course",
            course=course.name,
            content="傅里叶变换用于将时域信号表示为频率分量。",
            language="zh",
            knowledge_base_type="zh_course_kb",
            visibility="course",
            index_status="indexed",
            is_active=True,
            created_at=app_module.current_time_text(),
        ))
        version.chunk_count = 1
        evaluation_set = app_module.EvaluationSet(name="regression-set", created_at=app_module.current_time_text())
        app_module.db.session.add(evaluation_set)
        app_module.db.session.flush()
        app_module.db.session.add(app_module.EvaluationItem(
            set_id=evaluation_set.id,
            evaluation_set_id=evaluation_set.id,
            item_id="REG-1",
            split="test",
            course_id=course.id,
            english_term="Fourier Transform",
            expected_chinese_term="傅里叶变换",
            expected_chinese_evidence="傅里叶变换用于将时域信号表示为频率分量。",
            negative_chinese_evidence="哈希表通过哈希函数将关键字映射到桶或存储位置。",
            expected_alignment_status="exact_match",
            created_at=app_module.current_time_text(),
        ))
        app_module.db.session.commit()
        result = app_module.run_retrieval_regression_for_course(course_id=course.id, kb_version_id=version.id)
        assert result["status"] == "completed"
        assert result["case_count"] >= 1
        assert result["no_evidence_forced_match"] == 0
