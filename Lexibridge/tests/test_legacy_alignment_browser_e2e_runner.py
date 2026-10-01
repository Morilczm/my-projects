import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_runner_module():
    spec = importlib.util.spec_from_file_location(
        "run_legacy_alignment_browser_e2e",
        ROOT / "scripts" / "run_legacy_alignment_browser_e2e.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def passing_flow(module, name):
    flow = module.base_e2e.flow_result(name)
    flow["status"] = "PASS"
    module.base_e2e.add_step(flow, "sample step")
    return flow


def test_alignment_browser_result_schema_has_required_flows():
    module = load_runner_module()
    result = module.build_alignment_result(
        local_flow=passing_flow(module, "legacy_alignment_local"),
        external_blocked_flow=passing_flow(module, "legacy_alignment_external_blocked"),
        blocked_external_requests=[],
    )

    assert result["status"] == "PASS"
    assert result["legacy_alignment_local_flow"]["status"] == "PASS"
    assert result["legacy_alignment_external_blocked_flow"]["status"] == "PASS"
    assert result["external_dependency_requests"] == []


def test_alignment_browser_result_fails_on_page_external_dependency():
    module = load_runner_module()
    result = module.build_alignment_result(
        local_flow=passing_flow(module, "legacy_alignment_local"),
        external_blocked_flow=passing_flow(module, "legacy_alignment_external_blocked"),
        blocked_external_requests=[
            {
                "flow": "legacy_alignment_local",
                "source": "page",
                "url": "https://cdn.example.invalid/library.js",
            }
        ],
    )

    assert result["status"] == "FAIL"
    assert result["external_dependency_requests"]


def test_fetch_json_helper_uses_browser_relative_paths():
    module = load_runner_module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "fetch(path" in source
    assert "/api/alignment/run" in source
    assert "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED" in source
