import os
import stat

from services import ocr


def _make_executable(path):
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_tesseract_env_executable_takes_priority(monkeypatch, tmp_path):
    configured = _make_executable(tmp_path / "configured-tesseract")
    path_candidate = _make_executable(tmp_path / "path-tesseract")
    monkeypatch.setenv("LEXIBRIDGE_TESSERACT_CMD", str(configured))
    monkeypatch.setattr(ocr.shutil, "which", lambda name: str(path_candidate))

    discovery = ocr.discover_tesseract_executable()

    assert discovery.discovery_source == "environment"
    assert discovery.executable_path == str(configured)


def test_invalid_configured_tesseract_fails_closed_without_path_fallback(monkeypatch, tmp_path):
    path_candidate = _make_executable(tmp_path / "path-tesseract")
    monkeypatch.setenv("LEXIBRIDGE_TESSERACT_CMD", str(tmp_path / "missing-tesseract"))
    monkeypatch.setattr(ocr.shutil, "which", lambda name: str(path_candidate))

    discovery = ocr.discover_tesseract_executable()

    assert discovery.executable_path == ""
    assert discovery.discovery_source == "not_found"
    assert discovery.safe_error_code == "TESSERACT_EXECUTABLE_NOT_RUNNABLE"


def test_tesseract_path_fallback_when_environment_absent(monkeypatch, tmp_path):
    path_candidate = _make_executable(tmp_path / "path-tesseract")
    monkeypatch.delenv("LEXIBRIDGE_TESSERACT_CMD", raising=False)
    monkeypatch.setattr(ocr.shutil, "which", lambda name: str(path_candidate))

    discovery = ocr.discover_tesseract_executable()

    assert discovery.discovery_source == "path"
    assert discovery.executable_path == str(path_candidate)


def test_windows_path_with_spaces_is_treated_as_single_executable_reference(monkeypatch):
    windows_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    discovery = ocr.discover_tesseract_executable(
        env={"LEXIBRIDGE_TESSERACT_CMD": windows_path},
        which_func=lambda name: "",
        is_file=lambda value: value == windows_path,
        is_executable=lambda value: value == windows_path,
    )

    assert discovery.discovery_source == "environment"
    assert discovery.executable_path == windows_path


def test_tesseract_language_allowlist_rejects_arbitrary_arguments():
    assert ocr.resolve_tesseract_language("en") == "eng"
    assert ocr.resolve_tesseract_language("zh") == "chi_sim"
    assert ocr.resolve_tesseract_language("mixed") == "eng+chi_sim"
    assert ocr.resolve_tesseract_language("eng;--psm 1") is None
    assert ocr.resolve_tesseract_language("eng+custom") is None
