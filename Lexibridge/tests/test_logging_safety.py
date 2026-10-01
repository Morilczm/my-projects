from services.logging_config import redact_sensitive_value, safe_log_context


def test_redact_sensitive_values():
    assert redact_sensitive_value("Bearer abcdefghijklmnop") == "[REDACTED]"
    assert redact_sensitive_value("sk-1234567890abcdef") == "[REDACTED]"


def test_safe_log_context_removes_password_token_and_api_key():
    context = safe_log_context({
        "user_id": 1,
        "password": "Secret1234",
        "token": "Bearer abcdefghijklmnop",
        "DEEPSEEK_API_KEY": "sk-1234567890abcdef",
    })
    assert context["user_id"] == 1
    assert context["password"] == "[REDACTED]"
    assert context["token"] == "[REDACTED]"
    assert context["DEEPSEEK_API_KEY"] == "[REDACTED]"


def test_long_content_and_ocr_ai_fields_are_safe():
    long_text = "x" * 500
    context = safe_log_context({
        "summary": long_text,
        "ocr_text": "full OCR text should not be logged",
        "ai_prompt": "full prompt should not be logged",
        "ai_response": "full response should not be logged",
    })
    assert "truncated" in context["summary"]
    assert context["ocr_text"] == "[REDACTED]"
    assert context["ai_prompt"] == "[REDACTED]"
    assert context["ai_response"] == "[REDACTED]"
