from services import student_first_boundaries as boundaries


def _result(status, **overrides):
    value = {
        "alignment_result_uid": "alignment-1",
        "workspace_scope": "MANAGED_COURSE",
        "alignment_status": status,
        "english_term": "mass",
        "chinese_term": "质量",
        "english_evidence": [{"source_uid": "en", "chunk_uid": "en-c", "snippet": "bounded"}],
        "chinese_evidence": [{"source_uid": "zh", "chunk_uid": "zh-c", "snippet": "有限"}],
        "chinese_candidates": [
            {"text": "质量", "evidence_backed": True, "generated": False},
            {"text": "重量", "evidence_backed": True, "generated": False},
        ],
    }
    value.update(overrides)
    return boundaries.serialize_student_alignment_result(value)


def test_ready_maps_to_evidence_backed_recommendation():
    payload = _result("READY")
    assert payload["display_mode"] == "EVIDENCE_BACKED_RECOMMENDATION"
    assert payload["uncertain"] is False
    assert payload["authority"] == "NON_OFFICIAL"


def test_review_required_maps_to_bounded_alternatives_without_blocking_learning():
    payload = _result("REVIEW_REQUIRED")
    assert payload["display_mode"] == "EVIDENCE_BACKED_ALTERNATIVES"
    assert payload["uncertain"] is True
    assert payload["student_access_allowed"] is True
    assert len(payload["chinese_candidates"]) == 2


def test_not_ready_does_not_expose_a_canonical_chinese_term():
    payload = _result("NOT_READY")
    assert payload["display_mode"] == "NO_RELIABLE_ALIGNMENT"
    assert payload["chinese_term"] == ""


def test_generated_hint_is_non_evidence_non_official_and_cannot_be_canonical():
    payload = _result(
        "NOT_READY",
        chinese_term="机器提示",
        chinese_candidates=[],
        generated_hints=[
            {
                "text": "机器提示",
                "generated": True,
                "no_evidence": True,
                "provenance_type": "GENERATED_HINT",
                "provider_id": "local",
                "provider_version": "v1",
            }
        ],
    )
    hint = payload["generated_hints"][0]
    assert payload["chinese_term"] == ""
    assert hint["generated"] is True
    assert hint["evidence_backed"] is False
    assert hint["authority"] == "NON_OFFICIAL"


def test_student_serializer_omits_internal_and_secret_fields():
    payload = _result(
        "READY",
        api_key="secret",
        prompt_text="full prompt",
        raw_json={"secret": True},
        pairing_component_scores={"internal": 1},
        provider_secret="secret",
    )
    serialized = repr(payload).lower()
    for forbidden in ("api_key", "full prompt", "provider_secret", "pairing_component_scores", "raw_json"):
        assert forbidden not in serialized
