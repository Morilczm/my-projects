from services.alignment import finalize_alignment_decision


def evidence(score=0.9, language="en"):
    return [{
        "chunk_id": 11 if language == "en" else 12,
        "source_title": "Signal Processing Notes",
        "source_citation": "Lecture 3, p.12",
        "page_number": 12,
        "language": language,
        "knowledge_base_type": "en_course_kb" if language == "en" else "zh_course_kb",
        "visibility": "course",
        "content_excerpt": "Fourier Transform converts a time-domain signal into a frequency-domain representation.",
        "evidence_score": score,
        "evidence_strength": "strong" if score >= 0.8 else "weak",
        "score_breakdown": {
            "course_scope_score": 1.0,
            "source_quality_score": 0.9,
        },
        "risk_flags": [],
    }]


def strong_alignment(run_id=None, **overrides):
    data = {
        "english_term": "Fourier Transform",
        "final_chinese_term": "傅里叶变换",
        "ai_translation_candidate": "傅里叶变换",
        "courseware_sentence": "Fourier Transform converts a time-domain signal into a frequency-domain representation.",
        "alignment_status": "exact_match",
        "confidence_score": 94,
        "english_evidence_items": evidence(0.9, "en"),
        "chinese_evidence_items": evidence(0.88, "zh"),
        "explanation": "傅里叶变换用于时域与频域表示之间的概念对齐。",
        "alignment_reason": "Both evidence sides refer to the same signal-processing concept.",
        "ai_provider": "deepseek",
        "ai_model": "deepseek-chat",
        "provider_status": "real_provider",
        "is_real_provider": True,
        "prompt_version": "alignment_v1",
        "retrieval_version": "local_lexical_v1",
    }
    if run_id is not None:
        data["alignment_run_id"] = run_id
        data["source_alignment_run_id"] = run_id
    data.update(overrides)
    return finalize_alignment_decision(data)


def test_card_generation_persists_snapshots_and_alignment_run(app_module):
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
        run = app_module.AlignmentRun(
            document_id=None,
            course_id=course.id,
            triggered_by=teacher.id,
            provider="deepseek",
            model_name="deepseek-chat",
            ai_provider="deepseek",
            ai_model="deepseek-chat",
            prompt_version="alignment_v1",
            retrieval_version="local_lexical_v1",
            status="running",
            started_at=app_module.current_time_text(),
        )
        app_module.db.session.add(run)
        app_module.db.session.flush()
        card = app_module.create_or_update_card_from_alignment(
            "Fourier Transform",
            strong_alignment(run.id),
            scope_type="course",
            course_id=course.id,
            owner_user_id=None,
            courseware_sentence="Fourier Transform converts a time-domain signal into a frequency-domain representation.",
        )
        app_module.update_alignment_run_stats(run, cards=[card], term_count=1)
        run.status = "completed"
        run.finished_at = app_module.current_time_text()
        app_module.db.session.commit()

        assert card.status == "auto_approved"
        assert card.alignment_status == "exact_match"
        assert card.source_alignment_run_id == run.id
        assert card.retrieval_version == "local_lexical_v1"
        assert app_module.safe_json_loads(card.english_evidence_snapshot, [])[0]["chunk_id"] == 11
        assert "auto_approval_gate" in app_module.safe_json_loads(card.score_breakdown_json, {})
        assert run.card_created_count == 1
        assert run.auto_approved_count == 1


def test_rejected_card_is_not_system_auto_approved_again(app_module):
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        card = app_module.TerminologyCard(
            english_term="Convolution",
            normalized_english_term=app_module.normalize_english_term("Convolution"),
            final_chinese_term="卷积",
            scope_type="course",
            course_id=course.id,
            status="rejected",
            rejected_reason="Teacher rejected stale candidate.",
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(card)
        app_module.db.session.commit()

        alignment = strong_alignment(english_term="Convolution", final_chinese_term="卷积")
        updated = app_module.create_or_update_card_from_alignment(
            "Convolution",
            alignment,
            scope_type="course",
            course_id=course.id,
        )
        app_module.db.session.commit()

        assert updated.id == card.id
        assert updated.status == "rejected"
        assert updated.rejected_reason == "Teacher rejected stale candidate."


def test_alignment_run_detail_api_returns_statistics(app_module, client, teacher_token):
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
        run = app_module.AlignmentRun(
            document_id=99,
            course_id=course.id,
            triggered_by=teacher.id,
            provider="deepseek",
            model_name="deepseek-chat",
            ai_provider="deepseek",
            ai_model="deepseek-chat",
            prompt_version="alignment_v1",
            retrieval_version="local_lexical_v1",
            term_count=3,
            card_created_count=2,
            auto_approved_count=1,
            qc_count=1,
            needs_evidence_count=0,
            conflict_count=0,
            failed_count=0,
            status="completed",
            started_at=app_module.current_time_text(),
            finished_at=app_module.current_time_text(),
        )
        app_module.db.session.add(run)
        app_module.db.session.commit()
        run_id = run.id

    response = client.get(
        f"/api/alignment/runs/{run_id}",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert response.status_code == 200
    data = response.get_json()["run"]
    assert data["term_count"] == 3
    assert data["card_created_count"] == 2
    assert data["auto_approved_count"] == 1
