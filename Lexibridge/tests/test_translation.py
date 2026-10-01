"""Tests for the optional small-LLM term translation providers."""

import io
import json
import urllib.error

import pytest

from services import translate_provider as translation
from services.translate_provider import (
    OllamaTranslationProvider,
    clean_translated_term,
    get_translation_provider,
    parse_provider_chain,
    translate_term,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def _mock_ollama(monkeypatch, tags_payload, chat_payload=None, chat_error=None):
    def fake_urlopen(request, timeout=None):
        url = request.full_url
        if url.endswith("/api/tags"):
            return _FakeResponse(tags_payload)
        if url.endswith("/api/chat"):
            if chat_error is not None:
                raise chat_error
            return _FakeResponse(chat_payload)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


def test_default_provider_is_none_and_unavailable(monkeypatch):
    monkeypatch.delenv("TRANSLATION_PROVIDER", raising=False)

    result = translate_term("Fourier Transform")

    assert result["status"] == "translation_unavailable"
    assert result["provider"] == "none"
    assert result["chinese_term"] == ""


def test_unknown_provider_degrades_to_unavailable(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "not-a-real-provider")

    result = translate_term("Fourier Transform")

    assert result["status"] == "translation_unavailable"
    assert "Unknown translation provider" in result["error"]


def test_ollama_unreachable_reports_unavailable(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")

    def _refused(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _refused)

    result = translate_term("Fourier Transform")

    assert result["status"] == "translation_unavailable"
    assert result["provider"] == "ollama"
    assert "not available" in result["error"]


def test_ollama_model_missing_reports_unavailable(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")
    _mock_ollama(monkeypatch, tags_payload={"models": [{"name": "qwen3:8b"}]})

    result = translate_term("Fourier Transform")

    assert result["status"] == "translation_unavailable"


def test_ollama_translation_success_cleans_term(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")
    _mock_ollama(
        monkeypatch,
        tags_payload={"models": [{"name": "translategemma:12b"}]},
        chat_payload={"message": {"content": "“傅里叶变换”。\n一种积分变换"}},
    )

    result = translate_term("Fourier Transform", context_sentence="The Fourier Transform maps signals.")

    assert result["status"] == "ok"
    assert result["chinese_term"] == "傅里叶变换"
    assert result["model"] == "translategemma:12b"


def test_ollama_empty_response_is_failed_not_exception(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")
    _mock_ollama(
        monkeypatch,
        tags_payload={"models": [{"name": "translategemma:12b"}]},
        chat_payload={"message": {"content": ""}},
    )

    result = translate_term("Fourier Transform")

    assert result["status"] == "translation_failed"
    assert result["chinese_term"] == ""


def test_translate_term_never_raises(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")
    monkeypatch.setattr(
        translation,
        "get_translation_provider",
        lambda name=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = translate_term("Fourier Transform")

    assert result["status"] == "translation_failed"
    assert "boom" in result["error"]


def test_clean_translated_term_cases():
    assert clean_translated_term("傅里叶变换。") == "傅里叶变换"
    assert clean_translated_term('"哈希表"') == "哈希表"
    assert clean_translated_term("  卷积\n\n解释文字") == "卷积"
    assert clean_translated_term("") == ""
    assert clean_translated_term("x" * 80) == ""


def test_provider_factory_names(monkeypatch):
    monkeypatch.delenv("TRANSLATION_PROVIDER", raising=False)
    assert get_translation_provider().provider_name == "none"
    assert get_translation_provider("ollama").provider_name == "ollama"
    assert isinstance(get_translation_provider("OLLAMA"), OllamaTranslationProvider)


def test_parse_provider_chain_drops_unknown_and_duplicates():
    assert parse_provider_chain("bogus, ollama,,ollama") == ["ollama"]
    assert parse_provider_chain("") == []


def test_auto_chain_all_unavailable_reports_attempts(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "auto")
    monkeypatch.delenv("TRANSLATION_PROVIDER_CHAIN", raising=False)

    def _refused(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _refused)

    result = translate_term("Fourier Transform")

    assert result["status"] == "translation_unavailable"
    assert result["attempted"] == ["ollama"]
    assert "ollama" in result["error"]


def test_auto_chain_first_success_wins(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "auto")
    monkeypatch.setenv("TRANSLATION_PROVIDER_CHAIN", "ollama")
    _mock_ollama(
        monkeypatch,
        tags_payload={"models": [{"name": "translategemma:12b"}]},
        chat_payload={"message": {"content": "卷积"}},
    )

    result = translate_term("Convolution")

    assert result["status"] == "ok"
    assert result["chinese_term"] == "卷积"
    assert result["provider"] == "ollama"
    assert result["attempted"] == ["ollama"]


def test_auto_chain_skips_unknown_names(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "auto")
    monkeypatch.setenv("TRANSLATION_PROVIDER_CHAIN", "bogus,ollama")
    _mock_ollama(
        monkeypatch,
        tags_payload={"models": [{"name": "translategemma:12b"}]},
        chat_payload={"message": {"content": "卷积"}},
    )

    result = translate_term("Convolution")

    assert result["status"] == "ok"
    assert result["attempted"] == ["ollama"]


def test_auto_empty_chain_is_unavailable(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "auto")
    monkeypatch.setenv("TRANSLATION_PROVIDER_CHAIN", "")

    result = translate_term("Fourier Transform")

    assert result["status"] == "translation_unavailable"
    assert result["attempted"] == []
    assert "empty" in result["error"]
