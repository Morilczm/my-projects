from types import SimpleNamespace

import pytest

from scripts.evaluations.bilingual_knowledge_quality import runner


def _benchmark(count=25):
    return tuple(
        runner.FrozenBenchmarkIdentity(
            concept_id=f"physics-{index:02d}",
            binding_term=f"benchmark term {index}",
        )
        for index in range(1, count + 1)
    )


def _candidate(index, *, suffix=""):
    return runner.ProductionCandidateBindingInput(
        candidate_id=f"candidate-{index}{suffix}",
        candidate_term=f"benchmark term {index}",
        system_payload={"candidate_id": f"candidate-{index}{suffix}"},
    )


def _prepared(candidate):
    return SimpleNamespace(
        outcome="prepared",
        error_code="",
        candidate_count=1,
        english_evidence_refs=("en-1",),
        chinese_evidence_refs=("zh-1",),
        prepared_input={"candidate_id": candidate.candidate_id},
    )


def test_frozen_rows_survive_when_production_extractor_matches_only_three():
    benchmark = _benchmark()
    candidates = tuple(_candidate(index) for index in (23, 24, 25))
    execution_inputs = []

    rows = runner.build_frozen_evaluation_bootstrap(
        benchmark,
        candidates,
        prepare_candidate=lambda candidate: execution_inputs.append(candidate)
        or _prepared(candidate),
    )

    assert len(rows) == 25
    assert sum(row.binding_status == "matched" for row in rows) == 3
    assert sum(row.execution_status == "upstream_not_ready" for row in rows) == 22
    assert all(row.included_in_denominator for row in rows)
    assert all(row.provider_called is False for row in rows)
    assert [candidate.candidate_id for candidate in execution_inputs] == [
        "candidate-23",
        "candidate-24",
        "candidate-25",
    ]


def test_missing_and_ambiguous_bindings_are_item_failures_not_global_stops():
    benchmark = _benchmark(3)
    candidates = (_candidate(2), _candidate(3), _candidate(3, suffix="-duplicate"))

    rows = runner.build_frozen_evaluation_bootstrap(
        benchmark,
        candidates,
        prepare_candidate=_prepared,
    )

    assert [row.binding_status for row in rows] == ["missing", "matched", "ambiguous"]
    assert rows[0].primary_attribution == "CANDIDATE_EXTRACTION_DEFECT"
    assert rows[2].primary_attribution == "CANDIDATE_EXTRACTION_DEFECT"
    assert rows[0].provider_called is False
    assert rows[2].provider_called is False
    assert len(rows) == 3


def test_gold_binding_term_never_enters_system_execution_payload():
    benchmark = (
        runner.FrozenBenchmarkIdentity("physics-01", "Gold-only English term"),
    )
    candidate = runner.ProductionCandidateBindingInput(
        "candidate-system-1",
        "gold-only english term",
        {"candidate_id": "candidate-system-1", "query": "system-derived query"},
    )
    seen = []

    rows = runner.build_frozen_evaluation_bootstrap(
        benchmark,
        (candidate,),
        prepare_candidate=lambda value: seen.append(value.system_payload)
        or _prepared(value),
    )

    assert rows[0].binding_status == "matched"
    assert seen == [{"candidate_id": "candidate-system-1", "query": "system-derived query"}]
    assert "binding_term" not in seen[0]
    assert "Gold-only English term" not in repr(seen)


def test_preflight_selects_first_ready_row_and_no_ready_fails_closed():
    benchmark = _benchmark(3)
    candidates = (_candidate(2), _candidate(3))
    rows = runner.build_frozen_evaluation_bootstrap(
        benchmark,
        candidates,
        prepare_candidate=lambda candidate: (
            _prepared(candidate)
            if candidate.candidate_id == "candidate-3"
            else SimpleNamespace(
                outcome="evidence_insufficient",
                error_code="DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT",
                candidate_count=1,
                english_evidence_refs=(),
                chinese_evidence_refs=("zh-1",),
                prepared_input=None,
            )
        ),
    )

    selected = runner.select_frozen_evaluation_preflight(rows)
    assert selected.concept_id == "physics-03"

    with pytest.raises(runner.FormalProviderReadinessError) as exc:
        runner.select_frozen_evaluation_preflight(rows[:2])
    assert exc.value.error_code == "FORMAL_PROVIDER_PREFLIGHT_NO_READY_ITEM"
