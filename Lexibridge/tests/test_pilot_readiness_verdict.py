import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_readiness_module():
    spec = importlib.util.spec_from_file_location("pilot_readiness_check", ROOT / "scripts" / "pilot_readiness_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ready_with_conditions_when_trial_boundaries_remain():
    module = load_readiness_module()
    checks = [{"name": "all checks", "status": "PASS", "returncode": 0}]
    conditions = ["sqlite_database", "flask_development_server"]
    assert module.compute_readiness_verdict(checks, conditions) == module.READY_WITH_CONDITIONS


def test_blocking_failure_is_not_ready():
    module = load_readiness_module()
    checks = [{"name": "backup restore", "status": "FAIL", "returncode": 1}]
    assert module.compute_readiness_verdict(checks, ["sqlite_database"]) == module.NOT_READY


def test_ready_only_when_no_conditions_and_all_checks_pass():
    module = load_readiness_module()
    checks = [{"name": "all checks", "status": "PASS", "returncode": 0}]
    assert module.compute_readiness_verdict(checks, []) == module.READY


def test_conditions_prevent_unqualified_ready():
    module = load_readiness_module()
    checks = [{"name": "all checks", "status": "PASS", "returncode": 0}]
    payload = module.build_readiness_payload(
        profile="small-pilot",
        checks=checks,
        conditions=["external_llm_disabled"],
        warnings=[],
    )
    assert payload["verdict"] == module.READY_WITH_CONDITIONS
    assert payload["conditions"]


def test_browser_e2e_unavailable_is_condition_not_pass():
    module = load_readiness_module()
    checks = [
        {"name": "browser e2e", "status": "UNAVAILABLE", "returncode": module.E2E_ENVIRONMENT_UNAVAILABLE}
    ]
    payload = module.build_readiness_payload(
        profile="small-pilot",
        checks=checks,
        conditions=["browser_e2e_not_executed"],
        warnings=["browser_e2e_not_executed"],
    )
    assert payload["verdict"] == module.READY_WITH_CONDITIONS
    assert payload["blocking_failures"] == []


def test_browser_e2e_pass_is_not_not_executed_condition():
    module = load_readiness_module()
    payload = module.build_readiness_payload(
        profile="small-pilot",
        checks=[{"name": "browser e2e", "status": "PASS", "returncode": 0}],
        conditions=["sqlite_database", "flask_development_server"],
        warnings=[],
        browser_e2e={
            "browser_e2e_status": "PASS",
            "browser_name": "chromium",
            "browser_version": "148.0.7778.96",
            "student_flow_status": "PASS",
            "teacher_flow_status": "PASS",
            "js_error_count": 0,
            "external_dependency_count": 0,
            "blocked_external_request_count": 2,
        },
    )
    assert payload["verdict"] == module.READY_WITH_CONDITIONS
    assert "browser_e2e_not_executed" not in payload["conditions"]
    assert payload["browser_e2e"]["browser_e2e_status"] == "PASS"


def test_json_payload_verdict_is_stable(tmp_path):
    module = load_readiness_module()
    payload = module.build_readiness_payload(
        profile="small-pilot",
        checks=[{"name": "release safety", "status": "PASS", "returncode": 0}],
        conditions=module.default_conditions("small-pilot"),
        warnings=[],
    )
    output = tmp_path / "pilot-result.json"
    output.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["verdict"] == module.READY_WITH_CONDITIONS
    assert loaded["profile"] == "small-pilot"


def test_report_verdict_matches_script_semantics():
    module = load_readiness_module()
    report = (ROOT / "docs" / "pilot_readiness_report.md").read_text(encoding="utf-8")
    assert "READY WITH CONDITIONS" in report
    payload = module.build_readiness_payload(
        profile="small-pilot",
        checks=[{"name": "all pilot gates", "status": "PASS", "returncode": 0}],
        conditions=module.default_conditions("small-pilot"),
        warnings=[],
    )
    assert payload["verdict"] == "READY_WITH_CONDITIONS"


def test_external_llm_disabled_and_demo_performance_are_conditions_not_blockers():
    module = load_readiness_module()
    checks = [
        {"name": "provider network-disabled check", "status": "PASS", "returncode": 0},
        {"name": "lightweight performance smoke", "status": "WARN", "returncode": 0},
    ]
    payload = module.build_readiness_payload(
        profile="small-pilot",
        checks=checks,
        conditions=["external_llm_disabled", "demo_scale_performance_only"],
        warnings=["demo_scale_performance_only"],
    )
    assert payload["verdict"] == module.READY_WITH_CONDITIONS
    assert payload["blocking_failures"] == []
