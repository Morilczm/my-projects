def test_knowledge_health_fail_without_published_version(app_module):
    with app_module.app.app_context():
        health = app_module.run_knowledge_health_check(course_id=999999)
        assert health["status"] == "FAIL"


def test_knowledge_health_warns_on_high_duplicates(app_module):
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        version = app_module.create_knowledge_base_version(course.id, "course", None, "health")
        version.status = "published"
        version.is_active = True
        for idx in range(4):
            app_module.db.session.add(app_module.KnowledgeChunk(
                document_id=0,
                knowledge_base_version_id=version.id,
                course_id=course.id,
                scope_type="course",
                content=f"chunk {idx}",
                language="zh",
                knowledge_base_type="zh_course_kb",
                visibility="course",
                index_status="duplicate" if idx else "indexed",
                is_duplicate=bool(idx),
                is_active=not bool(idx),
                created_at=app_module.current_time_text(),
            ))
        app_module.db.session.commit()
        health = app_module.run_knowledge_health_check(course_id=course.id, kb_version_id=version.id)
        assert health["status"] == "WARN"
        assert health["metrics"]["duplicate_ratio"] > 0.3
