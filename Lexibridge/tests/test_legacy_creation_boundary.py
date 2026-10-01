from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_set(app_module):
    return {
        "alignment_runs": app_module.AlignmentRun.query.count(),
        "jobs": app_module.BackgroundJob.query.count(),
        "job_events": app_module.BackgroundJobEvent.query.count(),
        "cards": app_module.TerminologyCard.query.count(),
    }


def test_disabled_legacy_route_admission_returns_503_with_zero_writes(
    app_module,
    client,
    teacher_token,
    test_course,
    monkeypatch,
):
    with app_module.app.app_context():
        before = _write_set(app_module)

    monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED", False)
    response = client.post(
        "/api/alignment/run",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={
            "english_term": "legacy-admission-boundary-9c5n1",
            "course_id": test_course.id,
            "scope_type": "course",
        },
    )

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "error",
        "error_code": "LEGACY_ALIGNMENT_ADMISSION_DISABLED",
        "message": "Legacy alignment admission is disabled; use the formal document alignment workflow.",
        "details": {},
    }
    with app_module.app.app_context():
        assert _write_set(app_module) == before


def test_admission_control_is_default_enabled_and_does_not_change_route_contract(app_module):
    assert app_module.LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED is True
    rules = {
        (rule.rule, method, rule.endpoint)
        for rule in app_module.app.url_map.iter_rules()
        for method in rule.methods
        if rule.rule == "/api/alignment/run" and method not in {"HEAD", "OPTIONS"}
    }
    assert rules == {("/api/alignment/run", "POST", "run_alignment")}


def test_creation_boundary_documents_all_non_test_production_entries():
    boundary = (ROOT / "docs" / "legacy_creation_boundary.md").read_text(encoding="utf-8")
    for expected in (
        "POST /api/alignment/run",
        "POST /api/documents/upload?sync=true",
        "run_alignment_for_chunks",
        "Production compatibility",
        "Migration only",
        "Test only",
        "Obsolete",
        "LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED",
        "LEGACY_ALIGNMENT_CREATION_FREEZE_BOUNDARY_COMPLETE",
    ):
        assert expected in boundary


def test_openapi_preserves_operation_and_documents_reversible_admission_state():
    text = (ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8")
    operation = text.split("  /api/alignment/run:", 1)[1].split("\n  /api/alignment/runs:", 1)[0]
    assert "deprecated: true" in operation
    assert "LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=false" in operation
    assert "LEGACY_ALIGNMENT_ADMISSION_DISABLED" in operation
    assert '"503"' in operation
    assert "410" in operation
