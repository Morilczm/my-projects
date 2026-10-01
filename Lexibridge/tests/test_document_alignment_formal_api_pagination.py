import pytest

from scripts.formal_document_alignment_api_e2e_support import (
    cleanup_formal_api_state,
    create_formal_source,
    http_json,
    login,
    start_threaded_server,
)


PAGINATION_TERMS = (
    "Abstraction",
    "Approximation",
    "Calibration",
    "Classification",
    "Computation",
    "Correlation",
    "Definition",
    "Demodulation",
    "Differentiation",
    "Estimation",
    "Formation",
    "Generation",
    "Integration",
    "Interpolation",
    "Modulation",
    "Normalization",
    "Optimization",
    "Prediction",
    "Quantization",
    "Regularization",
    "Representation",
    "Segmentation",
    "Simulation",
    "Synchronization",
    "Transformation",
)


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)
    yield
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)


def test_real_http_item_pagination_is_stable_and_bounded(app_module):
    with app_module.app.app_context():
        source = create_formal_source(
            app_module,
            suffix="pagination",
            terms=PAGINATION_TERMS,
            bilingual_terms={term: f"术语{index:02d}" for index, term in enumerate(PAGINATION_TERMS)},
        )

    with start_threaded_server(app_module.app) as server:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        started = http_json(
            server.base_url,
            "/api/document-alignment-runs",
            method="POST",
            token=teacher.token,
            body={"source_uid": source.source_uid},
            headers={"Idempotency-Key": "pagination-key"},
        )
        assert started.status == 202
        run_uid = started.body["data"]["run_uid"]
        with app_module.app.app_context():
            result = app_module.run_formal_worker_once(worker_id="pagination-worker")
            assert result.outcome == "completed"

        path = f"/api/document-alignment-runs/{run_uid}/items"
        page_one = http_json(server.base_url, f"{path}?page=1&page_size=20", token=teacher.token)
        page_two = http_json(server.base_url, f"{path}?page=2&page_size=20", token=teacher.token)
        repeated = http_json(server.base_url, f"{path}?page=1&page_size=20", token=teacher.token)

        assert page_one.status == page_two.status == repeated.status == 200
        first_items = page_one.body["data"]["items"]
        second_items = page_two.body["data"]["items"]
        assert len(first_items) == 20
        assert len(second_items) == 5
        assert page_one.body["data"]["pagination"] == {
            "page": 1,
            "page_size": 20,
            "total_items": 25,
            "total_pages": 2,
            "has_next": True,
            "has_previous": False,
        }
        assert page_two.body["data"]["pagination"]["has_previous"] is True
        assert page_two.body["data"]["pagination"]["has_next"] is False
        assert {item["item_uid"] for item in first_items}.isdisjoint(
            item["item_uid"] for item in second_items
        )
        assert [item["item_uid"] for item in repeated.body["data"]["items"]] == [
            item["item_uid"] for item in first_items
        ]

        for query in (
            "page=0",
            "page_size=0",
            "page_size=101",
            "status=not-a-status",
            "reviewable_only=yes",
        ):
            assert http_json(
                server.base_url,
                f"{path}?{query}",
                token=teacher.token,
            ).status == 400
