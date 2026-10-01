def _seed_source_chunk(app_module, course, authorization="allowed_for_course_use", status="active"):
    version = app_module.create_knowledge_base_version(course.id, "course", None, "source")
    version.status = "published"
    version.is_active = True
    source = app_module.KnowledgeSource(
        name=f"source-{authorization}-{status}",
        source_title="Governed Source",
        course_id=course.id,
        scope_type="course",
        language="zh",
        source_type="teacher_upload",
        authorization_status=authorization,
        status=status,
        allow_derivative_cards=authorization != "restricted_no_derivative",
        version_introduced_id=version.id,
        created_at=app_module.current_time_text(),
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    chunk = app_module.KnowledgeChunk(
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
    )
    app_module.db.session.add(chunk)
    version.chunk_count = 1
    app_module.db.session.commit()
    return version


def test_restricted_and_removed_sources_do_not_return_public_evidence(app_module):
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        restricted = _seed_source_chunk(app_module, course, authorization="restricted_no_derivative")
        assert app_module.retrieve_evidence_results("Fourier Transform", course_id=course.id, language="zh", knowledge_base_type="zh_course_kb", knowledge_base_version_id=restricted.id) == []
        removed = _seed_source_chunk(app_module, course, status="removed")
        assert app_module.retrieve_evidence_results("Fourier Transform", course_id=course.id, language="zh", knowledge_base_type="zh_course_kb", knowledge_base_version_id=removed.id) == []


def test_deprecated_source_is_not_strong_evidence(app_module):
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        deprecated = _seed_source_chunk(app_module, course, status="deprecated")
        results = app_module.retrieve_evidence_results("Fourier Transform", course_id=course.id, language="zh", knowledge_base_type="zh_course_kb", knowledge_base_version_id=deprecated.id)
        assert results
        assert results[0]["evidence_strength"] != "strong"
