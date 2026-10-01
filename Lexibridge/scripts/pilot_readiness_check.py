#!/usr/bin/env python3
"""Run pilot-readiness checks for LexiBridge-AI without external network calls."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend" / ".venv-macos" / "bin" / "python"
PYTHON_CMD = str(PYTHON if PYTHON.exists() else sys.executable)
READY = "READY"
READY_WITH_CONDITIONS = "READY_WITH_CONDITIONS"
NOT_READY = "NOT_READY"
E2E_ENVIRONMENT_UNAVAILABLE = 2

PROFILE_CONDITIONS = {
    "local-demo": [
        "sqlite_database",
        "flask_development_server",
        "external_llm_disabled",
        "demo_local_accounts_only",
        "formal_migration_not_enabled",
        "FORMAL_WORKFLOW_PROVIDER_SELECTION_POLICY_PRESENT",
        "FORMAL_ADMISSION_PROVIDER_SELECTION_FROZEN",
        "FORMAL_DEFAULT_DETERMINISTIC_PROVIDER_CONFIGURED",
        "FORMAL_DEFAULT_PROVIDER_POLICY_ALLOWED",
        "FORMAL_DEFAULT_PROVIDER_PREFLIGHT_PASSED",
        "FORMAL_ITEM_PREPARATION_NO_SILENT_PROVIDER_FALLBACK",
        "FORMAL_LEGACY_NULL_SELECTION_FAILS_CLOSED",
        "FORMAL_BACKGROUND_JOB_LEASE_FOUNDATION_PRESENT",
        "FORMAL_CHUNK_SCOPED_TERM_CANDIDATES_PRESENT",
        "FORMAL_WORKFLOW_ITEM_BOOTSTRAP_PRESENT",
        "FORMAL_BOOTSTRAP_LEASE_FENCING_PRESENT",
        "FORMAL_ITEM_EXECUTION_IDENTITY_SCHEMA_PRESENT",
        "FORMAL_VERIFICATION_EXECUTION_KEY_UNIQUENESS_PRESENT",
        "FORMAL_PREFLIGHT_EXECUTION_KEY_UNIQUENESS_PRESENT",
        "FORMAL_USAGE_EXECUTION_KEY_UNIQUENESS_PRESENT",
        "FORMAL_AUDIT_EVENT_IDENTITY_UNIQUENESS_PRESENT",
        "FORMAL_ITEM_VERIFICATION_ADAPTER_PRESENT",
        "FORMAL_ITEM_EXECUTION_MAPPING_USED",
        "FORMAL_PROVIDER_PREFLIGHT_ENFORCED",
        "FORMAL_VERIFICATION_EXECUTION_REUSE_PRESENT",
        "FORMAL_USAGE_EXECUTION_IDENTITY_ENFORCED",
        "FORMAL_AUDIT_EVENT_IDENTITY_ENFORCED",
        "FORMAL_APPROVED_CARD_PROTECTION_PRESENT",
        "FORMAL_EVIDENCE_PERSISTENCE_MINIMIZED",
        "POSTGRESQL_ITEM_ADAPTER_NOT_VERIFIED",
        "POSTGRESQL_IDEMPOTENCY_CONSTRAINTS_NOT_VERIFIED",
        "FORMAL_MIGRATION_FRAMEWORK_NOT_ESTABLISHED",
        "POSTGRESQL_BOOTSTRAP_TRANSACTION_NOT_VERIFIED",
        "FORMAL_DOCUMENT_PROCESSING_ORCHESTRATOR_PRESENT",
        "FORMAL_ITEM_PREPARATION_COMPOSITION_PRESENT",
        "FORMAL_ROOT_PROGRESS_RECALCULATION_PRESENT",
        "FORMAL_ROOT_FINALIZATION_PRESENT",
        "FORMAL_ROOT_AUDIT_IDEMPOTENCY_PRESENT",
        "FORMAL_PROCESSING_PARTIAL_FAILURE_PRESENT",
        "FORMAL_PROCESSING_RESUME_PRESENT",
        "FORMAL_DOCUMENT_ALIGNMENT_WORKER_HANDLER_PRESENT",
        "FORMAL_DOCUMENT_ALIGNMENT_JOB_DISPATCH_PRESENT",
        "FORMAL_WORKER_RESULT_MAPPING_PRESENT",
        "FORMAL_WORKER_RETRY_MAPPING_PRESENT",
        "FORMAL_WORKER_STALE_RECOVERY_PRESENT",
        "FORMAL_ROOT_JOB_TERMINAL_CONSISTENCY_PRESENT",
        "FORMAL_JOB_NO_LEGACY_DISPATCH_PRESENT",
        "FORMAL_WORKFLOW_RETRY_BUDGET_POLICY_PRESENT",
        "FORMAL_ADMISSION_MAX_ATTEMPTS_FROZEN",
        "FORMAL_HTTP_RETRYABLE_REQUEUE_VERIFIED",
        "FORMAL_RETRY_NEXT_CLAIM_RECOVERY_VERIFIED",
        "FORMAL_RETRY_EXHAUSTION_ORDER_VERIFIED",
        "FORMAL_STALE_RECLAIM_DOES_NOT_CONSUM_RETRY_BUDGET",
        "FORMAL_WORKFLOW_RUN_QUERY_SERVICE_PRESENT",
        "FORMAL_WORKFLOW_ITEM_QUERY_SERVICE_PRESENT",
        "FORMAL_WORKFLOW_QUERY_PERMISSION_ENFORCED",
        "FORMAL_WORKFLOW_QUERY_STUDENT_DENIED",
        "FORMAL_WORKFLOW_QUERY_BACKGROUND_JOB_HIDDEN",
        "FORMAL_WORKFLOW_QUERY_SAFE_ERROR_PRESENT",
        "FORMAL_WORKFLOW_QUERY_PAGINATION_PRESENT",
        "FORMAL_WORKFLOW_QUERY_NO_WRITE_PRESENT",
        "FORMAL_WORKFLOW_START_ROUTE_PRESENT",
        "FORMAL_WORKFLOW_RUN_ROUTE_PRESENT",
        "FORMAL_WORKFLOW_ITEMS_ROUTE_PRESENT",
        "FORMAL_WORKFLOW_IDEMPOTENCY_HEADER_ENFORCED",
        "FORMAL_WORKFLOW_HTTP_PERMISSION_ENFORCED",
        "FORMAL_WORKFLOW_HTTP_STUDENT_DENIED",
        "FORMAL_WORKFLOW_HTTP_BACKGROUND_JOB_HIDDEN",
        "FORMAL_WORKFLOW_OPENAPI_PRESENT",
        "FORMAL_WORKFLOW_OPENAPI_RUNTIME_PARITY_PRESENT",
        "FORMAL_PRODUCTION_DEFAULT_CONTRACT_VERIFIED",
        "FORMAL_API_E2E_PRESENT",
        "FORMAL_API_HTTP_START_VERIFIED",
        "FORMAL_API_WORKER_EXECUTION_VERIFIED",
        "FORMAL_API_POLLING_VERIFIED",
        "FORMAL_API_ITEM_QUERY_VERIFIED",
        "FORMAL_API_SOURCE_SCOPED_IDEMPOTENCY_VERIFIED",
        "FORMAL_API_CONCURRENT_REPLAY_VERIFIED",
        "FORMAL_API_PARTIAL_FAILURE_VERIFIED",
        "FORMAL_API_ALL_BLOCKED_VERIFIED",
        "FORMAL_API_RETRYABLE_RECOVERY_VERIFIED",
        "FORMAL_API_STALE_RECOVERY_VERIFIED",
        "FORMAL_API_TERMINAL_RECOVERY_VERIFIED",
        "FORMAL_API_STUDENT_DENIAL_VERIFIED",
        "FORMAL_FRONTEND_CUTOVER_PRESENT",
        "FORMAL_FRONTEND_START_USES_FORMAL_API",
        "FORMAL_FRONTEND_RUN_POLLING_PRESENT",
        "FORMAL_FRONTEND_ITEMS_QUERY_PRESENT",
        "FORMAL_FRONTEND_ITEMS_PAGINATION_PRESENT",
        "FORMAL_FRONTEND_RELOAD_RESUME_PRESENT",
        "FORMAL_FRONTEND_DUPLICATE_START_PREVENTED",
        "FORMAL_FRONTEND_TEACHER_GATED",
        "FORMAL_FRONTEND_LEGACY_ALIGNMENT_NOT_CALLED",
        "FORMAL_FRONTEND_NO_LEGACY_FALLBACK",
        "LEGACY_ALIGNMENT_ROUTE_STILL_PRESENT",
        "FRONTEND_VISUAL_REDESIGN_NOT_COMPLETED",
        "HISTORICAL_RUN_LIST_NOT_IMPLEMENTED",
        "FULL_REVIEW_WORKBENCH_NOT_IMPLEMENTED",
        "POSTGRESQL_UI_FLOW_NOT_VERIFIED",
        "POSTGRESQL_API_E2E_NOT_VERIFIED",
        "POSTGRESQL_HTTP_FLOW_NOT_VERIFIED",
        "POSTGRESQL_QUERY_NOT_VERIFIED",
        "POSTGRESQL_WORKER_NOT_VERIFIED",
        "PRODUCTION_WORKER_RUNTIME_NOT_ESTABLISHED",
        "POSTGRESQL_PROCESSING_NOT_VERIFIED",
        "POSTGRESQL_LEASE_SEMANTICS_NOT_VERIFIED",
        "CONTROLLED_PROVIDER_EVALUATION_CONTRACT_PRESENT",
        "CONTROLLED_PROVIDER_PRIVACY_GATE_PRESENT",
        "CONTROLLED_PROVIDER_PROPOSAL_SCHEMA_PRESENT",
        "CONTROLLED_PROVIDER_ABSTENTION_PRESENT",
        "CONTROLLED_PROVIDER_HTTP_TRANSPORT_PRESENT",
        "CONTROLLED_PROVIDER_CREDENTIAL_GUARD_PRESENT",
        "CONTROLLED_PROVIDER_COST_PREFLIGHT_PRESENT",
        "CONTROLLED_PROVIDER_REQUEST_CAP_PRESENT",
        "CONTROLLED_PROVIDER_RETRY_CAP_PRESENT",
        "CONTROLLED_PROVIDER_ARTIFACT_PRESENT",
        "CONTROLLED_PROVIDER_FAKE_HTTP_E2E_VERIFIED",
        "CONTROLLED_PROVIDER_DRY_RUN_VERIFIED",
        "REAL_PROVIDER_NOT_EXECUTED",
        "FORMAL_WORKFLOW_PROVIDER_UNCHANGED",
        "PRIVATE_COURSE_EXTERNAL_SEND_BLOCKED",
    ],
    "small-pilot": [
        "small_pilot_only",
        "sqlite_database",
        "flask_development_server",
        "external_llm_disabled",
        "demo_local_account_restrictions",
        "formal_migration_not_enabled",
        "production_monitoring_not_enabled",
        "FORMAL_WORKFLOW_PROVIDER_SELECTION_POLICY_PRESENT",
        "FORMAL_ADMISSION_PROVIDER_SELECTION_FROZEN",
        "FORMAL_DEFAULT_DETERMINISTIC_PROVIDER_CONFIGURED",
        "FORMAL_DEFAULT_PROVIDER_POLICY_ALLOWED",
        "FORMAL_DEFAULT_PROVIDER_PREFLIGHT_PASSED",
        "FORMAL_ITEM_PREPARATION_NO_SILENT_PROVIDER_FALLBACK",
        "FORMAL_LEGACY_NULL_SELECTION_FAILS_CLOSED",
        "FORMAL_BACKGROUND_JOB_LEASE_FOUNDATION_PRESENT",
        "FORMAL_CHUNK_SCOPED_TERM_CANDIDATES_PRESENT",
        "FORMAL_WORKFLOW_ITEM_BOOTSTRAP_PRESENT",
        "FORMAL_BOOTSTRAP_LEASE_FENCING_PRESENT",
        "FORMAL_ITEM_EXECUTION_IDENTITY_SCHEMA_PRESENT",
        "FORMAL_VERIFICATION_EXECUTION_KEY_UNIQUENESS_PRESENT",
        "FORMAL_PREFLIGHT_EXECUTION_KEY_UNIQUENESS_PRESENT",
        "FORMAL_USAGE_EXECUTION_KEY_UNIQUENESS_PRESENT",
        "FORMAL_AUDIT_EVENT_IDENTITY_UNIQUENESS_PRESENT",
        "FORMAL_ITEM_VERIFICATION_ADAPTER_PRESENT",
        "FORMAL_ITEM_EXECUTION_MAPPING_USED",
        "FORMAL_PROVIDER_PREFLIGHT_ENFORCED",
        "FORMAL_VERIFICATION_EXECUTION_REUSE_PRESENT",
        "FORMAL_USAGE_EXECUTION_IDENTITY_ENFORCED",
        "FORMAL_AUDIT_EVENT_IDENTITY_ENFORCED",
        "FORMAL_APPROVED_CARD_PROTECTION_PRESENT",
        "FORMAL_EVIDENCE_PERSISTENCE_MINIMIZED",
        "POSTGRESQL_ITEM_ADAPTER_NOT_VERIFIED",
        "POSTGRESQL_IDEMPOTENCY_CONSTRAINTS_NOT_VERIFIED",
        "FORMAL_MIGRATION_FRAMEWORK_NOT_ESTABLISHED",
        "POSTGRESQL_BOOTSTRAP_TRANSACTION_NOT_VERIFIED",
        "FORMAL_DOCUMENT_PROCESSING_ORCHESTRATOR_PRESENT",
        "FORMAL_ITEM_PREPARATION_COMPOSITION_PRESENT",
        "FORMAL_ROOT_PROGRESS_RECALCULATION_PRESENT",
        "FORMAL_ROOT_FINALIZATION_PRESENT",
        "FORMAL_ROOT_AUDIT_IDEMPOTENCY_PRESENT",
        "FORMAL_PROCESSING_PARTIAL_FAILURE_PRESENT",
        "FORMAL_PROCESSING_RESUME_PRESENT",
        "FORMAL_DOCUMENT_ALIGNMENT_WORKER_HANDLER_PRESENT",
        "FORMAL_DOCUMENT_ALIGNMENT_JOB_DISPATCH_PRESENT",
        "FORMAL_WORKER_RESULT_MAPPING_PRESENT",
        "FORMAL_WORKER_RETRY_MAPPING_PRESENT",
        "FORMAL_WORKER_STALE_RECOVERY_PRESENT",
        "FORMAL_ROOT_JOB_TERMINAL_CONSISTENCY_PRESENT",
        "FORMAL_JOB_NO_LEGACY_DISPATCH_PRESENT",
        "FORMAL_WORKFLOW_RETRY_BUDGET_POLICY_PRESENT",
        "FORMAL_ADMISSION_MAX_ATTEMPTS_FROZEN",
        "FORMAL_HTTP_RETRYABLE_REQUEUE_VERIFIED",
        "FORMAL_RETRY_NEXT_CLAIM_RECOVERY_VERIFIED",
        "FORMAL_RETRY_EXHAUSTION_ORDER_VERIFIED",
        "FORMAL_STALE_RECLAIM_DOES_NOT_CONSUM_RETRY_BUDGET",
        "FORMAL_WORKFLOW_RUN_QUERY_SERVICE_PRESENT",
        "FORMAL_WORKFLOW_ITEM_QUERY_SERVICE_PRESENT",
        "FORMAL_WORKFLOW_QUERY_PERMISSION_ENFORCED",
        "FORMAL_WORKFLOW_QUERY_STUDENT_DENIED",
        "FORMAL_WORKFLOW_QUERY_BACKGROUND_JOB_HIDDEN",
        "FORMAL_WORKFLOW_QUERY_SAFE_ERROR_PRESENT",
        "FORMAL_WORKFLOW_QUERY_PAGINATION_PRESENT",
        "FORMAL_WORKFLOW_QUERY_NO_WRITE_PRESENT",
        "FORMAL_WORKFLOW_START_ROUTE_PRESENT",
        "FORMAL_WORKFLOW_RUN_ROUTE_PRESENT",
        "FORMAL_WORKFLOW_ITEMS_ROUTE_PRESENT",
        "FORMAL_WORKFLOW_IDEMPOTENCY_HEADER_ENFORCED",
        "FORMAL_WORKFLOW_HTTP_PERMISSION_ENFORCED",
        "FORMAL_WORKFLOW_HTTP_STUDENT_DENIED",
        "FORMAL_WORKFLOW_HTTP_BACKGROUND_JOB_HIDDEN",
        "FORMAL_WORKFLOW_OPENAPI_PRESENT",
        "FORMAL_WORKFLOW_OPENAPI_RUNTIME_PARITY_PRESENT",
        "FORMAL_PRODUCTION_DEFAULT_CONTRACT_VERIFIED",
        "FORMAL_API_E2E_PRESENT",
        "FORMAL_API_HTTP_START_VERIFIED",
        "FORMAL_API_WORKER_EXECUTION_VERIFIED",
        "FORMAL_API_POLLING_VERIFIED",
        "FORMAL_API_ITEM_QUERY_VERIFIED",
        "FORMAL_API_SOURCE_SCOPED_IDEMPOTENCY_VERIFIED",
        "FORMAL_API_CONCURRENT_REPLAY_VERIFIED",
        "FORMAL_API_PARTIAL_FAILURE_VERIFIED",
        "FORMAL_API_ALL_BLOCKED_VERIFIED",
        "FORMAL_API_RETRYABLE_RECOVERY_VERIFIED",
        "FORMAL_API_STALE_RECOVERY_VERIFIED",
        "FORMAL_API_TERMINAL_RECOVERY_VERIFIED",
        "FORMAL_API_STUDENT_DENIAL_VERIFIED",
        "FORMAL_FRONTEND_CUTOVER_PRESENT",
        "FORMAL_FRONTEND_START_USES_FORMAL_API",
        "FORMAL_FRONTEND_RUN_POLLING_PRESENT",
        "FORMAL_FRONTEND_ITEMS_QUERY_PRESENT",
        "FORMAL_FRONTEND_ITEMS_PAGINATION_PRESENT",
        "FORMAL_FRONTEND_RELOAD_RESUME_PRESENT",
        "FORMAL_FRONTEND_DUPLICATE_START_PREVENTED",
        "FORMAL_FRONTEND_TEACHER_GATED",
        "FORMAL_FRONTEND_LEGACY_ALIGNMENT_NOT_CALLED",
        "FORMAL_FRONTEND_NO_LEGACY_FALLBACK",
        "LEGACY_ALIGNMENT_ROUTE_STILL_PRESENT",
        "FRONTEND_VISUAL_REDESIGN_NOT_COMPLETED",
        "HISTORICAL_RUN_LIST_NOT_IMPLEMENTED",
        "FULL_REVIEW_WORKBENCH_NOT_IMPLEMENTED",
        "POSTGRESQL_UI_FLOW_NOT_VERIFIED",
        "POSTGRESQL_API_E2E_NOT_VERIFIED",
        "POSTGRESQL_HTTP_FLOW_NOT_VERIFIED",
        "POSTGRESQL_QUERY_NOT_VERIFIED",
        "POSTGRESQL_WORKER_NOT_VERIFIED",
        "PRODUCTION_WORKER_RUNTIME_NOT_ESTABLISHED",
        "POSTGRESQL_PROCESSING_NOT_VERIFIED",
        "POSTGRESQL_LEASE_SEMANTICS_NOT_VERIFIED",
        "CONTROLLED_PROVIDER_EVALUATION_CONTRACT_PRESENT",
        "CONTROLLED_PROVIDER_PRIVACY_GATE_PRESENT",
        "CONTROLLED_PROVIDER_PROPOSAL_SCHEMA_PRESENT",
        "CONTROLLED_PROVIDER_ABSTENTION_PRESENT",
        "CONTROLLED_PROVIDER_HTTP_TRANSPORT_PRESENT",
        "CONTROLLED_PROVIDER_CREDENTIAL_GUARD_PRESENT",
        "CONTROLLED_PROVIDER_COST_PREFLIGHT_PRESENT",
        "CONTROLLED_PROVIDER_REQUEST_CAP_PRESENT",
        "CONTROLLED_PROVIDER_RETRY_CAP_PRESENT",
        "CONTROLLED_PROVIDER_ARTIFACT_PRESENT",
        "CONTROLLED_PROVIDER_FAKE_HTTP_E2E_VERIFIED",
        "CONTROLLED_PROVIDER_DRY_RUN_VERIFIED",
        "REAL_PROVIDER_NOT_EXECUTED",
        "FORMAL_WORKFLOW_PROVIDER_UNCHANGED",
        "PRIVATE_COURSE_EXTERNAL_SEND_BLOCKED",
    ],
}


class PhaseResult(dict):
    @property
    def ok(self) -> bool:
        return self.get("status") in {"PASS", "WARN", "UNAVAILABLE"}

    @property
    def blocking_failed(self) -> bool:
        return self.get("status") == "FAIL"


def default_conditions(profile: str) -> list[str]:
    return list(PROFILE_CONDITIONS.get(profile, PROFILE_CONDITIONS["small-pilot"]))


def compute_readiness_verdict(checks: list[dict], conditions: list[str] | None = None) -> str:
    if any(str(check.get("status") or "").upper() == "FAIL" for check in checks):
        return NOT_READY
    if conditions:
        return READY_WITH_CONDITIONS
    return READY


def build_readiness_payload(
    *,
    profile: str,
    checks: list[dict],
    conditions: list[str],
    warnings: list[str],
    browser_e2e: dict | None = None,
) -> dict:
    blocking_failures = [
        {
            "name": check.get("name"),
            "returncode": check.get("returncode"),
            "status": check.get("status"),
        }
        for check in checks
        if str(check.get("status") or "").upper() == "FAIL"
    ]
    verdict = compute_readiness_verdict(checks, conditions)
    return {
        "verdict": verdict,
        "profile": profile,
        "checks": checks,
        "conditions": conditions,
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "browser_e2e": browser_e2e or {},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def summarize_browser_e2e_result(result: dict | None) -> dict:
    result = result or {}
    student = result.get("student_flow") or {}
    teacher = result.get("teacher_flow") or {}
    browser = result.get("browser") or {}
    flows = [student, teacher]
    return {
        "browser_e2e_status": result.get("status", "UNKNOWN"),
        "browser_name": browser.get("name", ""),
        "browser_version": browser.get("version", ""),
        "student_flow_status": student.get("status", "UNKNOWN"),
        "teacher_flow_status": teacher.get("status", "UNKNOWN"),
        "js_error_count": sum(len(flow.get("console_errors") or []) for flow in flows),
        "page_error_count": sum(len(flow.get("page_errors") or []) for flow in flows),
        "external_dependency_count": len(result.get("external_dependency_requests") or []),
        "blocked_external_request_count": len(result.get("blocked_external_requests") or []),
    }


def load_json_result(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_env(temp_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{temp_root / 'pilot-readiness.db'}"
    env["UPLOAD_FOLDER"] = str(temp_root / "uploads")
    env["AUTH_REQUIRED"] = "True"
    env["AI_PROVIDER"] = "none"
    env["ALLOW_MOCK_AI"] = "True"
    env["OCR_PROVIDER"] = "none"
    env["FORMULA_OCR_PROVIDER"] = "none"
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def run_command(
    name: str,
    cmd: list[str],
    env: dict[str, str],
    *,
    timeout: int = 180,
    condition_returncodes: dict[int, tuple[str, str]] | None = None,
) -> PhaseResult:
    print(f"\n==> {name}")
    started = time.perf_counter()
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr)
    condition_returncodes = condition_returncodes or {}
    condition = ""
    if result.returncode == 0:
        status = "PASS"
    elif result.returncode in condition_returncodes:
        status, condition = condition_returncodes[result.returncode]
    else:
        status = "FAIL"
    print(f"{status}: {name} ({elapsed_ms} ms)")
    payload = PhaseResult(name=name, returncode=result.returncode, elapsed_ms=elapsed_ms, status=status)
    if condition:
        payload["condition"] = condition
    return payload


def run_python_snippet(name: str, code: str, env: dict[str, str], *, timeout: int = 180) -> PhaseResult:
    return run_command(name, [PYTHON_CMD, "-c", textwrap.dedent(code)], env, timeout=timeout)


def frontend_js_syntax_check_code() -> str:
    return r"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path.cwd()
html = root / "frontend" / "index.html"
text = html.read_text(encoding="utf-8")
matches = re.findall(r"<script>(.*?)</script>", text, flags=re.S)
if not matches:
    raise SystemExit("no inline frontend script found")
node = (
    Path.home()
    / ".cache"
    / "codex-runtimes"
    / "codex-primary-runtime"
    / "dependencies"
    / "node"
    / "bin"
    / "node"
)
node_cmd = str(node) if node.exists() else shutil.which("node")
if not node_cmd:
    print("SKIP: node not available for frontend JavaScript syntax check")
    raise SystemExit(0)
with tempfile.TemporaryDirectory(prefix="lexibridge-js-check-") as tmp:
    path = Path(tmp) / "frontend.js"
    path.write_text("\n".join(matches), encoding="utf-8")
    subprocess.run([node_cmd, "--check", str(path)], cwd=root, check=True)
"""


def python_compile_code() -> str:
    return r"""
import tokenize
from pathlib import Path

root = Path.cwd()
skip_parts = {".git", ".venv", ".venv-macos", "__pycache__", ".pytest_cache", "uploads", "final_delivery"}
failures = []
for path in root.rglob("*.py"):
    relative_parts = path.relative_to(root).parts
    if any(part in skip_parts or part.startswith(".venv") for part in relative_parts):
        continue
    try:
        with tokenize.open(path) as handle:
            source = handle.read()
        compile(source, str(path), "exec")
    except Exception as exc:
        failures.append(f"{path}: {exc}")
if failures:
    print("\n".join(failures))
    raise SystemExit(1)
print("compiled python files")
"""


def api_smoke_code() -> str:
    return r"""
import importlib.util
from pathlib import Path

root = Path.cwd()
backend = root / "backend"
import sys
sys.path.insert(0, str(backend))
spec = importlib.util.spec_from_file_location("pilot_app", backend / "app.py")
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
seed_spec = importlib.util.spec_from_file_location("pilot_seed", root / "scripts" / "seed_review_demo.py")
seed = importlib.util.module_from_spec(seed_spec)
seed_spec.loader.exec_module(seed)
summary = seed.seed_review_demo(app_module, reset_demo=False)
client = app_module.app.test_client()
login = client.post("/api/auth/login", json={
    "email": summary["users"]["student"]["email"],
    "password": summary["users"]["student"]["password"],
})
assert login.status_code == 200, login.get_data(as_text=True)
token = login.get_json()["token"]
headers = {"Authorization": f"Bearer {token}", "X-Request-ID": "pilot-readiness-api-smoke"}
cards = client.get("/api/student/concept-cards?per_page=5", headers=headers)
assert cards.status_code == 200, cards.get_data(as_text=True)
assert cards.get_json()["request_id"] == "pilot-readiness-api-smoke"
print(f"student cards: {len(cards.get_json()['data']['items'])}")
"""


def provider_network_disabled_code() -> str:
    return r"""
import importlib.util
import socket
import sys
import urllib.request
from pathlib import Path

root = Path.cwd()
backend = root / "backend"
sys.path.insert(0, str(backend))
spec = importlib.util.spec_from_file_location("pilot_app_network", backend / "app.py")
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
seed_spec = importlib.util.spec_from_file_location("pilot_seed_network", root / "scripts" / "seed_review_demo.py")
seed = importlib.util.module_from_spec(seed_spec)
seed_spec.loader.exec_module(seed)
summary = seed.seed_review_demo(app_module, reset_demo=False)
client = app_module.app.test_client()
login = client.post("/api/auth/login", json={
    "email": summary["users"]["admin"]["email"],
    "password": summary["users"]["admin"]["password"],
})
assert login.status_code == 200, login.get_data(as_text=True)
token = login.get_json()["token"]
original_connect = socket.socket.connect
original_request = urllib.request.Request
original_urlopen = urllib.request.urlopen
def blocked_connect(*args, **kwargs):
    raise AssertionError("external network is disabled during pilot readiness checks")
def blocked_request(*args, **kwargs):
    raise AssertionError("legacy alignment urllib Request must not be constructed")
def blocked_urlopen(*args, **kwargs):
    raise AssertionError("legacy alignment urlopen must not be called")
socket.socket.connect = blocked_connect
urllib.request.Request = blocked_request
urllib.request.urlopen = blocked_urlopen
try:
    response = client.post(
        "/api/alignment/verify",
        json={"card_uid": summary["card_uids"]["fourier"], "provider": "deepseek-alignment-v1-disabled"},
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "pilot-readiness-disabled-provider"},
    )
finally:
    socket.socket.connect = original_connect
    urllib.request.Request = original_request
    urllib.request.urlopen = original_urlopen
assert response.status_code == 200, response.get_data(as_text=True)
payload = response.get_json()["data"]
assert payload["verification_status"] == "failed"
assert payload["can_auto_approve"] is False
with app_module.app.app_context():
    live_config = app_module.AIProviderConfig(
        provider_name="deepseek",
        provider_mode="live",
        base_url="https://example.invalid/readiness-live-probe",
        default_model="deepseek-chat",
        is_enabled=True,
        is_default=True,
        health_status="unknown",
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(live_config)
    app_module.db.session.commit()
app_module.DEEPSEEK_API_KEY = "LEXIBRIDGE_READINESS_SENTINEL_SECRET"
app_module.DEEPSEEK_BASE_URL = "https://example.invalid/readiness-live-probe"
legacy_response = client.post(
    "/api/admin/ai/healthcheck",
    json={"live_probe": True},
    headers={"Authorization": f"Bearer {token}", "X-Request-ID": "pilot-readiness-legacy-live-probe-disabled"},
)
assert legacy_response.status_code == 200, legacy_response.get_data(as_text=True)
legacy_payload = legacy_response.get_json()
serialized = str(legacy_payload)
assert "LEXIBRIDGE_READINESS_SENTINEL_SECRET" not in serialized
assert any(
    item.get("error_code") == "LEGACY_LIVE_PROBE_DISABLED"
    for item in legacy_payload["data"]["items"]
), legacy_payload
ctx = app_module.app.app_context()
ctx.push()
course = app_module.Course.query.filter_by(name=summary["course"]).first()
admin = app_module.User.query.filter_by(email=summary["users"]["admin"]["email"]).first()
assert course is not None
assert admin is not None
before_route = {
    "alignment_runs": app_module.AlignmentRun.query.count(),
    "background_jobs": app_module.BackgroundJob.query.count(),
    "terminology_cards": app_module.TerminologyCard.query.count(),
    "usage_records": app_module.UsageRecord.query.count(),
    "ai_call_logs": app_module.AICallLog.query.count(),
    "verification_runs": app_module.AlignmentVerificationRun.query.count(),
    "audit_records": app_module.AuditRecord.query.count(),
}
def fail_metadata(*args, **kwargs):
    raise AssertionError("legacy alignment blocked path must not load provider metadata")
app_module.current_provider_metadata = fail_metadata
original_connect = socket.socket.connect
original_request = urllib.request.Request
original_urlopen = urllib.request.urlopen
socket.socket.connect = blocked_connect
urllib.request.Request = blocked_request
urllib.request.urlopen = blocked_urlopen
try:
    route_response = client.post(
        "/api/alignment/run",
        json={
            "scope_type": "course",
            "course_id": course.id,
            "english_term": "Pilot readiness external legacy route",
            "courseware_sentence": "External provider must be blocked before transport.",
            "provider": "deepseek",
            "base_url": "https://example.invalid/readiness-legacy-alignment?token=LEXIBRIDGE_READINESS_SENTINEL_SECRET",
        },
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": "pilot-readiness-legacy-alignment-external-disabled"},
    )
finally:
    socket.socket.connect = original_connect
    urllib.request.Request = original_request
    urllib.request.urlopen = original_urlopen
assert route_response.status_code == 422, route_response.get_data(as_text=True)
route_payload = route_response.get_json()
route_serialized = str(route_payload)
assert route_payload["error_code"] == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED", route_payload
assert "LEXIBRIDGE_READINESS_SENTINEL_SECRET" not in route_serialized
after_route = {
    "alignment_runs": app_module.AlignmentRun.query.count(),
    "background_jobs": app_module.BackgroundJob.query.count(),
    "terminology_cards": app_module.TerminologyCard.query.count(),
    "usage_records": app_module.UsageRecord.query.count(),
    "ai_call_logs": app_module.AICallLog.query.count(),
    "verification_runs": app_module.AlignmentVerificationRun.query.count(),
    "audit_records": app_module.AuditRecord.query.count(),
}
assert after_route == before_route, (before_route, after_route)
alignment_run = app_module.AlignmentRun(
    course_id=course.id,
    triggered_by=admin.id,
    provider="deepseek",
    model_name="deepseek-chat",
    ai_provider="deepseek",
    ai_provider_mode="live",
    ai_model="deepseek-chat",
    prompt_key="term_alignment",
    prompt_version="v1",
    retrieval_version=app_module.RETRIEVAL_VERSION,
    status="queued",
    started_at="",
)
app_module.db.session.add(alignment_run)
app_module.db.session.flush()
job = app_module.create_background_job(
    "alignment_run",
    admin.id,
    course_id=course.id,
    alignment_run_id=alignment_run.id,
    scope_type="course",
    input_data={
        "provider": "deepseek",
        "provider_mode": "live",
        "base_url": "https://example.invalid/readiness-worker?token=LEXIBRIDGE_READINESS_SENTINEL_SECRET",
        "english_term": "Pilot readiness external worker",
        "courseware_sentence": "Queued external job must be quarantined.",
    },
)
app_module.db.session.commit()
before_worker = {
    "terminology_cards": app_module.TerminologyCard.query.count(),
    "usage_records": app_module.UsageRecord.query.count(),
    "ai_call_logs": app_module.AICallLog.query.count(),
    "verification_runs": app_module.AlignmentVerificationRun.query.count(),
    "audit_records": app_module.AuditRecord.query.count(),
}
original_connect = socket.socket.connect
original_request = urllib.request.Request
original_urlopen = urllib.request.urlopen
socket.socket.connect = blocked_connect
urllib.request.Request = blocked_request
urllib.request.urlopen = blocked_urlopen
try:
    processed = app_module.run_background_job(job.id, worker_id="pilot-readiness-worker")
finally:
    socket.socket.connect = original_connect
    urllib.request.Request = original_request
    urllib.request.urlopen = original_urlopen
assert processed.status == "failed"
assert processed.error_code == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED"
assert "LEXIBRIDGE_READINESS_SENTINEL_SECRET" not in (processed.error_message or "")
after_worker = {
    "terminology_cards": app_module.TerminologyCard.query.count(),
    "usage_records": app_module.UsageRecord.query.count(),
    "ai_call_logs": app_module.AICallLog.query.count(),
    "verification_runs": app_module.AlignmentVerificationRun.query.count(),
    "audit_records": app_module.AuditRecord.query.count(),
}
assert after_worker == before_worker, (before_worker, after_worker)
legacy_external_runnable_jobs_count = 0
for existing_job in app_module.BackgroundJob.query.filter(app_module.BackgroundJob.status.in_(["queued", "running", "retrying"])).all():
    data = app_module.job_input(existing_job)
    run = app_module.db.session.get(app_module.AlignmentRun, existing_job.alignment_run_id) if existing_job.alignment_run_id else None
    classification = app_module.classify_legacy_alignment_job(existing_job, alignment_run=run, data=data)
    if classification.external_execution_blocked:
        legacy_external_runnable_jobs_count += 1
assert legacy_external_runnable_jobs_count == 0
openapi_text = (root / "docs" / "openapi.yaml").read_text(encoding="utf-8")
alignment_run_section = openapi_text.split("/api/alignment/run:", 1)[1].split("/api/", 1)[0]
assert "deprecated: true" in alignment_run_section
assert "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED" in alignment_run_section
print("disabled external provider, legacy live probe, legacy alignment route, and legacy worker produced safe results without network")
"""


def performance_smoke_code() -> str:
    return r"""
import importlib.util
import sys
import time
from pathlib import Path

root = Path.cwd()
backend = root / "backend"
sys.path.insert(0, str(backend))
spec = importlib.util.spec_from_file_location("pilot_app_perf", backend / "app.py")
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
seed_spec = importlib.util.spec_from_file_location("pilot_seed_perf", root / "scripts" / "seed_review_demo.py")
seed = importlib.util.module_from_spec(seed_spec)
seed_spec.loader.exec_module(seed)
summary = seed.seed_review_demo(app_module, reset_demo=False)
client = app_module.app.test_client()

def token_for(role):
    response = client.post("/api/auth/login", json={
        "email": summary["users"][role]["email"],
        "password": summary["users"][role]["password"],
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["token"]

student_token = token_for("student")
teacher_token = token_for("teacher")
course = seed.DEMO_COURSE.replace(" ", "%20")
checks = [
    ("review queue", "/api/concept-cards/review-queue?course=" + course, teacher_token),
    ("student card list", "/api/student/concept-cards?course=" + course, student_token),
    ("student progress", "/api/student/progress?course=" + course, student_token),
    ("feedback queue", "/api/concept-cards/student-feedback-queue?course=" + course, teacher_token),
    ("teacher analytics", "/api/teacher/learning-analytics?course=" + course, teacher_token),
]
warnings = []
for name, path, token in checks:
    started = time.perf_counter()
    response = client.get(path, headers={"Authorization": f"Bearer {token}", "X-Request-ID": "pilot-readiness-perf"})
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json().get("data", {})
    if isinstance(data, dict) and "items" in data:
        count = len(data["items"])
    elif isinstance(data, dict) and "course_summary" in data:
        count = data["course_summary"].get("approved_card_count", 0)
    else:
        count = 1
    print(f"{name}: {elapsed_ms} ms, result_count={count}")
    if elapsed_ms > 2000:
        warnings.append(name)
if warnings:
    print("WARNING: slow demo endpoints: " + ", ".join(warnings))
"""


def table_count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"select count(*) from {table}").fetchone()[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LexiBridge pilot-readiness checks.")
    parser.add_argument("--skip-full-tests", action="store_true", help="Run targeted pilot checks instead of full pytest.")
    parser.add_argument("--profile", choices=sorted(PROFILE_CONDITIONS), default="small-pilot")
    parser.add_argument("--json-output", help="Write machine-readable readiness result JSON.")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="lexibridge-pilot-readiness-") as tmp:
        temp_root = Path(tmp)
        env = build_env(temp_root)
        db_path = temp_root / "pilot-readiness.db"
        upload_dir = temp_root / "uploads"
        backup_parent = temp_root / "backup-output"
        restored_db = temp_root / "restored" / "restored.db"
        restored_uploads = temp_root / "restored" / "uploads"
        browser_e2e_json = temp_root / "browser-e2e-result.json"
        formal_api_e2e_json = temp_root / "formal-api-e2e-result.json"
        formal_recovery_json = temp_root / "formal-api-recovery-result.json"
        formal_browser_api_json = temp_root / "formal-browser-api-result.json"
        formal_frontend_e2e_json = temp_root / "formal-frontend-e2e-result.json"
        formal_frontend_resume_json = temp_root / "formal-frontend-resume-result.json"
        browser_e2e_result: dict | None = None

        phases: list[PhaseResult] = []
        warnings: list[str] = []
        conditions = default_conditions(args.profile)
        phases.append(run_command("release safety", [PYTHON_CMD, "scripts/check_release_safety.py"], env, timeout=120))
        phases.append(run_python_snippet("python compile", python_compile_code(), env, timeout=120))
        phases.append(run_python_snippet("frontend javascript syntax", frontend_js_syntax_check_code(), env, timeout=120))

        if args.skip_full_tests:
            pytest_cmd = [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_pilot_end_to_end.py",
                "tests/test_permission_matrix.py",
                "tests/test_openapi_route_parity.py",
                "tests/test_database_upgrade_path.py",
                "tests/test_data_integrity.py",
            ]
        else:
            pytest_cmd = [PYTHON_CMD, "-m", "pytest", "-q"]
        phases.append(run_command("pytest", pytest_cmd, env, timeout=600))

        phases.append(run_command("fresh database migration", [PYTHON_CMD, "scripts/migrate_db.py", "--apply"], env, timeout=120))
        phases.append(run_command("existing database upgrade simulation", [PYTHON_CMD, "-m", "pytest", "-q", "tests/test_database_upgrade_path.py"], env, timeout=240))
        phases.append(run_command("demo seed reset", [PYTHON_CMD, "scripts/seed_review_demo.py", "--reset-demo"], env, timeout=120))
        phases.append(run_command("demo seed repeated run", [PYTHON_CMD, "scripts/seed_review_demo.py"], env, timeout=120))
        backup_phase = run_command(
            "backup creation",
            [
                PYTHON_CMD,
                "scripts/pilot_backup.py",
                "--database",
                str(db_path),
                "--uploads",
                str(upload_dir),
                "--output",
                str(backup_parent),
            ],
            env,
            timeout=120,
        )
        phases.append(backup_phase)
        backup_path = backup_parent
        if backup_phase.ok:
            manifest_candidates = sorted(backup_parent.rglob("backup_manifest.json"))
            if manifest_candidates:
                backup_path = manifest_candidates[-1].parent
        phases.append(run_command("backup verification", [PYTHON_CMD, "scripts/verify_pilot_backup.py", "--backup", str(backup_path)], env, timeout=120))
        phases.append(
            run_command(
                "restore",
                [
                    PYTHON_CMD,
                    "scripts/pilot_restore.py",
                    "--backup",
                    str(backup_path),
                    "--database-target",
                    str(restored_db),
                    "--uploads-target",
                    str(restored_uploads),
                ],
                env,
                timeout=120,
            )
        )
        phases.append(
            run_python_snippet(
                "restored database integrity",
                f"""
import sqlite3
from pathlib import Path
db = Path({str(restored_db)!r})
assert db.exists(), db
with sqlite3.connect(db) as conn:
    assert conn.execute("pragma integrity_check").fetchone()[0] == "ok"
    for table in ["concept_alignment_card", "concept_card_review_record", "student_concept_card_state", "audit_record"]:
        assert conn.execute("select count(*) from sqlite_master where type='table' and name=?", (table,)).fetchone()[0] == 1, table
print("restored database integrity ok")
""",
                env,
                timeout=120,
            )
        )
        phases.append(run_python_snippet("api smoke", api_smoke_code(), env, timeout=120))
        phases.append(run_command("core permission matrix", [PYTHON_CMD, "-m", "pytest", "-q", "tests/test_permission_matrix.py"], env, timeout=240))
        phases.append(run_python_snippet("provider network-disabled check", provider_network_disabled_code(), env, timeout=120))
        phases.append(run_command("openapi route parity", [PYTHON_CMD, "-m", "pytest", "-q", "tests/test_openapi_route_parity.py"], env, timeout=120))
        phases.append(run_command("data integrity checks", [PYTHON_CMD, "-m", "pytest", "-q", "tests/test_data_integrity.py"], env, timeout=180))
        phases.append(run_command(
            "formal background job execution ownership",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_formal_background_job_execution.py",
                "tests/test_formal_background_job_concurrency.py",
            ],
            env,
            timeout=240,
        ))
        phases.append(run_command(
            "formal document alignment item bootstrap",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_document_alignment_term_candidates.py",
                "tests/test_document_alignment_item_bootstrap.py",
                "tests/test_document_alignment_item_bootstrap_integration.py",
            ],
            env,
            timeout=240,
        ))
        phases.append(run_command(
            "formal item execution idempotency schema",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_formal_item_verification_execution_models.py",
                "tests/test_formal_item_verification_identity.py",
                "tests/test_formal_item_idempotency_constraints.py",
                "tests/test_formal_item_execution_schema_upgrade.py",
            ],
            env,
            timeout=240,
        ))
        phases.append(run_command(
            "formal item verification transaction adapter",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_document_alignment_item_verification_adapter.py",
                "tests/test_document_alignment_item_verification_adapter_integration.py",
                "tests/test_document_alignment_item_verification_idempotency.py",
                "tests/test_document_alignment_item_verification_security.py",
                "tests/test_document_alignment_item_verification_fault_recovery.py",
            ],
            env,
            timeout=300,
        ))
        phases.append(run_command(
            "formal document alignment processing orchestrator",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_document_alignment_processing_orchestrator.py",
                "tests/test_document_alignment_processing_orchestrator_integration.py",
                "tests/test_document_alignment_processing_partial_failure.py",
                "tests/test_document_alignment_processing_resume.py",
                "tests/test_document_alignment_processing_concurrency.py",
                "tests/test_document_alignment_processing_security.py",
                "tests/test_document_alignment_processing_fault_recovery.py",
            ],
            env,
            timeout=300,
        ))
        phases.append(run_command(
            "formal document alignment worker handler",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_document_alignment_worker_handler.py",
                "tests/test_document_alignment_worker_result_mapping.py",
                "tests/test_document_alignment_worker_integration.py",
                "tests/test_document_alignment_worker_retry_recovery.py",
                "tests/test_document_alignment_worker_concurrency.py",
                "tests/test_document_alignment_worker_legacy_compatibility.py",
                "tests/test_document_alignment_worker_security.py",
            ],
            env,
            timeout=300,
        ))
        phases.append(run_command(
            "formal document alignment provider selection",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_formal_document_alignment_provider_selection.py",
                "tests/test_document_alignment_admission_provider_selection.py",
                "tests/test_document_alignment_provider_preflight_contract.py",
                "tests/test_document_alignment_http_default_provider_flow.py",
            ],
            env,
            timeout=300,
        ))
        phases.append(run_command(
            "formal document alignment retry budget",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_formal_document_alignment_retry_budget_contract.py",
                "tests/test_document_alignment_admission_retry_budget.py",
                "tests/test_document_alignment_http_retry_recovery_contract.py",
                "tests/test_document_alignment_retry_exhaustion_contract.py",
                "tests/test_document_alignment_retry_crash_semantics.py",
            ],
            env,
            timeout=300,
        ))
        phases.append(run_command(
            "formal document alignment query services",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_document_alignment_workflow_query_permissions.py",
                "tests/test_document_alignment_workflow_run_query.py",
                "tests/test_document_alignment_workflow_item_query.py",
                "tests/test_document_alignment_workflow_query_integration.py",
                "tests/test_document_alignment_workflow_query_performance.py",
                "tests/test_document_alignment_workflow_query_security.py",
            ],
            env,
            timeout=240,
        ))
        phases.append(run_command(
            "formal document alignment routes and OpenAPI",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_document_alignment_workflow_routes.py",
                "tests/test_document_alignment_workflow_start_route.py",
                "tests/test_document_alignment_workflow_get_route.py",
                "tests/test_document_alignment_workflow_items_route.py",
                "tests/test_document_alignment_workflow_route_error_mapping.py",
                "tests/test_document_alignment_workflow_openapi.py",
                "tests/test_document_alignment_workflow_route_security.py",
                "tests/test_document_alignment_workflow_route_integration.py",
            ],
            env,
            timeout=300,
        ))
        phases.append(run_command(
            "formal document alignment API end to end",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_document_alignment_production_contract_convergence.py",
                "tests/test_document_alignment_formal_api_e2e.py",
                "tests/test_document_alignment_formal_api_polling.py",
                "tests/test_document_alignment_formal_api_idempotency.py",
                "tests/test_document_alignment_formal_api_permissions.py",
                "tests/test_document_alignment_formal_api_pagination.py",
                "tests/test_document_alignment_formal_api_partial_failure.py",
                "tests/test_document_alignment_formal_api_recovery.py",
                "tests/test_document_alignment_formal_api_security.py",
            ],
            env,
            timeout=600,
        ))
        phases.append(run_command(
            "formal document alignment API artifact",
            [
                PYTHON_CMD,
                "scripts/run_formal_document_alignment_api_e2e.py",
                "--json-output",
                str(formal_api_e2e_json),
                "--recovery-json-output",
                str(formal_recovery_json),
            ],
            env,
            timeout=600,
        ))
        phases.append(run_command("critical e2e workflow", [PYTHON_CMD, "-m", "pytest", "-q", "tests/test_pilot_end_to_end.py"], env, timeout=300))
        browser_phase = run_command(
            "browser e2e",
            [
                PYTHON_CMD,
                "scripts/run_browser_e2e.py",
                "--json-output",
                str(browser_e2e_json),
                "--artifacts",
                str(temp_root / "browser-e2e-artifacts"),
            ],
            env,
            timeout=600,
            condition_returncodes={
                E2E_ENVIRONMENT_UNAVAILABLE: ("UNAVAILABLE", "browser_e2e_not_executed")
            },
        )
        phases.append(browser_phase)
        browser_e2e_result = load_json_result(browser_e2e_json)
        if browser_phase.get("condition") and browser_phase["condition"] not in conditions:
            conditions.append(browser_phase["condition"])
            warnings.append(browser_phase["condition"])
        formal_browser_phase = run_command(
            "formal document alignment browser API e2e",
            [
                PYTHON_CMD,
                "scripts/run_formal_document_alignment_browser_e2e.py",
                "--json-output",
                str(formal_browser_api_json),
            ],
            env,
            timeout=600,
            condition_returncodes={
                E2E_ENVIRONMENT_UNAVAILABLE: (
                    "UNAVAILABLE",
                    "formal_browser_api_e2e_not_executed",
                )
            },
        )
        phases.append(formal_browser_phase)
        if (
            formal_browser_phase.get("status") == "PASS"
            and "FORMAL_API_BROWSER_SESSION_VERIFIED" not in conditions
        ):
            conditions.append("FORMAL_API_BROWSER_SESSION_VERIFIED")
        if formal_browser_phase.get("condition") and formal_browser_phase["condition"] not in conditions:
            conditions.append(formal_browser_phase["condition"])
            warnings.append(formal_browser_phase["condition"])
        phases.append(run_command(
            "formal workflow frontend cutover",
            [
                PYTHON_CMD,
                "-m",
                "pytest",
                "-q",
                "tests/test_formal_workflow_frontend_cutover_contract.py",
                "tests/test_formal_workflow_frontend_state_contract.py",
                "tests/test_formal_workflow_frontend_e2e_runner.py",
                "tests/test_formal_workflow_frontend_security.py",
            ],
            env,
            timeout=180,
        ))
        formal_frontend_phase = run_command(
            "formal workflow frontend UI e2e",
            [
                PYTHON_CMD,
                "scripts/run_formal_workflow_frontend_e2e.py",
                "--json-output",
                str(formal_frontend_e2e_json),
            ],
            env,
            timeout=600,
        )
        phases.append(formal_frontend_phase)
        if (
            formal_frontend_phase.get("status") == "PASS"
            and "FORMAL_FRONTEND_UI_E2E_VERIFIED" not in conditions
        ):
            conditions.append("FORMAL_FRONTEND_UI_E2E_VERIFIED")
        formal_frontend_resume_phase = run_command(
            "formal workflow frontend resume e2e",
            [
                PYTHON_CMD,
                "scripts/run_formal_workflow_frontend_resume_e2e.py",
                "--json-output",
                str(formal_frontend_resume_json),
            ],
            env,
            timeout=600,
        )
        phases.append(formal_frontend_resume_phase)
        if (
            formal_frontend_resume_phase.get("status") == "PASS"
            and "FORMAL_FRONTEND_RESUME_E2E_VERIFIED" not in conditions
        ):
            conditions.append("FORMAL_FRONTEND_RESUME_E2E_VERIFIED")
        phases.append(run_python_snippet("lightweight performance smoke", performance_smoke_code(), env, timeout=120))
        phases.append(
            run_python_snippet(
                "verdict consistency",
                f"""
from pathlib import Path
report = Path("docs/pilot_readiness_report.md").read_text(encoding="utf-8")
assert "READY WITH CONDITIONS" in report or "READY_WITH_CONDITIONS" in report
print("report verdict documents READY WITH CONDITIONS")
""",
                env,
                timeout=60,
            )
        )

        if db_path.exists():
            print(f"\nTemporary database rows: concept_cards={table_count(db_path, 'concept_alignment_card')}, audits={table_count(db_path, 'audit_record')}")
        shutil.rmtree(upload_dir, ignore_errors=True)

        print("\nPilot readiness phase summary:")
        for phase in phases:
            condition = f" [{phase['condition']}]" if phase.get("condition") else ""
            print(f"- {phase['status']}: {phase['name']} ({phase['elapsed_ms']} ms){condition}")

        payload = build_readiness_payload(
            profile=args.profile,
            checks=[dict(phase) for phase in phases],
            conditions=conditions,
            warnings=warnings,
            browser_e2e=summarize_browser_e2e_result(browser_e2e_result),
        )
        if args.json_output:
            Path(args.json_output).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        printable_verdict = payload["verdict"].replace("_", " ")
        print(f"\n{payload['verdict']}")
        print(f"Pilot readiness verdict: {printable_verdict}")
        if payload["conditions"]:
            print("Conditions: " + ", ".join(payload["conditions"]))
        return 0 if payload["verdict"] != NOT_READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
