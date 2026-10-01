import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from services import controlled_provider_evaluation as cpe


def _proposal(term="时间复杂度", *, abstain=False):
    return json.dumps({
        "chinese_term": "" if abstain else term,
        "chinese_explanation": "" if abstain else "安全合成上下文中的中文候选。",
        "alignment_rationale": "Uses only bounded synthetic context.",
        "alternative_candidates": [],
        "risk_labels": ["provider_generated_candidate"],
        "abstain": abstain,
        "abstain_reason": "ambiguous_without_context" if abstain else "",
        "provider_name": "loopback-provider",
        "model_name": "candidate-model",
        "prompt_version": "provider-chinese-candidate-evaluation-v1",
        "output_schema_version": "provider-chinese-candidate-proposal-v1",
    }, ensure_ascii=False).encode("utf-8")


class _FakeProvider(BaseHTTPRequestHandler):
    scenario = "success"
    call_count = 0
    bodies = []

    def do_POST(self):
        type(self).call_count += 1
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).bodies.append(body.decode("utf-8"))
        scenario = type(self).scenario
        if scenario == "success":
            self._send(200, _proposal())
        elif scenario == "abstain":
            self._send(200, _proposal(abstain=True))
        elif scenario == "malformed":
            self._send(200, b"{not-json")
        elif scenario == "unknown_fields":
            payload = _proposal().decode("utf-8")[:-1] + ',"extra":"field"}'
            self._send(200, payload.encode("utf-8"))
        elif scenario == "code_fence":
            self._send(200, b"```json\n{}\n```")
        elif scenario == "trailing":
            self._send(200, _proposal() + b" prose")
        elif scenario == "rate_then_success":
            if type(self).call_count == 1:
                self._send(429, b'{"error":"rate"}')
            else:
                self._send(200, _proposal("复杂度"))
        elif scenario == "always_429":
            self._send(429, b'{"error":"rate"}')
        elif scenario == "server_then_success":
            if type(self).call_count == 1:
                self._send(500, b'{"error":"server"}')
            else:
                self._send(200, _proposal("复杂度"))
        elif scenario == "always_500":
            self._send(500, b'{"error":"server"}')
        elif scenario == "large":
            self._send(200, b"x" * (cpe.MAX_RESPONSE_BYTES + 1))
        elif scenario == "redirect":
            self.send_response(302)
            self.send_header("Location", "https://example.com/elsewhere")
            self.end_headers()
        else:
            self._send(500, b'{"error":"unknown"}')

    def _send(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


@pytest.fixture()
def fake_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeProvider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()


def _items(count=1):
    return [
        cpe.build_evaluation_input({
            "evaluation_item_uid": f"fake-item-{idx:03d}",
            "course_or_domain": "computer science",
            "english_term": "time complexity",
            "normalized_english_term": "time complexity",
            "bounded_context": "Time complexity describes algorithm growth.",
            "context_source_type": "synthetic_fixture",
            "privacy_classification": "SYNTHETIC",
        })
        for idx in range(count)
    ]


def _run(fake_server, scenario, items=None):
    _FakeProvider.scenario = scenario
    _FakeProvider.call_count = 0
    _FakeProvider.bodies = []
    return cpe.run_controlled_provider_evaluation(
        items or _items(),
        provider_name="loopback-provider",
        model_name="candidate-model",
        credential_loader=cpe.StaticCredentialLoader(cpe.test_sentinel_value()),
        pricing=cpe.test_pricing_config(),
        budget=cpe.test_budget_config(max_total_requests=80),
        transport=cpe.SafeEvaluationHTTPTransport(max_retries=1),
        execute_live=True,
        evaluation_test_mode=True,
        test_endpoint=f"http://127.0.0.1:{fake_server.server_port}/v1/candidates",
        test_loopback_ports={fake_server.server_port},
    )


def test_40_item_fake_provider_success_e2e(fake_server):
    run = _run(fake_server, "success", _items(40))

    assert len(run.results) == 40
    assert run.status_counts()["SUCCEEDED"] == 40
    assert run.actual_external_provider_requests == 0
    assert run.private_course_provider_requests == 0
    assert "source_uid" not in "".join(_FakeProvider.bodies)
    assert cpe.test_sentinel_value() not in "".join(_FakeProvider.bodies)


@pytest.mark.parametrize("scenario,status,error", [
    ("abstain", "ABSTAINED", ""),
    ("malformed", "OUTPUT_INVALID", "provider_output_not_json"),
    ("unknown_fields", "OUTPUT_INVALID", "provider_output_unknown_fields"),
    ("code_fence", "OUTPUT_INVALID", "provider_output_code_fence"),
    ("trailing", "OUTPUT_INVALID", "provider_output_not_json"),
    ("rate_then_success", "SUCCEEDED", ""),
    ("always_429", "TRANSPORT_FAILED", "provider_rate_limited"),
    ("server_then_success", "SUCCEEDED", ""),
    ("always_500", "TRANSPORT_FAILED", "provider_server_error"),
    ("large", "TRANSPORT_FAILED", "response_too_large"),
    ("redirect", "TRANSPORT_FAILED", "redirect_rejected"),
])
def test_fake_provider_failure_matrix(fake_server, scenario, status, error):
    run = _run(fake_server, scenario)

    assert run.results[0].status == status
    if error:
        assert run.results[0].safe_error_code == error
    assert run.results[0].can_auto_approve is False
