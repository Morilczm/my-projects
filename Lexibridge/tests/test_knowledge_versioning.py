def _course(app_module):
    return app_module.Course.query.filter_by(name="OCR Test Course").first()


def test_create_publish_and_rollback_kb_versions(app_module):
    with app_module.app.app_context():
        course = _course(app_module)
        v1 = app_module.create_knowledge_base_version(course.id, "course", None, "v1")
        v1.status = "ready"
        source = app_module.KnowledgeSource(
            name="Signal Source",
            source_title="Signal Source",
            course_id=course.id,
            scope_type="course",
            language="zh",
            source_type="teacher_upload",
            license_type="teacher_provided",
            authorization_status="allowed_for_course_use",
            status="active",
            version_introduced_id=v1.id,
            allow_derivative_cards=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(source)
        app_module.db.session.flush()
        chunk = app_module.KnowledgeChunk(
            document_id=0,
            knowledge_base_version_id=v1.id,
            knowledge_source_id=source.id,
            source_id=source.id,
            course_id=course.id,
            scope_type="course",
            course=course.name,
            content="傅里叶变换用于将时域信号表示为频率分量。",
            normalized_text="傅里叶变换用于将时域信号表示为频率分量。",
            content_hash="hash-v1",
            language="zh",
            knowledge_base_type="zh_course_kb",
            visibility="course",
            index_status="indexed",
            is_active=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(chunk)
        app_module.db.session.flush()
        v1.chunk_count = 1
        result = app_module.publish_kb_version(v1.id, actor_user_id=1)
        assert result["status"] == "success"
        assert v1.status == "published"

        v2 = app_module.create_knowledge_base_version(course.id, "course", None, "v2", parent_version_id=v1.id)
        v2.status = "ready"
        v2.chunk_count = 1
        app_module.db.session.flush()
        rollback = app_module.rollback_kb_version(course.id, v1.id, actor_user_id=1)
        assert rollback["status"] == "success"
        assert v1.status == "published"
        assert v2.status == "ready"


def test_personal_kb_version_requires_owner(app_module):
    with app_module.app.app_context():
        version = app_module.create_knowledge_base_version(None, "personal", 123, "personal")
        assert version.scope_type == "personal"
        assert version.owner_user_id == 123
