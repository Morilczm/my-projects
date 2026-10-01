from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path


TESSERACT_CMD_ENV = "LEXIBRIDGE_TESSERACT_CMD"
TESSDATA_PREFIX_ENV = "LEXIBRIDGE_TESSDATA_PREFIX"
TESSERACT_DEFAULT_LANGUAGE = "eng+chi_sim"
TESSERACT_REQUIRED_HEALTH_LANGS = {"eng", "chi_sim", "osd"}
TESSERACT_LANGUAGE_ALIASES = {
    "": TESSERACT_DEFAULT_LANGUAGE,
    "en": "eng",
    "eng": "eng",
    "english": "eng",
    "zh": "chi_sim",
    "cn": "chi_sim",
    "chinese": "chi_sim",
    "chi_sim": "chi_sim",
    "simplified_chinese": "chi_sim",
    "bilingual": "eng+chi_sim",
    "mixed": "eng+chi_sim",
    "eng+chi_sim": "eng+chi_sim",
    "orientation": "osd",
    "osd": "osd",
}
TESSERACT_OUTPUT_LIMIT_BYTES = 5 * 1024 * 1024
TESSERACT_ERROR_LIMIT_CHARS = 220
LOCAL_PATH_RE = re.compile(
    r"([A-Za-z]:\\[^\s\"']+|/(?:private|tmp|var|Volumes|Users)/[^\s\"']+)",
    re.IGNORECASE,
)
SENTINEL_RE = re.compile(
    r"(?:LEXIBRIDGE_(?:SENTINEL|SYNTHETIC|SECRET)|OCR_TEST_PRIVATE_MARKER)[A-Z0-9_:-]*",
    re.IGNORECASE,
)


def _env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _normalize_language(language):
    language = (language or "").strip().lower()
    if language in {"zh", "cn", "chinese", "chi_sim", "bilingual", "mixed"}:
        return "zh"
    if language in {"en", "english", "eng"}:
        return "en"
    return language or "bilingual"


def _platform_id() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def _safe_error_text(value: object, default: str = "Tesseract execution failed.") -> str:
    text = " ".join(str(value or "").split())
    if not text:
        text = default
    text = SENTINEL_RE.sub("<REDACTED>", text)
    text = LOCAL_PATH_RE.sub("<LOCAL_PATH>", text)
    return text[:TESSERACT_ERROR_LIMIT_CHARS]


def _default_is_file(value: str) -> bool:
    try:
        return Path(value).is_file()
    except (OSError, ValueError):
        return False


def _default_is_executable(value: str) -> bool:
    if not _default_is_file(value):
        return False
    if _platform_id() == "windows":
        return True
    return os.access(value, os.X_OK)


@dataclass(frozen=True)
class TesseractExecutableDiscovery:
    executable_path: str = ""
    discovery_source: str = "not_found"
    safe_error_code: str | None = "TESSERACT_EXECUTABLE_NOT_FOUND"


@dataclass(frozen=True)
class LocalOcrHealthResult:
    provider: str = "tesseract"
    platform: str = ""
    discovery_source: str = "not_found"
    executable_available: bool = False
    engine_version: str = ""
    english_available: bool = False
    simplified_chinese_available: bool = False
    orientation_available: bool = False
    offline_runtime: bool = True
    ready: bool = False
    safe_error_code: str | None = None

    def to_safe_dict(self) -> dict:
        return {
            "provider": self.provider,
            "platform": self.platform,
            "discovery_source": self.discovery_source,
            "executable_available": self.executable_available,
            "engine_version": self.engine_version,
            "english_available": self.english_available,
            "simplified_chinese_available": self.simplified_chinese_available,
            "orientation_available": self.orientation_available,
            "offline_runtime": self.offline_runtime,
            "ready": self.ready,
            "safe_error_code": self.safe_error_code,
        }


def discover_tesseract_executable(
    *,
    env=None,
    which_func=None,
    is_file=None,
    is_executable=None,
) -> TesseractExecutableDiscovery:
    env = os.environ if env is None else env
    which_func = shutil.which if which_func is None else which_func
    is_file = _default_is_file if is_file is None else is_file
    is_executable = _default_is_executable if is_executable is None else is_executable

    configured = str(env.get(TESSERACT_CMD_ENV) or "").strip()
    if configured:
        if "\x00" in configured or "\n" in configured or "\r" in configured:
            return TesseractExecutableDiscovery(
                discovery_source="not_found",
                safe_error_code="TESSERACT_EXECUTABLE_NOT_RUNNABLE",
            )
        if not is_file(configured) or not is_executable(configured):
            return TesseractExecutableDiscovery(
                discovery_source="not_found",
                safe_error_code="TESSERACT_EXECUTABLE_NOT_RUNNABLE",
            )
        return TesseractExecutableDiscovery(
            executable_path=configured,
            discovery_source="environment",
            safe_error_code=None,
        )

    candidate = str(which_func("tesseract") or "").strip()
    if not candidate:
        return TesseractExecutableDiscovery()
    if not is_file(candidate) or not is_executable(candidate):
        return TesseractExecutableDiscovery(
            discovery_source="not_found",
            safe_error_code="TESSERACT_EXECUTABLE_NOT_RUNNABLE",
        )
    return TesseractExecutableDiscovery(
        executable_path=candidate,
        discovery_source="path",
        safe_error_code=None,
    )


def resolve_tesseract_language(language: str | None) -> str | None:
    key = str(language or "").strip().lower()
    return TESSERACT_LANGUAGE_ALIASES.get(key)


def _run_tesseract(executable: str, args: list[str], *, timeout: int, max_output_bytes: int) -> dict:
    try:
        completed = subprocess.run(
            [executable, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "TESSERACT_TIMEOUT", "stdout": "", "stderr": "Tesseract timed out."}
    except Exception as exc:
        return {"ok": False, "code": "TESSERACT_EXECUTION_FAILED", "stdout": "", "stderr": _safe_error_text(exc)}

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if len(stdout.encode("utf-8", errors="ignore")) > max_output_bytes:
        return {"ok": False, "code": "TESSERACT_OUTPUT_TOO_LARGE", "stdout": "", "stderr": "Tesseract output exceeded the safe size limit."}
    if len(stderr.encode("utf-8", errors="ignore")) > max_output_bytes:
        stderr = stderr[:TESSERACT_ERROR_LIMIT_CHARS]
    if completed.returncode != 0:
        return {"ok": False, "code": "TESSERACT_EXECUTION_FAILED", "stdout": stdout, "stderr": _safe_error_text(stderr)}
    return {"ok": True, "code": None, "stdout": stdout, "stderr": stderr}


def _parse_engine_version(stdout: str) -> str:
    first = next((line.strip() for line in str(stdout or "").splitlines() if line.strip()), "")
    match = re.search(r"tesseract\s+([0-9][^\s]*)", first, re.IGNORECASE)
    return match.group(1) if match else first[:80]


def _parse_listed_languages(stdout: str) -> set[str]:
    languages = set()
    for line in str(stdout or "").splitlines():
        value = line.strip()
        if not value or value.lower().startswith("list of available languages"):
            continue
        languages.add(value)
    return languages


def check_tesseract_health() -> LocalOcrHealthResult:
    discovery = discover_tesseract_executable()
    if not discovery.executable_path:
        return LocalOcrHealthResult(
            platform=_platform_id(),
            discovery_source=discovery.discovery_source,
            executable_available=False,
            ready=False,
            safe_error_code=discovery.safe_error_code or "TESSERACT_EXECUTABLE_NOT_FOUND",
        )
    version = _run_tesseract(
        discovery.executable_path,
        ["--version"],
        timeout=10,
        max_output_bytes=128 * 1024,
    )
    if not version["ok"]:
        return LocalOcrHealthResult(
            platform=_platform_id(),
            discovery_source=discovery.discovery_source,
            executable_available=True,
            ready=False,
            safe_error_code=version["code"] or "TESSERACT_VERSION_UNAVAILABLE",
        )
    listed = _run_tesseract(
        discovery.executable_path,
        ["--list-langs"],
        timeout=10,
        max_output_bytes=256 * 1024,
    )
    if not listed["ok"]:
        return LocalOcrHealthResult(
            platform=_platform_id(),
            discovery_source=discovery.discovery_source,
            executable_available=True,
            engine_version=_parse_engine_version(version["stdout"]),
            ready=False,
            safe_error_code=listed["code"] or "TESSERACT_LANGUAGE_LIST_UNAVAILABLE",
        )
    languages = _parse_listed_languages(listed["stdout"])
    english_available = "eng" in languages
    simplified_chinese_available = "chi_sim" in languages
    orientation_available = "osd" in languages
    missing_code = None
    if not english_available:
        missing_code = "TESSERACT_ENG_UNAVAILABLE"
    elif not simplified_chinese_available:
        missing_code = "TESSERACT_CHI_SIM_UNAVAILABLE"
    elif not orientation_available:
        missing_code = "TESSERACT_OSD_UNAVAILABLE"
    return LocalOcrHealthResult(
        platform=_platform_id(),
        discovery_source=discovery.discovery_source,
        executable_available=True,
        engine_version=_parse_engine_version(version["stdout"]),
        english_available=english_available,
        simplified_chinese_available=simplified_chinese_available,
        orientation_available=orientation_available,
        ready=missing_code is None,
        safe_error_code=missing_code,
    )


def _to_int(value):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_confidence(value):
    try:
        confidence = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if confidence < 0:
        return None
    return max(0.0, min(confidence, 100.0))


def parse_tesseract_tsv(tsv_text: str, *, page_number: int | None = None) -> list[dict]:
    required = {
        "level",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
        "word_num",
        "left",
        "top",
        "width",
        "height",
        "conf",
        "text",
    }
    rows = csv.DictReader(StringIO(str(tsv_text or "")), delimiter="\t")
    if not rows.fieldnames or not required.issubset(set(rows.fieldnames)):
        return []
    blocks = []
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        left = _to_int(row.get("left"))
        top = _to_int(row.get("top"))
        width = _to_int(row.get("width"))
        height = _to_int(row.get("height"))
        if None in {left, top, width, height}:
            continue
        tesseract_page = _to_int(row.get("page_num")) or 1
        blocks.append({
            "text": text,
            "page_number": page_number or tesseract_page,
            "tesseract_page": tesseract_page,
            "level": _to_int(row.get("level")) or 0,
            "block_number": _to_int(row.get("block_num")) or 0,
            "paragraph_number": _to_int(row.get("par_num")) or 0,
            "line_number": _to_int(row.get("line_num")) or 0,
            "word_number": _to_int(row.get("word_num")) or 0,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "confidence": _to_confidence(row.get("conf")),
        })
    return blocks


def _contains_cjk(text: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in str(text or ""))


def _join_ocr_tokens(tokens: list[str]) -> str:
    output = ""
    for token in tokens:
        token = str(token or "").strip()
        if not token:
            continue
        if not output:
            output = token
        elif _contains_cjk(output[-1]) or _contains_cjk(token[0]):
            output += token
        else:
            output += f" {token}"
    return output


def join_tesseract_blocks_text(blocks: list[dict]) -> str:
    grouped: dict[tuple[int, int, int, int], list[str]] = {}
    order: list[tuple[int, int, int, int]] = []
    for block in sorted(
        blocks or [],
        key=lambda item: (
            int(item.get("page_number") or 0),
            int(item.get("block_number") or 0),
            int(item.get("paragraph_number") or 0),
            int(item.get("line_number") or 0),
            int(item.get("word_number") or 0),
        ),
    ):
        key = (
            int(block.get("page_number") or 0),
            int(block.get("block_number") or 0),
            int(block.get("paragraph_number") or 0),
            int(block.get("line_number") or 0),
        )
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(str(block.get("text") or ""))
    return "\n".join(_join_ocr_tokens(grouped[key]) for key in order if grouped.get(key)).strip()


@dataclass
class OCRTextResult:
    status: str
    text: str = ""
    confidence: float = 0
    provider: str = ""
    language: str = ""
    error: str = ""
    blocks: list = field(default_factory=list)
    quality_flags: list = field(default_factory=list)
    engine_version: str = ""

    @property
    def ok(self):
        return self.status == "ok" and bool(self.text.strip())


# Backward compatible name used by older imports/tests.
OCRResult = OCRTextResult


class OCRProvider:
    provider_name = "none"

    def is_available(self):
        return False

    def recognize_image(self, image_path, language=""):
        return OCRTextResult(
            status="ocr_unavailable",
            provider=self.provider_name,
            language=_normalize_language(language),
            error="No OCR provider is configured."
        )


class NoneOCRProvider(OCRProvider):
    provider_name = "none"


class MockOCRProvider(OCRProvider):
    provider_name = "mock"

    def recognize_image(self, image_path, language=""):
        return OCRTextResult(
            status="ocr_unavailable",
            provider=self.provider_name,
            language=_normalize_language(language),
            error="Real OCR engine is not configured."
        )


class TesseractOCRProvider(OCRProvider):
    provider_name = "tesseract"

    def __init__(self):
        discovery = discover_tesseract_executable()
        self.binary = discovery.executable_path
        self.discovery_source = discovery.discovery_source
        self.discovery_error = discovery.safe_error_code
        self.ocr_langs = resolve_tesseract_language(os.environ.get("OCR_LANGS", TESSERACT_DEFAULT_LANGUAGE)) or TESSERACT_DEFAULT_LANGUAGE
        self.min_confidence = _env_int("OCR_MIN_CONFIDENCE", 60)
        self.timeout_seconds = _env_int("OCR_TIMEOUT_SECONDS", 60)
        self.max_output_bytes = _env_int("OCR_TESSERACT_MAX_OUTPUT_BYTES", TESSERACT_OUTPUT_LIMIT_BYTES)
        self._engine_version = ""

    def is_available(self):
        return bool(self.binary)

    def supports_language(self, language=""):
        language_code = resolve_tesseract_language(language or self.ocr_langs)
        if not language_code:
            return False
        health = check_tesseract_health()
        if not health.ready:
            return False
        required = set(language_code.split("+"))
        return (
            ("eng" not in required or health.english_available)
            and ("chi_sim" not in required or health.simplified_chinese_available)
            and ("osd" not in required or health.orientation_available)
        )

    def recognize_image(self, image_path, language=""):
        normalized_language = _normalize_language(language)
        language_code = resolve_tesseract_language(language or self.ocr_langs)
        if not language_code:
            return OCRTextResult(
                status="ocr_failed",
                provider=self.provider_name,
                language=normalized_language,
                error="Requested OCR language is not allowlisted.",
                quality_flags=["ocr_language_not_allowlisted"],
            )
        if not self.is_available():
            return OCRTextResult(
                status="ocr_unavailable",
                provider=self.provider_name,
                language=normalized_language,
                error="Tesseract executable is unavailable.",
                quality_flags=[self.discovery_error or "TESSERACT_EXECUTABLE_NOT_FOUND"],
            )

        if not os.path.exists(image_path):
            return OCRTextResult(
                status="ocr_failed",
                provider=self.provider_name,
                language=normalized_language,
                error="OCR input image was not found."
            )

        completed = _run_tesseract(
            self.binary,
            [image_path, "stdout", "-l", language_code, "--psm", "6", "tsv"],
            timeout=self.timeout_seconds,
            max_output_bytes=self.max_output_bytes,
        )
        if not completed["ok"]:
            flags = []
            if completed["code"] == "TESSERACT_TIMEOUT":
                flags.append("ocr_timeout")
            return OCRTextResult(
                status="ocr_failed",
                provider=self.provider_name,
                language=language_code,
                error=_safe_error_text(completed.get("stderr") or completed.get("code")),
                quality_flags=flags,
            )

        blocks = parse_tesseract_tsv(completed["stdout"])
        joined = join_tesseract_blocks_text(blocks)
        if not joined:
            return OCRTextResult(
                status="empty_result",
                provider=self.provider_name,
                language=language_code,
                error="OCR completed but no text was detected.",
                blocks=blocks
            )

        confidences = [float(block["confidence"]) for block in blocks if block.get("confidence") is not None]
        confidence = round(sum(confidences) / len(confidences), 2) if confidences else 50.0
        status = "ok"
        quality_flags = []
        if confidence < self.min_confidence:
            status = "low_confidence"
            quality_flags.append("ocr_low_confidence")
        if not self._engine_version:
            health = check_tesseract_health()
            self._engine_version = health.engine_version

        return OCRTextResult(
            status=status,
            text=joined,
            confidence=max(0, min(confidence, 100)),
            provider=self.provider_name,
            language=language_code,
            blocks=blocks,
            quality_flags=quality_flags,
            engine_version=self._engine_version,
        )


class PaddleOCRProvider(OCRProvider):
    provider_name = "paddle"

    def __init__(self, language=""):
        self._ocr = None
        self._error = ""
        self.language = _normalize_language(language)
        self.min_confidence = _env_int("OCR_MIN_CONFIDENCE", 60)
        try:
            from paddleocr import PaddleOCR
            paddle_lang = "ch" if self.language in {"zh", "bilingual", "mixed"} else "en"
            self._ocr = PaddleOCR(use_angle_cls=True, lang=paddle_lang, show_log=False)
        except Exception as exc:
            self._error = str(exc)

    def is_available(self):
        return self._ocr is not None

    def recognize_image(self, image_path, language=""):
        normalized_language = _normalize_language(language or self.language)
        if not self.is_available():
            return OCRTextResult(
                status="ocr_unavailable",
                provider=self.provider_name,
                language=normalized_language,
                error=f"PaddleOCR is not available: {self._error}"
            )
        try:
            result = self._ocr.ocr(image_path, cls=True)
        except Exception as exc:
            return OCRTextResult(
                status="ocr_failed",
                provider=self.provider_name,
                language=normalized_language,
                error=f"PaddleOCR execution failed: {exc}"
            )

        texts = []
        confidences = []
        blocks = []
        for page in result or []:
            for item in page or []:
                if len(item) >= 2 and isinstance(item[1], (list, tuple)):
                    text = str(item[1][0]).strip()
                    if text:
                        texts.append(text)
                    try:
                        conf = float(item[1][1]) * 100
                        confidences.append(conf)
                    except Exception:
                        conf = 0
                    blocks.append({
                        "text": text,
                        "confidence": max(0, min(conf, 100)),
                        "bbox": item[0] if item else None
                    })

        joined = " ".join(texts).strip()
        if not joined:
            return OCRTextResult(
                status="empty_result",
                provider=self.provider_name,
                language=normalized_language,
                error="OCR completed but no text was detected.",
                blocks=blocks
            )

        confidence = round(sum(confidences) / len(confidences), 2) if confidences else 50
        status = "ok"
        quality_flags = []
        if confidence < self.min_confidence:
            status = "low_confidence"
            quality_flags.append("ocr_low_confidence")

        return OCRTextResult(
            status=status,
            text=joined,
            confidence=max(0, min(confidence, 100)),
            provider=self.provider_name,
            language=normalized_language,
            blocks=blocks,
            quality_flags=quality_flags
        )


def get_ocr_provider(provider_name, language=""):
    provider_name = (provider_name or "none").strip().lower()
    if provider_name == "tesseract":
        return TesseractOCRProvider()
    if provider_name == "paddle":
        return PaddleOCRProvider(language=language)
    if provider_name == "mock":
        return MockOCRProvider()
    if provider_name == "auto":
        tesseract = TesseractOCRProvider()
        if tesseract.is_available() and tesseract.supports_language(language or tesseract.ocr_langs):
            return tesseract
        return NoneOCRProvider()
    return NoneOCRProvider()
