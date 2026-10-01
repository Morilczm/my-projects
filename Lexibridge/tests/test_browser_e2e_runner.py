import builtins
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_runner_module():
    spec = importlib.util.spec_from_file_location("run_browser_e2e", ROOT / "scripts" / "run_browser_e2e.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_readiness_module():
    spec = importlib.util.spec_from_file_location("pilot_readiness_check", ROOT / "scripts" / "pilot_readiness_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def passing_flow(module, name):
    flow = module.flow_result(name)
    flow["status"] = "PASS"
    module.add_step(flow, "sample step")
    return flow


def test_flow_result_json_schema_shape():
    module = load_runner_module()
    flow = module.flow_result("student")
    assert flow["name"] == "student"
    assert flow["status"] == "SKIPPED"
    for key in ["steps", "console_errors", "page_errors", "failed_requests", "downloads", "requests"]:
        assert isinstance(flow[key], list)


def test_overall_pass_requires_requested_flows_to_pass():
    module = load_runner_module()
    instructor = passing_flow(module, "instructor")
    result = module.build_overall_result(
        student_flow=passing_flow(module, "student"),
        instructor_flow=instructor,
        reviewer_flow=passing_flow(module, "reviewer"),
        blocked_external_requests=[],
    )
    assert result["status"] == "PASS"
    assert result["student_flow"]["status"] == "PASS"
    assert result["instructor_flow"]["status"] == "PASS"
    assert result["reviewer_flow"]["status"] == "PASS"
    assert result["teacher_flow"] == instructor
    assert result["teacher_flow_compatibility"] == "instructor_flow_alias"


def test_student_failure_makes_overall_fail():
    module = load_runner_module()
    student = passing_flow(module, "student")
    student["status"] = "FAIL"
    result = module.build_overall_result(
        student_flow=student,
        instructor_flow=passing_flow(module, "instructor"),
        reviewer_flow=passing_flow(module, "reviewer"),
        blocked_external_requests=[],
    )
    assert result["status"] == "FAIL"


def test_instructor_or_reviewer_failure_makes_overall_fail():
    module = load_runner_module()
    instructor = passing_flow(module, "instructor")
    instructor["status"] = "FAIL"
    result = module.build_overall_result(
        student_flow=passing_flow(module, "student"),
        instructor_flow=instructor,
        reviewer_flow=passing_flow(module, "reviewer"),
        blocked_external_requests=[],
    )
    assert result["status"] == "FAIL"
    reviewer = passing_flow(module, "reviewer")
    reviewer["status"] = "FAIL"
    result = module.build_overall_result(
        student_flow=passing_flow(module, "student"),
        instructor_flow=passing_flow(module, "instructor"),
        reviewer_flow=reviewer,
        blocked_external_requests=[],
    )
    assert result["status"] == "FAIL"


def test_console_error_makes_flow_and_overall_fail():
    module = load_runner_module()
    reviewer = passing_flow(module, "reviewer")
    reviewer["console_errors"].append("Unhandled browser error")
    assert module.flow_has_failures(reviewer, []) is True
    result = module.build_overall_result(
        student_flow=passing_flow(module, "student"),
        instructor_flow=passing_flow(module, "instructor"),
        reviewer_flow=reviewer,
        blocked_external_requests=[],
    )
    assert result["status"] == "FAIL"


def test_external_page_dependency_makes_overall_fail():
    module = load_runner_module()
    blocked = [{"flow": "student", "source": "page", "url": "https://cdn.example.invalid/app.js"}]
    result = module.build_overall_result(
        student_flow=passing_flow(module, "student"),
        instructor_flow=passing_flow(module, "instructor"),
        reviewer_flow=passing_flow(module, "reviewer"),
        blocked_external_requests=blocked,
    )
    assert result["status"] == "FAIL"
    assert result["external_dependency_requests"] == blocked


def test_expected_probe_failed_request_does_not_fail_flow():
    module = load_runner_module()
    flow = passing_flow(module, "student")
    flow["failed_requests"].append(
        {
            "url": "https://example.invalid/lexibridge-e2e-probe.json",
            "failure": "net::ERR_FAILED",
            "expected": True,
        }
    )
    assert module.flow_has_failures(flow, []) is False


def test_pdf_blob_navigation_abort_is_expected_browser_lifecycle_event():
    module = load_runner_module()
    flow = passing_flow(module, "student")
    capture = module.FlowCapture(flow, [], 5000)

    class FakeRequest:
        url = "blob:http://127.0.0.1:5000/private-pdf"
        failure = "net::ERR_ABORTED"

    capture.on_request_failed(FakeRequest())

    assert flow["failed_requests"] == [{
        "url": FakeRequest.url,
        "failure": "net::ERR_ABORTED",
        "expected": True,
    }]
    assert module.flow_has_failures(flow, []) is False


def test_runtime_detection_reports_missing_playwright(monkeypatch):
    module = load_runner_module()
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("missing playwright for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="E2E_ENVIRONMENT_UNAVAILABLE"):
        module.assert_playwright_available()


def test_artifact_path_fixture_is_outside_git_workspace(tmp_path):
    artifact_dir = tmp_path / "browser-e2e-artifacts"
    assert not str(artifact_dir.resolve()).startswith(str(ROOT.resolve()))


def test_wait_text_contains_synchronizes_async_browser_content():
    module = load_runner_module()

    class FakeLocator:
        def inner_text(self):
            return "个人中文证据：1 份可检索 / 1 份已上传。"

    class FakePage:
        def __init__(self):
            self.wait_call = None

        def wait_for_function(self, script, *, arg, timeout):
            self.wait_call = {"script": script, "arg": arg, "timeout": timeout}

        def locator(self, selector):
            assert selector == '[data-testid="personal-evidence-corpus-status"]'
            return FakeLocator()

    page = FakePage()
    locator = module.wait_text_contains(
        page,
        '[data-testid="personal-evidence-corpus-status"]',
        "1 份可检索",
    )

    assert locator.inner_text().startswith("个人中文证据")
    assert page.wait_call["arg"] == [
        '[data-testid="personal-evidence-corpus-status"]',
        "1 份可检索",
    ]
    assert page.wait_call["timeout"] == 10000


@pytest.mark.parametrize(
    ("alignment_status", "support_status"),
    [
        ("READY", "EVIDENCE_GROUNDED"),
        ("REVIEW_REQUIRED", "ALTERNATIVES_UNRESOLVED"),
        ("NOT_READY", "NO_RELIABLE_ALIGNMENT"),
    ],
)
def test_student_browser_accepts_every_student_facing_alignment_state(
    alignment_status,
    support_status,
):
    module = load_runner_module()
    support = {
        "contract_id": "student-learning-support@1.0.0",
        "provider_used": False,
        "grounding_mode": "DETERMINISTIC_EVIDENCE_TEMPLATE",
        "status": support_status,
        "candidate_evidence": [] if alignment_status == "NOT_READY" else [{}],
        "do_not_confuse_with": [] if alignment_status == "NOT_READY" else [{}],
    }

    module.assert_student_learning_support_contract(alignment_status, support)


def test_readiness_e2e_summary_maps_json_fields():
    readiness = load_readiness_module()
    summary = readiness.summarize_browser_e2e_result(
        {
            "status": "PASS",
            "browser": {"name": "chromium", "version": "148.0.7778.96"},
            "student_flow": {"status": "PASS", "console_errors": [], "page_errors": []},
            "instructor_flow": {"status": "PASS", "console_errors": [], "page_errors": []},
            "reviewer_flow": {"status": "PASS", "console_errors": [], "page_errors": []},
            "teacher_flow": {"status": "PASS", "console_errors": [], "page_errors": []},
            "blocked_external_requests": [{"source": "probe", "url": "https://example.invalid"}],
            "external_dependency_requests": [],
        }
    )
    assert summary["browser_e2e_status"] == "PASS"
    assert summary["browser_name"] == "chromium"
    assert summary["student_flow_status"] == "PASS"
    assert summary["teacher_flow_status"] == "PASS"
    assert summary["js_error_count"] == 0
    assert summary["external_dependency_count"] == 0
    assert summary["blocked_external_request_count"] == 1
