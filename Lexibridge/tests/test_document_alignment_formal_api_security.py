import json
import socket

import pytest

from scripts import run_formal_document_alignment_api_e2e as api_runner
from scripts import run_formal_document_alignment_browser_e2e as browser_runner
from formal_document_alignment_retry_support import claim
from scripts.formal_document_alignment_api_e2e_support import (
    assert_safe_public_payload,
    block_external_network,
    cleanup_formal_api_state,
    create_formal_source,
    find_job_for_run,
    http_json,
    login,
    start_threaded_server,
)
from services.document_alignment_worker_handler import (
    run_claimed_formal_document_alignment_job,
)


SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C5G_V3"


@pytest.fixture(autouse=True)
def clean_state(app_module):
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)
    yield
    with app_module.app.app_context():
        cleanup_formal_api_state(app_module)


def test_formal_http_responses_hide_transport_execution_and_private_content(app_module):
    with app_module.app.app_context():
        source = create_formal_source(
            app_module,
            suffix="security",
            terms=("Fourier Transform",),
            bilingual_terms={"Fourier Transform": "傅里叶变换"},
        )
        stored_source = app_module.KnowledgeSource.query.filter_by(
            source_uid=source.source_uid
        ).one()
        stored_source.title = SENTINEL
        parse = app_module.DocumentParseRecord.query.filter_by(
            parse_uid=stored_source.parse_uid
        ).one()
        parse.source_filename = f"/private/tmp/{SENTINEL}/source.txt"
        private_chunk = app_module.KnowledgeChunk.query.filter_by(
            source_uid=source.source_uid
        ).first()
        private_chunk.content = f"Fourier Transform {SENTINEL}"
        app_module.db.session.commit()

    with start_threaded_server(app_module.app) as server, block_external_network() as external:
        teacher = login(server.base_url, "teacher.test@lexibridge.local", "Teacher1234")
        started = http_json(
            server.base_url,
            "/api/document-alignment-runs",
            method="POST",
            token=teacher.token,
            body={"source_uid": source.source_uid},
            headers={"Idempotency-Key": "security-key"},
        )
        assert started.status == 202
        run_uid = started.body["data"]["run_uid"]
        with app_module.app.app_context():
            job_uid = find_job_for_run(app_module, run_uid).job_uid
            lease = claim(
                app_module,
                "security-worker",
                expected_job_uid=job_uid,
                token=f"{SENTINEL}-LEASE",
            )
            result = run_claimed_formal_document_alignment_job(
                lease,
                app_module._formal_worker_handler_dependencies(lease),
            )
            assert result.outcome == "completed"

        run = http_json(
            server.base_url,
            f"/api/document-alignment-runs/{run_uid}",
            token=teacher.token,
        )
        items = http_json(
            server.base_url,
            f"/api/document-alignment-runs/{run_uid}/items",
            token=teacher.token,
        )
        assert run.status == items.status == 200
        for response in (started, run, items):
            assert_safe_public_payload(response.body, sentinel=SENTINEL)
            assert SENTINEL not in json_headers(response.headers)
        assert external == []


def json_headers(headers):
    return "\n".join(f"{key}: {value}" for key, value in headers.items())


def test_browser_api_artifact_contract_excludes_session_secrets():
    result = browser_runner.build_browser_result(
        verdict="PASS",
        scenarios=[{"name": "teacher_browser_api", "status": "PASS"}],
        browser_version="test",
        console_errors=[],
        page_errors=[],
        external_requests=[],
    )

    assert result["verdict"] == "PASS"
    assert result["actual_external_dependency_requests"] == 0
    assert "token" not in str(result).casefold()


def test_external_network_guard_records_blocked_python_attempt_in_caller_list():
    attempts = []

    with block_external_network(attempts):
        with pytest.raises(AssertionError, match="external network request blocked"):
            socket.create_connection(("example.invalid", 443))

    assert attempts == [{"source": "python"}]


def test_api_failure_artifacts_retain_network_count_and_hide_raw_exception(
    monkeypatch,
    tmp_path,
):
    sensitive_path = "/" + "Users/private/provider-output"

    def fail(**kwargs):
        kwargs["external_requests"].append({"source": "python"})
        raise RuntimeError(f"{SENTINEL} {sensitive_path}")

    monkeypatch.setattr(api_runner, "run_api_checks", fail)
    api_output = tmp_path / "api.json"
    recovery_output = tmp_path / "recovery.json"

    assert api_runner.main([
        "--json-output",
        str(api_output),
        "--recovery-json-output",
        str(recovery_output),
    ]) == 1

    for path in (api_output, recovery_output):
        payload = json.loads(path.read_text(encoding="utf-8"))
        serialized = json.dumps(payload)
        assert payload["actual_external_dependency_requests"] == 1
        assert SENTINEL not in serialized
        assert sensitive_path not in serialized


def test_browser_failure_artifact_retains_network_count_and_hides_raw_exception(
    monkeypatch,
    tmp_path,
):
    def fail(**kwargs):
        kwargs["external_requests"].append({"source": "python"})
        raise RuntimeError(f"{SENTINEL} /private/provider-output")

    monkeypatch.setattr(browser_runner, "run_browser_checks", fail)
    output = tmp_path / "browser.json"

    assert browser_runner.main(["--json-output", str(output)]) == 1

    payload = json.loads(output.read_text(encoding="utf-8"))
    serialized = json.dumps(payload)
    assert payload["actual_external_dependency_requests"] == 1
    assert SENTINEL not in serialized
    assert "/private/" not in serialized
