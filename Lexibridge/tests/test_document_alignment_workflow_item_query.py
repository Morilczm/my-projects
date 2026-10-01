from dataclasses import FrozenInstanceError

import pytest

from services.document_alignment_workflow_queries import (
    DocumentAlignmentQueryActor,
    DocumentAlignmentWorkflowQueryDependencies,
    ListDocumentAlignmentWorkflowItemsCommand,
    list_document_alignment_workflow_items,
)

from document_alignment_workflow_query_support import cleanup, create_scenario


def _list(app_module, scenario, **kwargs):
    values = {
        "run_uid": scenario["run_uid"],
        "actor": DocumentAlignmentQueryActor(str(scenario["requester_id"]), "teacher"),
    }
    values.update(kwargs)
    return list_document_alignment_workflow_items(
        ListDocumentAlignmentWorkflowItemsCommand(**values),
        DocumentAlignmentWorkflowQueryDependencies.from_app_module(app_module),
    )


def test_item_pagination_is_database_ordered_and_bounded(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(app_module, item_count=25, ready=7, blocked=6, failed=6)
        first = _list(app_module, scenario, page=1, page_size=20)
        second = _list(app_module, scenario, page=2, page_size=20)
        empty = _list(app_module, scenario, page=3, page_size=20)

        assert first.outcome == second.outcome == empty.outcome == "found"
        assert len(first.page.items) == 20
        assert len(second.page.items) == 5
        assert empty.page.items == ()
        assert first.page.total_items == 25
        assert first.page.total_pages == 2
        assert first.page.has_next is True
        assert second.page.has_previous is True
        assert [item.candidate_term for item in first.page.items] == [f"Term {index:03d}" for index in range(20)]
        item = first.page.items[0]
        assert item.source_chunk_count == 2
        assert item.risk_labels == ("evidence_gap", "translation_risk")
        assert not hasattr(item, "item_key")
        assert not hasattr(item, "execution_key")
        assert not hasattr(item, "source_chunk_ids")
        assert not hasattr(item, "id")
        with pytest.raises(FrozenInstanceError):
            item.status = "failed"
        cleanup(app_module)


def test_item_filters_and_validation(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
        scenario = create_scenario(app_module, item_count=8)

        reviewable = _list(app_module, scenario, reviewable_only=True)
        blocked = _list(app_module, scenario, status="blocked")
        assert {item.status for item in reviewable.page.items} == {"needs_review"}
        assert {item.status for item in blocked.page.items} == {"blocked"}
        assert _list(app_module, scenario, page=0).outcome == "invalid_request"
        assert _list(app_module, scenario, page_size=101).outcome == "invalid_request"
        assert _list(app_module, scenario, status="approved").outcome == "invalid_request"
        cleanup(app_module)
