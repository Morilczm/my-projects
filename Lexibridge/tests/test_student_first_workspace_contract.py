import pytest

from services import student_first_boundaries as boundaries


def test_student_can_hold_personal_and_managed_course_memberships():
    memberships = boundaries.validate_workspace_memberships(
        [
            {"workspace_uid": "personal:u-1", "workspace_scope": "PERSONAL", "member_role": "STUDENT"},
            {"workspace_uid": "course:mechanics", "workspace_scope": "MANAGED_COURSE", "member_role": "STUDENT"},
        ],
        actor_uid="u-1",
    )
    assert {item["workspace_scope"] for item in memberships} == {"PERSONAL", "MANAGED_COURSE"}


@pytest.mark.parametrize("scope", ["PERSONAL", "MANAGED_COURSE"])
def test_both_workspaces_use_the_same_alignment_serializer(scope):
    payload = boundaries.serialize_student_alignment_result(
        {
            "alignment_result_uid": "alignment-1",
            "workspace_scope": scope,
            "alignment_status": "READY",
            "english_term": "electric potential",
            "chinese_term": "电势",
            "english_evidence": [{"source_uid": "en-1", "chunk_uid": "en-c1", "snippet": "bounded"}],
            "chinese_evidence": [{"source_uid": "zh-1", "chunk_uid": "zh-c1", "snippet": "有限证据"}],
            "chinese_candidates": [],
        }
    )
    assert payload["contract_id"] == boundaries.STUDENT_ALIGNMENT_RESULT_CONTRACT_ID
    assert payload["workspace_scope"] == scope
    assert payload["visibility"] == "PRIVATE"
    assert payload["authority"] == "NON_OFFICIAL"
    assert payload["publication_status"] == "NOT_APPLICABLE"


def test_personal_and_managed_query_defaults_are_private_non_official():
    for scope in ("PERSONAL", "MANAGED_COURSE"):
        state = boundaries.validate_result_dimensions(
            workspace_scope=scope,
            visibility="PRIVATE",
            authority="NON_OFFICIAL",
            alignment_status="REVIEW_REQUIRED",
            publication_status="NOT_APPLICABLE",
            content_kind="PERSONAL_LEARNING_RESULT",
        )
        assert state.visibility == "PRIVATE"
        assert state.authority == "NON_OFFICIAL"


@pytest.mark.parametrize(
    "values",
    [
        dict(workspace_scope="PERSONAL", visibility="COURSE_SHARED", authority="NON_OFFICIAL", publication_status="NOT_APPLICABLE"),
        dict(workspace_scope="PERSONAL", visibility="PRIVATE", authority="OFFICIAL", publication_status="DRAFT"),
        dict(workspace_scope="MANAGED_COURSE", visibility="PRIVATE", authority="NON_OFFICIAL", publication_status="PUBLISHED"),
    ],
)
def test_illegal_state_combinations_are_rejected(values):
    with pytest.raises(boundaries.BoundaryContractError):
        boundaries.validate_result_dimensions(
            alignment_status="READY",
            content_kind="PERSONAL_LEARNING_RESULT",
            **values,
        )


def test_official_course_card_requires_managed_course_reviewer_and_shared_visibility():
    state = boundaries.validate_result_dimensions(
        workspace_scope="MANAGED_COURSE",
        visibility="COURSE_SHARED",
        authority="OFFICIAL",
        alignment_status="READY",
        publication_status="DRAFT",
        content_kind="OFFICIAL_COURSE_CARD",
        actor_role="reviewer",
        reviewer_decision_uid="review-1",
    )
    assert state.authority == "OFFICIAL"
    with pytest.raises(boundaries.BoundaryContractError):
        boundaries.validate_result_dimensions(
            workspace_scope="MANAGED_COURSE",
            visibility="COURSE_SHARED",
            authority="OFFICIAL",
            alignment_status="READY",
            publication_status="PUBLISHED",
            content_kind="OFFICIAL_COURSE_CARD",
            actor_role="student",
            reviewer_decision_uid="",
        )


def test_personal_learning_record_never_auto_upgrades_to_official_card():
    record = boundaries.personal_learning_record_contract(
        student_uid="student-1",
        workspace_uid="course-1",
        workspace_scope="MANAGED_COURSE",
        alignment_result_uid="alignment-1",
    )
    assert record["visibility"] == "PRIVATE"
    assert record["authority"] == "NON_OFFICIAL"
    assert record["publication_status"] == "NOT_APPLICABLE"
    assert record["requires_human_review"] is False
