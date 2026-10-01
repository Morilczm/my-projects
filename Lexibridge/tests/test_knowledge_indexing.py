def test_document_chunks_index_into_kb_version(app_module):
    with app_module.app.app_context():
        teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        document = app_module.Document(
            owner_user_id=teacher.id,
            course_id=course.id,
            scope_type="course",
            filename="signal.txt",
            file_type="txt",
            language="en",
            parsing_status="parsed",
            source_type="teacher_upload",
            upload_time=app_module.current_time_text(),
        )
        app_module.db.session.add(document)
        app_module.db.session.flush()
        app_module.db.session.add(app_module.DocumentChunk(
            document_id=document.id,
            course_id=course.id,
            owner_user_id=teacher.id,
            chunk_index=1,
            language="en",
            content="Fourier Transform converts a time-domain signal.",
            ocr_confidence=100,
            created_at=app_module.current_time_text(),
        ))
        app_module.db.session.commit()
        version = app_module.create_knowledge_base_version(course.id, "course", None, "index test", created_by=teacher.id)
        report = app_module.index_document_into_kb_version(document.id, version.id)
        app_module.db.session.commit()
        assert report["chunks_created"] == 1
        chunk = app_module.KnowledgeChunk.query.filter_by(knowledge_base_version_id=version.id).first()
        assert chunk.content_hash
        assert chunk.index_status == "indexed"
        assert chunk.knowledge_source_id
        assert version.status == "ready"


def test_personal_document_cannot_index_into_course_kb(app_module):
    with app_module.app.app_context():
        student = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        document = app_module.Document(
            owner_user_id=student.id,
            course_id=None,
            scope_type="personal",
            filename="private.txt",
            file_type="txt",
            language="en",
            upload_time=app_module.current_time_text(),
        )
        app_module.db.session.add(document)
        app_module.db.session.commit()
        version = app_module.create_knowledge_base_version(course.id, "course", None, "course")
        try:
            app_module.index_document_into_kb_version(document.id, version.id)
            assert False
        except PermissionError:
            assert True
