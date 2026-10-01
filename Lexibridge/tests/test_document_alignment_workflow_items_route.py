import pytest

from document_alignment_workflow_query_support import cleanup as cleanup_query, create_scenario
from document_alignment_workflow_route_support import bearer, token_for_user


@pytest.fixture(autouse=True)
def clean_query_state(app_module):
    with app_module.app.app_context():
        cleanup_query(app_module)
    yield
    with app_module.app.app_context():
        cleanup_query(app_module)


def _route_state(app_module, item_count=25):
    scenario = create_scenario(app_module, item_count=item_count, ready=7, blocked=6, failed=6)
    token = token_for_user(app_module, scenario["requester_id"])
    return scenario, token


def test_default_and_explicit_pagination_are_stable(client, app_module):
    with app_module.app.app_context():
        scenario, token = _route_state(app_module)
    path = f"/api/document-alignment-runs/{scenario['run_uid']}/items"
    default = client.get(path, headers=bearer(token))
    second = client.get(f"{path}?page=2&page_size=10", headers=bearer(token))
    repeat = client.get(f"{path}?page=2&page_size=10", headers=bearer(token))

    assert default.status_code == second.status_code == repeat.status_code == 200
    assert len(default.get_json()["data"]["items"]) == 20
    assert second.get_json()["data"]["pagination"] == {
        "page": 2,
        "page_size": 10,
        "total_items": 25,
        "total_pages": 3,
        "has_next": True,
        "has_previous": True,
    }
    assert [item["item_uid"] for item in second.get_json()["data"]["items"]] == [
        item["item_uid"] for item in repeat.get_json()["data"]["items"]
    ]


def test_status_and_reviewable_filters(client, app_module):
    with app_module.app.app_context():
        scenario, token = _route_state(app_module, 8)
    path = f"/api/document-alignment-runs/{scenario['run_uid']}/items"
    blocked = client.get(f"{path}?status=blocked", headers=bearer(token))
    reviewable = client.get(f"{path}?reviewable_only=true", headers=bearer(token))
    false_filter = client.get(f"{path}?reviewable_only=false", headers=bearer(token))
    assert {item["status"] for item in blocked.get_json()["data"]["items"]} == {"blocked"}
    assert {item["status"] for item in reviewable.get_json()["data"]["items"]} == {"needs_review"}
    assert false_filter.get_json()["data"]["pagination"]["total_items"] == 8


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=abc",
        "page_size=0",
        "page_size=101",
        "status=unknown",
        "reviewable_only=1",
        "reviewable_only=True",
        "reviewable_only=yes",
        "page=1&page=2",
        "order_by=status",
    ],
)
def test_invalid_query_values_are_rejected(client, app_module, query):
    with app_module.app.app_context():
        scenario, token = _route_state(app_module, 1)
    response = client.get(
        f"/api/document-alignment-runs/{scenario['run_uid']}/items?{query}",
        headers=bearer(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "DOCUMENT_ALIGNMENT_QUERY_INVALID_REQUEST"


def test_item_page_hides_internal_identity_and_content(client, app_module, student_token):
    with app_module.app.app_context():
        scenario, token = _route_state(app_module, 3)
    path = f"/api/document-alignment-runs/{scenario['run_uid']}/items"
    response = client.get(path, headers=bearer(token))
    assert response.status_code == 200
    text = str(response.get_json()).casefold()
    for forbidden in (
        "execution_key",
        "input_fingerprint",
        "preflight_uid",
        "usage_uid",
        "audit_identity",
        "source_chunk_ids",
        "chunk text",
        "lease_token",
        "worker_id",
    ):
        assert forbidden not in text
    assert client.get(path, headers=bearer(student_token)).status_code == 403


def test_empty_page_is_success(client, app_module):
    with app_module.app.app_context():
        scenario, token = _route_state(app_module, 2)
    response = client.get(
        f"/api/document-alignment-runs/{scenario['run_uid']}/items?page=99",
        headers=bearer(token),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["items"] == []


def test_get_items_rejects_request_body(client, app_module):
    with app_module.app.app_context():
        scenario, token = _route_state(app_module, 1)
    response = client.get(
        f"/api/document-alignment-runs/{scenario['run_uid']}/items",
        data='{"unexpected":true}',
        content_type="application/json",
        headers=bearer(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "DOCUMENT_ALIGNMENT_QUERY_INVALID_REQUEST"
