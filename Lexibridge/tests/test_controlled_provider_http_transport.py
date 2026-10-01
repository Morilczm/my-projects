import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from services import controlled_provider_evaluation as cpe


class _Handler(BaseHTTPRequestHandler):
    responses = []
    seen = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).seen.append({
            "path": self.path,
            "request_id": self.headers.get("X-LexiBridge-Request-Id"),
            "body": body.decode("utf-8"),
        })
        response = type(self).responses.pop(0)
        status, headers, payload = response
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


def _server(responses):
    _Handler.responses = list(responses)
    _Handler.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_loopback_transport_posts_json_only_in_test_mode():
    server = _server([(200, {"Content-Type": "application/json"}, b'{"ok": true}')])
    try:
        transport = cpe.SafeEvaluationHTTPTransport()
        result = transport.post_json(
            url=f"http://127.0.0.1:{server.server_port}/v1/candidates",
            allowed_hosts={"127.0.0.1"},
            payload={"safe": True},
            credential=cpe.Credential("runtime-only-test-value"),
            request_id="req-stable",
            evaluation_test_mode=True,
            test_loopback_ports={server.server_port},
        )
    finally:
        server.shutdown()

    assert result.status == "success"
    assert json.loads(result.raw_output) == {"ok": True}
    assert _Handler.seen[0]["request_id"] == "req-stable"


def test_loopback_and_external_http_are_rejected_outside_test_mode():
    transport = cpe.SafeEvaluationHTTPTransport()
    loopback = transport.post_json(
        url="http://127.0.0.1:12345/v1/candidates",
        allowed_hosts={"127.0.0.1"},
        payload={},
        credential=cpe.Credential("runtime-only-test-value"),
        request_id="req",
        evaluation_test_mode=False,
    )
    external_http = transport.post_json(
        url="http://example.com/v1/candidates",
        allowed_hosts={"example.com"},
        payload={},
        credential=cpe.Credential("runtime-only-test-value"),
        request_id="req",
        evaluation_test_mode=False,
    )

    assert loopback.error_code == "endpoint_rejected"
    assert external_http.error_code == "endpoint_rejected"


def test_transport_retries_429_with_stable_request_id_and_rejects_redirect():
    success_body = b'{"chinese_term":"x"}'
    retry_server = _server([
        (429, {"Content-Type": "application/json"}, b'{"error":"rate"}'),
        (200, {"Content-Type": "application/json"}, success_body),
    ])
    try:
        result = cpe.SafeEvaluationHTTPTransport(max_retries=1).post_json(
            url=f"http://127.0.0.1:{retry_server.server_port}/v1/candidates",
            allowed_hosts={"127.0.0.1"},
            payload={"term": "x"},
            credential=cpe.Credential("runtime-only-test-value"),
            request_id="req-retry",
            evaluation_test_mode=True,
            test_loopback_ports={retry_server.server_port},
        )
    finally:
        retry_server.shutdown()
    assert result.status == "success"
    assert result.retry_count == 1
    assert [seen["request_id"] for seen in _Handler.seen] == ["req-retry", "req-retry"]

    redirect_server = _server([(302, {"Location": "https://example.com/elsewhere"}, b"")])
    try:
        redirect = cpe.SafeEvaluationHTTPTransport().post_json(
            url=f"http://127.0.0.1:{redirect_server.server_port}/v1/candidates",
            allowed_hosts={"127.0.0.1"},
            payload={"term": "x"},
            credential=cpe.Credential("runtime-only-test-value"),
            request_id="req-redirect",
            evaluation_test_mode=True,
            test_loopback_ports={redirect_server.server_port},
        )
    finally:
        redirect_server.shutdown()
    assert redirect.error_code == "redirect_rejected"


def test_transport_rejects_invalid_content_type_and_large_response():
    html_server = _server([(200, {"Content-Type": "text/html"}, b"<html></html>")])
    try:
        html = cpe.SafeEvaluationHTTPTransport().post_json(
            url=f"http://127.0.0.1:{html_server.server_port}/v1/candidates",
            allowed_hosts={"127.0.0.1"},
            payload={},
            credential=cpe.Credential("runtime-only-test-value"),
            request_id="req-html",
            evaluation_test_mode=True,
            test_loopback_ports={html_server.server_port},
        )
    finally:
        html_server.shutdown()
    assert html.error_code == "invalid_content_type"

    large_server = _server([(200, {"Content-Type": "application/json"}, b"x" * (cpe.MAX_RESPONSE_BYTES + 1))])
    try:
        large = cpe.SafeEvaluationHTTPTransport().post_json(
            url=f"http://127.0.0.1:{large_server.server_port}/v1/candidates",
            allowed_hosts={"127.0.0.1"},
            payload={},
            credential=cpe.Credential("runtime-only-test-value"),
            request_id="req-large",
            evaluation_test_mode=True,
            test_loopback_ports={large_server.server_port},
        )
    finally:
        large_server.shutdown()
    assert large.error_code == "response_too_large"
