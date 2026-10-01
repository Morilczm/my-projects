import inspect

from services import (
    document_alignment_item_preparation,
    translate_provider,
)


def test_translation_and_glossary_results_are_generated_hints_without_evidence(
    monkeypatch,
):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "none")

    glossary = translate_provider.translate_term(
        "rotational inertia",
        glossary={"rotational inertia": "转动惯量"},
    )
    unavailable = translate_provider.translate_term("electric current")

    for result in (glossary, unavailable):
        assert result["generated"] is True
        assert result["no_evidence"] is True
        assert result["provenance_type"] == "GENERATED_HINT"
        assert result["eligible_as_chinese_evidence"] is False
        assert result["eligible_as_canonical_term"] is False
        assert result["eligible_for_qualification"] is False
        assert result["eligible_for_provider_readiness"] is False


def test_formal_preparation_does_not_import_or_call_translation_provider():
    source = inspect.getsource(document_alignment_item_preparation)

    assert "translate_provider" not in source
    assert "translate_term(" not in source
    assert "glossary" not in source


def test_generated_hint_risk_cannot_auto_approve_legacy_alignment(app_module):
    with app_module.app.app_context():
        alignment = {
            "english_term": "rotational inertia",
            "english_kb_evidence": "bounded English evidence",
            "chinese_kb_evidence": "bounded Chinese evidence",
            "english_evidence_score": 0.99,
            "chinese_evidence_score": 0.99,
            "confidence_score": 99,
            "alignment_status": "exact_match",
            "ai_model": "approved-model",
            "provider_status": "real_provider",
            "review_status": "auto_approved",
            "translation_hint": {
                "generated": True,
                "no_evidence": True,
                "provenance_type": "GENERATED_HINT",
            },
        }

        flags = app_module.quality_flags_for_alignment(alignment)

        assert "generated_translation_hint" in flags
        assert app_module.card_status_from_alignment(alignment) == (
            "pending_quality_control"
        )
