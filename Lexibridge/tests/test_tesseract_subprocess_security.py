import subprocess

from services import ocr


def _ok_tsv(text="Eigenvalue"):
    return "\n".join([
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        f"5\t1\t1\t1\t1\t1\t10\t20\t90\t25\t95.0\t{text}",
    ])


def test_tesseract_subprocess_uses_argument_list_and_shell_false(monkeypatch, tmp_path):
    executable = tmp_path / "tesseract"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    image = tmp_path / "scan;touch-not-run.png"
    image.write_bytes(b"fake image")
    captured = {"commands": []}

    def fake_run(cmd, **kwargs):
        captured["commands"].append((cmd, kwargs.get("shell")))
        return subprocess.CompletedProcess(cmd, 0, stdout=_ok_tsv(), stderr="")

    monkeypatch.setenv("LEXIBRIDGE_TESSERACT_CMD", str(executable))
    monkeypatch.setattr(ocr.subprocess, "run", fake_run)

    result = ocr.TesseractOCRProvider().recognize_image(str(image), language="en")

    assert result.ok
    image_commands = [cmd for cmd, shell in captured["commands"] if str(image) in cmd]
    assert image_commands
    assert all(isinstance(cmd, list) for cmd, _shell in captured["commands"])
    assert all(shell is False for _cmd, shell in captured["commands"])
    assert "--psm" in image_commands[0]


def test_tesseract_error_sanitizes_stderr_and_paths(monkeypatch, tmp_path):
    executable = tmp_path / "tesseract"
    executable.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    executable.chmod(0o755)
    image = tmp_path / "scan.png"
    image.write_bytes(b"fake image")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr=f"OCR_TEST_PRIVATE_MARKER_10CP1 failed at {image}",
        )

    monkeypatch.setenv("LEXIBRIDGE_TESSERACT_CMD", str(executable))
    monkeypatch.setattr(ocr.subprocess, "run", fake_run)

    result = ocr.TesseractOCRProvider().recognize_image(str(image), language="en")

    assert result.status == "ocr_failed"
    assert "OCR_TEST_PRIVATE_MARKER_10CP1" not in result.error
    assert str(image) not in result.error


def test_tesseract_timeout_returns_safe_failure(monkeypatch, tmp_path):
    executable = tmp_path / "tesseract"
    executable.write_text("#!/bin/sh\nsleep 99\n", encoding="utf-8")
    executable.chmod(0o755)
    image = tmp_path / "scan.png"
    image.write_bytes(b"fake image")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 1))

    monkeypatch.setenv("LEXIBRIDGE_TESSERACT_CMD", str(executable))
    monkeypatch.setattr(ocr.subprocess, "run", fake_run)

    result = ocr.TesseractOCRProvider().recognize_image(str(image), language="en")

    assert result.status == "ocr_failed"
    assert result.quality_flags == ["ocr_timeout"]
    assert "path" not in result.error.lower()
