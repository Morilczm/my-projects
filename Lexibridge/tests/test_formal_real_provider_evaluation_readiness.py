from types import SimpleNamespace

import pytest

from scripts.evaluations.bilingual_knowledge_quality import runner


def _prepared(concept_id):
    return SimpleNamespace(
        outcome="prepared",
        error_code="",
        candidate_count=2,
        english_evidence_refs=("en-1",),
        chinese_evidence_refs=("zh-1",),
        prepared_input=SimpleNamespace(concept_id=concept_id),
    )


def _blocked():
    return SimpleNamespace(
        outcome="evidence_insufficient",
        error_code="DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT",
        candidate_count=3,
        english_evidence_refs=(),
        chinese_evidence_refs=("zh-1",),
        prepared_input=None,
    )


def test_scan_uses_formal_preparation_and_never_calls_provider():
    calls = {"prepare": [], "provider": 0}

    def prepare(concept_id):
        calls["prepare"].append(concept_id)
        return _blocked() if concept_id == "physics-07" else _prepared(concept_id)

    rows = runner.scan_formal_provider_readiness(
        ("physics-07", "physics-21"),
        prepare_item=prepare,
    )

    assert calls == {"prepare": ["physics-07", "physics-21"], "provider": 0}
    assert [row.provider_ready for row in rows] == [False, True]
    assert rows[0].rejection_code == "DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT"


def test_selector_is_first_ready_in_frozen_order_and_has_no_gold_parameter():
    rows = (
        runner.FormalProviderReadiness("physics-07", False, "evidence_insufficient"),
        runner.FormalProviderReadiness("physics-21", True, "prepared"),
        runner.FormalProviderReadiness("physics-22", True, "prepared"),
    )

    selected = runner.select_formal_provider_preflight(rows, ("physics-07", "physics-21", "physics-22"))

    assert selected.concept_id == "physics-21"
    assert selected.selection_reason == "first_provider_ready_in_frozen_order"


def test_no_ready_item_fails_closed_without_provider_result():
    rows = (runner.FormalProviderReadiness("physics-07", False, "evidence_insufficient"),)

    with pytest.raises(runner.FormalProviderReadinessError) as exc:
        runner.select_formal_provider_preflight(rows, ("physics-07",))

    assert exc.value.error_code == "FORMAL_PROVIDER_PREFLIGHT_NO_READY_ITEM"
