from services.alignment import finalize_alignment_decision


def evidence(score=0.9, language="en"):
    return [{
        "chunk_id": 1 if language == "en" else 2,
        "source_title": "Signal Processing Notes",
        "source_citation": "Lecture 1",
        "language": language,
        "knowledge_base_type": "en_course_kb" if language == "en" else "zh_course_kb",
        "visibility": "course",
        "content_excerpt": "Fourier Transform converts a time-domain signal into a frequency-domain representation.",
        "evidence_score": score,
        "evidence_strength": "strong",
        "score_breakdown": {"course_scope_score": 1.0, "source_quality_score": 0.9},
        "risk_flags": [],
    }]


def test_generate_alignment_uses_call_ai_task(app_module, monkeypatch):
    called = {"count": 0}

    def fake_call_ai_task(*args, **kwargs):
        called["count"] += 1
        return {
            "status": "error",
            "error_code": "AI_INVALID_RESPONSE",
            "message": "bad schema",
            "provider_name": "deepseek",
            "provider_mode": "live",
            "model_name": "deepseek-chat",
            "ai_call_log_id": 123,
        }

    monkeypatch.setattr(app_module, "call_ai_task", fake_call_ai_task)
    with app_module.app.app_context():
        result = app_module.generate_alignment_result(
            "Fourier Transform",
            "Fourier Transform converts a signal.",
            "No Such Course",
            provider_metadata={
                "provider": "deepseek",
                "provider_mode": "live",
                "model_name": "deepseek-chat",
                "is_real_provider": True,
            },
        )
        assert called["count"] == 1
        assert result["review_status"] == "needs_more_evidence"
        assert result["alignment_status"] in {"no_en_evidence", "no_zh_evidence"}


def test_mock_and_local_cannot_auto_approve_through_card_generation(app_module):
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        alignment = finalize_alignment_decision({
            "english_term": "Mock Alignment Term",
            "final_chinese_term": "傅里叶变换",
            "alignment_status": "exact_match",
            "confidence_score": 95,
            "english_evidence_items": evidence(0.92, "en"),
            "chinese_evidence_items": evidence(0.91, "zh"),
            "ai_provider": "mock",
            "ai_provider_mode": "mock",
            "ai_model": "mock",
            "provider_status": "mock",
            "is_real_provider": False,
            "prompt_key": "term_alignment",
            "prompt_version": "v1",
        })
        card = app_module.create_or_update_card_from_alignment(
            "Mock Alignment Term",
            alignment,
            scope_type="course",
            course_id=course.id,
        )
        assert card.status == "pending_quality_control"
        assert "mock_or_local_ai" in app_module.safe_json_loads(card.quality_flags_json, [])


def test_live_evaluated_model_can_auto_approve_and_records_metadata(app_module):
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name="OCR Test Course").first()
        provider = app_module.AIProviderConfig(
            provider_name="deepseek",
            provider_mode="live",
            default_model="deepseek-chat",
            is_enabled=True,
            is_default=False,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(provider)
        eval_run = app_module.EvaluationRun(
            evaluation_set_id=None,
            provider="deepseek",
            provider_name="deepseek",
            provider_mode="live",
            model_name="deepseek-chat",
            prompt_key="term_alignment",
            prompt_version="v1",
            alignment_accuracy=0.9,
            auto_approval_error_rate=0.0,
            no_evidence_forced_alignment_rate=0.0,
            status="completed",
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(eval_run)
        app_module.db.session.flush()
        model = app_module.AIModelRegistry(
            provider_name="deepseek",
            provider_mode="live",
            model_name="deepseek-chat",
            is_enabled=True,
            last_evaluation_run_id=eval_run.id,
            last_evaluation_score=0.9,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(model)
        app_module.ensure_ai_registry_seed()
        app_module.db.session.flush()
        assert app_module.can_use_model_for_auto_approval("deepseek", "deepseek-chat", "v1")[0] is True

        alignment = finalize_alignment_decision({
            "english_term": "Evaluated Alignment Term",
            "final_chinese_term": "傅里叶变换",
            "alignment_status": "exact_match",
            "confidence_score": 96,
            "english_evidence_items": evidence(0.92, "en"),
            "chinese_evidence_items": evidence(0.91, "zh"),
            "ai_provider": "deepseek",
            "ai_provider_mode": "live",
            "ai_model": "deepseek-chat",
            "provider_status": "real_provider",
            "is_real_provider": True,
            "prompt_key": "term_alignment",
            "prompt_version": "v1",
            "ai_call_log_id": 77,
        })
        card = app_module.create_or_update_card_from_alignment(
            "Evaluated Alignment Term",
            alignment,
            scope_type="course",
            course_id=course.id,
        )
        assert card.status == "auto_approved"
        assert card.ai_provider == "deepseek"
        assert card.ai_provider_mode == "live"
        assert card.ai_model == "deepseek-chat"
        assert card.prompt_key == "term_alignment"
        assert card.prompt_version == "v1"
        assert card.ai_call_log_id == 77


def test_model_without_evaluation_is_not_auto_approval_eligible(app_module):
    with app_module.app.app_context():
        app_module.db.session.add(app_module.AIProviderConfig(
            provider_name="deepseek",
            provider_mode="live",
            default_model="unvalidated",
            is_enabled=True,
            created_at=app_module.current_time_text(),
        ))
        app_module.db.session.add(app_module.AIModelRegistry(
            provider_name="deepseek",
            provider_mode="live",
            model_name="unvalidated",
            is_enabled=True,
            created_at=app_module.current_time_text(),
        ))
        app_module.db.session.commit()
        allowed, reasons = app_module.can_use_model_for_auto_approval("deepseek", "unvalidated", "v1")
        assert allowed is False
        assert any("evaluation" in reason for reason in reasons)
