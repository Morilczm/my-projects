from types import SimpleNamespace

from services.cost_control import check_quota, estimated_cost_for, record_usage_event, summarize_usage


def test_estimated_cost_and_summary():
    records = [
        SimpleNamespace(action_type="ocr_page", units_used=2),
        SimpleNamespace(action_type="ai_alignment_call", units_used=3),
        SimpleNamespace(action_type="formula_ocr_call", units_used=1),
        SimpleNamespace(action_type="pdf_export", units_used=1),
    ]
    summary = summarize_usage(records)
    assert summary["ocr_pages"] == 2
    assert summary["ai_calls"] == 3
    assert summary["formula_ocr_calls"] == 1
    assert summary["pdf_exports"] == 1
    assert estimated_cost_for("ocr_page", 2) > 0


def test_quota_exceeded():
    records = [SimpleNamespace(action_type="ocr_page", units_used=5)]
    result = check_quota(records, {"monthly_pages": 5}, "ocr_page", 1)
    assert result.allowed is False
    assert result.error_code == "QUOTA_EXCEEDED"


def test_record_usage_event(app_module):
    with app_module.app.app_context():
        user = app_module.User.query.first()
        result = record_usage_event(
            app_module.db.session,
            app_module.UsageRecord,
            user.id,
            "formula_ocr_call",
            units=2,
            provider="none",
            metadata={"source": "test"},
        )
        app_module.db.session.commit()
        assert result["event_type"] == "formula_ocr_call"
        assert result["estimated_cost"] > 0
        assert app_module.UsageRecord.query.filter_by(user_id=user.id, action_type="formula_ocr_call").count() >= 1
