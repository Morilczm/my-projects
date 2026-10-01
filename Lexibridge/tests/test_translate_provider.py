"""Tests for glossary, registry, batch, and layout-block APIs of translate_provider."""

import json
import urllib.error

import pytest

from services import translate_provider
from services.layout_analysis import BoundingBox, LayoutBlock
from services.translate_provider import (
    TranslationProvider,
    format_glossary_prompt,
    lookup_glossary,
    normalize_glossary,
    parse_provider_chain,
    register_provider,
    translate_layout_blocks,
    translate_term,
    translate_terms_batch,
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


def _mock_ollama(monkeypatch, chat_content="卷积"):
    captured = {}

    def fake_urlopen(request, timeout=None):
        if request.full_url.endswith("/api/tags"):
            return _FakeResponse({"models": [{"name": "translategemma:12b"}]})
        if request.full_url.endswith("/api/chat"):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": chat_content}})
        raise AssertionError(f"unexpected url: {request.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return captured


def _block(text, layout_type="text", page=1, order=1):
    return LayoutBlock(
        page_number=page,
        text=text,
        bbox=BoundingBox(0, 0, 100, 20),
        layout_type=layout_type,
        reading_order=order,
        page_width=612,
        page_height=792,
    )


# --- glossary ----------------------------------------------------------------

def test_glossary_hit_short_circuits_model_call(monkeypatch):
    def _forbidden(request, timeout=None):
        raise AssertionError("model must not be called on glossary hit")

    monkeypatch.setattr("urllib.request.urlopen", _forbidden)
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")

    result = translate_term("convolution", glossary={"Convolution": "卷积（自定义）"})

    assert result["status"] == "ok"
    assert result["chinese_term"] == "卷积（自定义）"
    assert result["provider"] == "glossary"
    assert result["glossary_hit"] is True


def test_glossary_injected_into_prompt_on_miss(monkeypatch):
    captured = _mock_ollama(monkeypatch)
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")

    result = translate_term("Hash Table", glossary={"Fourier Transform": "傅里叶变换"})

    assert result["status"] == "ok"
    system_prompt = captured["payload"]["messages"][0]["content"]
    assert "严格统一使用该译法" in system_prompt
    assert "Fourier Transform = 傅里叶变换" in system_prompt


def test_glossary_lookup_case_insensitive_and_limits():
    glossary = normalize_glossary({" Fourier Transform ": "傅里叶变换", "": "空", "Hash Table": ""})
    assert lookup_glossary(glossary, "fourier transform") == "傅里叶变换"
    assert lookup_glossary(glossary, "hash table") == ""
    assert normalize_glossary({"a": "1", "b": "2", "c": "3"}, max_entries=2) == {"a": "1", "b": "2"}
    assert format_glossary_prompt({}) == ""


# --- registry ------------------------------------------------------------------

class _DummyProvider(TranslationProvider):
    provider_name = "dummy"

    def is_available(self):
        return True

    def translate_term(self, english_term, context_sentence="", glossary=None):
        return {
            "status": "ok",
            "chinese_term": f"dummy:{english_term}",
            "provider": "dummy",
            "model": "dummy-v0",
            "error": "",
        }


def test_register_provider_manual_and_auto(monkeypatch):
    monkeypatch.setitem(translate_provider._PROVIDER_REGISTRY, "dummy", _DummyProvider)

    manual = translate_term("Convolution", provider="dummy")
    assert manual["status"] == "ok"
    assert manual["chinese_term"] == "dummy:Convolution"

    monkeypatch.setenv("TRANSLATION_PROVIDER_CHAIN", "dummy")
    routed = translate_term("Convolution", provider="auto")
    assert routed["status"] == "ok"
    assert routed["provider"] == "dummy"
    assert routed["attempted"] == ["dummy"]
    assert "dummy" in parse_provider_chain("dummy")


def test_register_provider_rejects_reserved_names():
    with pytest.raises(ValueError):
        register_provider("auto", _DummyProvider)
    with pytest.raises(ValueError):
        register_provider("glossary", _DummyProvider)


# --- batch ---------------------------------------------------------------------

def test_translate_terms_batch_mixed_glossary_and_model(monkeypatch):
    captured = _mock_ollama(monkeypatch, chat_content="哈希表")
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")

    results = translate_terms_batch(
        ["Convolution", "Hash Table"],
        glossary={"Convolution": "卷积"},
    )

    assert [r["chinese_term"] for r in results] == ["卷积", "哈希表"]
    assert results[0]["glossary_hit"] is True
    assert results[1]["provider"] == "ollama"


# --- layout blocks ---------------------------------------------------------------

def test_translate_layout_blocks_skips_non_text_types(monkeypatch):
    _mock_ollama(monkeypatch, chat_content="傅里叶变换")
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")
    blocks = [
        _block("Course Notes", layout_type="header_footer"),
        _block("Fourier Transform", layout_type="title"),
        _block("∫ f(x) dx", layout_type="formula"),
    ]

    translated = translate_layout_blocks(blocks)

    assert translated[0]["skipped"] is True
    assert translated[1]["skipped"] is False
    assert translated[1]["translated_text"] == "傅里叶变换"
    assert translated[1]["layout_type"] == "title"
    assert translated[1]["source_text"] == "Fourier Transform"
    assert translated[2]["skipped"] is True


def test_translate_layout_blocks_unavailable_provider_never_raises(monkeypatch):
    def _refused(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _refused)
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")
    blocks = [_block("Fourier Transform", layout_type="title")]

    translated = translate_layout_blocks(blocks)

    assert len(translated) == 1
    assert translated[0]["skipped"] is True
    assert translated[0]["translated_text"] == ""


def test_translate_layout_blocks_glossary_hit(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "none")
    blocks = [_block("Hash Table", layout_type="text")]

    translated = translate_layout_blocks(blocks, glossary={"Hash Table": "哈希表"})

    assert translated[0]["skipped"] is False
    assert translated[0]["provider"] == "glossary"
    assert translated[0]["translated_text"] == "哈希表"
