"""Bounded, offline adapter for the optional Docling PDF parser.

Docling is intentionally isolated from the application runtime.  The adapter
executes a separately provisioned Python interpreter, requires a local model
directory, strips credential-bearing environment variables, blocks remote
model resolution, and accepts only a small validated layout JSON contract.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DOCLING_PROVIDER_ID = "docling"
DOCLING_POLICY_ID = "conditional-docling-parser@1.0.0"
DOCLING_WORKER_CONTRACT = "docling-layout-worker@1.0.0"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_BLOCKS = 10_000
DEFAULT_MAX_BLOCK_TEXT_CHARS = 20_000


def _env_int(name: str, default: int, *, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(lower, min(value, upper))


@dataclass(frozen=True)
class DoclingRoutingDecision:
    document_class: str
    selected_provider: str
    docling_allowed: bool
    reason_codes: tuple[str, ...]
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DoclingAdapterBlock:
    page_number: int
    text: str
    bbox: tuple[float, float, float, float]
    layout_type: str
    reading_order: int
    page_width: float
    page_height: float
    confidence: float = 1.0


@dataclass(frozen=True)
class DoclingAdapterResult:
    status: str
    parser_version: str = ""
    page_count: int = 0
    blocks: tuple[DoclingAdapterBlock, ...] = ()
    warnings: tuple[str, ...] = ()
    reason_code: str = ""


def _has_table_signal(page: Any) -> bool:
    """Return a conservative vector-grid signal without invoking a parser."""
    try:
        drawings = page.get_drawings()
    except Exception:
        return False
    horizontal = 0
    vertical = 0
    rectangles = 0
    for drawing in drawings or []:
        for item in drawing.get("items", []) or []:
            kind = item[0] if item else ""
            if kind == "re":
                rectangles += 1
            elif kind == "l" and len(item) >= 3:
                first, second = item[1], item[2]
                dx = abs(float(second.x) - float(first.x))
                dy = abs(float(second.y) - float(first.y))
                if dx >= 20 and dy <= 1:
                    horizontal += 1
                elif dy >= 20 and dx <= 1:
                    vertical += 1
    return rectangles >= 2 or (horizontal >= 2 and vertical >= 2)


def _has_multi_column_signal(page: Any) -> bool:
    width = float(page.rect.width or 0)
    if width <= 0:
        return False
    try:
        blocks = page.get_text("blocks", sort=False) or []
    except Exception:
        return False
    left = []
    right = []
    for raw in blocks:
        if len(raw) < 5 or not str(raw[4] or "").strip():
            continue
        item = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        if item[2] <= width * 0.58:
            left.append(item)
        elif item[0] >= width * 0.42:
            right.append(item)
    if not left or not right:
        return False
    return any(
        min(left_box[3], right_box[3]) - max(left_box[1], right_box[1]) > 2
        for left_box in left
        for right_box in right
    )


def classify_pdf_for_docling(path: str | os.PathLike[str]) -> DoclingRoutingDecision:
    """Classify a PDF with cheap local signals before heavy parsing.

    The Task 14B benchmark authorizes Docling only for scanned PDFs and
    validated simple vector-table PDFs.  Multi-column documents remain on the
    current parser because their reading-order gate failed in that benchmark.
    """
    try:
        import fitz
    except ImportError:
        return DoclingRoutingDecision(
            document_class="classification_unavailable",
            selected_provider="rule_based",
            docling_allowed=False,
            reason_codes=("DOCLING_ROUTE_CLASSIFIER_UNAVAILABLE",),
        )

    page_count = 0
    text_page_count = 0
    nonempty_visual_page_count = 0
    table_signal = False
    multi_column_signal = False
    try:
        with fitz.open(str(path)) as document:
            page_count = len(document)
            for page in document:
                text = str(page.get_text("text") or "").strip()
                if text:
                    text_page_count += 1
                try:
                    visuals = bool(page.get_images(full=True) or page.get_drawings())
                except Exception:
                    visuals = False
                if visuals:
                    nonempty_visual_page_count += 1
                table_signal = table_signal or _has_table_signal(page)
                multi_column_signal = multi_column_signal or _has_multi_column_signal(page)
    except Exception:
        return DoclingRoutingDecision(
            document_class="classification_failed",
            selected_provider="rule_based",
            docling_allowed=False,
            reason_codes=("DOCLING_ROUTE_CLASSIFICATION_FAILED",),
        )

    diagnostics = {
        "page_count": page_count,
        "text_page_count": text_page_count,
        "visual_page_count": nonempty_visual_page_count,
        "table_signal": table_signal,
        "multi_column_signal": multi_column_signal,
    }
    if page_count <= 0:
        return DoclingRoutingDecision(
            "empty_pdf", "rule_based", False,
            ("DOCLING_ROUTE_EMPTY_PDF_EXCLUDED",), diagnostics,
        )
    if multi_column_signal:
        return DoclingRoutingDecision(
            "multi_column_pdf", "rule_based", False,
            ("DOCLING_ROUTE_MULTI_COLUMN_EXCLUDED",), diagnostics,
        )
    if text_page_count == 0 and nonempty_visual_page_count:
        return DoclingRoutingDecision(
            "scanned_pdf", DOCLING_PROVIDER_ID, True,
            ("DOCLING_ROUTE_SCANNED_PDF",), diagnostics,
        )
    if table_signal and text_page_count:
        return DoclingRoutingDecision(
            "simple_table_pdf", DOCLING_PROVIDER_ID, True,
            ("DOCLING_ROUTE_SIMPLE_TABLE_PDF",), diagnostics,
        )
    return DoclingRoutingDecision(
        "simple_digital_pdf", "rule_based", False,
        ("DOCLING_ROUTE_SIMPLE_NATIVE",), diagnostics,
    )


def _worker_environment(model_root: str) -> dict[str, str]:
    allowed = {}
    for name in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "PYTHONUTF8"):
        value = os.environ.get(name)
        if value:
            allowed[name] = value
    allowed.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DOCLING_ARTIFACTS_PATH": model_root,
            "PYTHONNOUSERSITE": "1",
        }
    )
    return allowed


class DoclingParserAdapter:
    def __init__(
        self,
        *,
        python_executable: str | None = None,
        model_root: str | None = None,
        worker_path: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        self.python_executable = str(
            python_executable or os.environ.get("DOCLING_PARSER_PYTHON", "")
        ).strip()
        self.model_root = str(
            model_root or os.environ.get("DOCLING_MODEL_ROOT", "")
        ).strip()
        self.worker_path = str(
            worker_path or root / "scripts" / "docling_parser_worker.py"
        )
        self.timeout_seconds = timeout_seconds or _env_int(
            "DOCLING_PARSER_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
            lower=1,
            upper=600,
        )
        self.max_file_bytes = _env_int(
            "DOCLING_PARSER_MAX_FILE_BYTES",
            DEFAULT_MAX_FILE_BYTES,
            lower=1024,
            upper=250 * 1024 * 1024,
        )
        self.max_pages = _env_int(
            "DOCLING_PARSER_MAX_PAGES", DEFAULT_MAX_PAGES, lower=1, upper=200
        )
        self.max_output_bytes = _env_int(
            "DOCLING_PARSER_MAX_OUTPUT_BYTES",
            DEFAULT_MAX_OUTPUT_BYTES,
            lower=1024,
            upper=64 * 1024 * 1024,
        )

    def _preflight_reason(self, path: Path) -> str:
        runtime = Path(self.python_executable) if self.python_executable else None
        if runtime is None or not runtime.is_absolute():
            return "DOCLING_RUNTIME_NOT_ABSOLUTE"
        if not runtime.is_file() or not os.access(runtime, os.X_OK):
            return "DOCLING_RUNTIME_UNAVAILABLE"
        model_root = Path(self.model_root) if self.model_root else None
        if model_root is None or not model_root.is_absolute():
            return "DOCLING_MODEL_ROOT_NOT_ABSOLUTE"
        if not model_root.is_dir():
            return "DOCLING_MODEL_ROOT_UNAVAILABLE"
        worker = Path(self.worker_path)
        if not worker.is_absolute() or not worker.is_file():
            return "DOCLING_WORKER_UNAVAILABLE"
        if not path.is_file():
            return "DOCLING_INPUT_UNAVAILABLE"
        try:
            if path.stat().st_size > self.max_file_bytes:
                return "DOCLING_INPUT_SIZE_EXCEEDED"
        except OSError:
            return "DOCLING_INPUT_UNAVAILABLE"
        try:
            import fitz

            with fitz.open(str(path)) as document:
                page_count = len(document)
        except Exception:
            return "DOCLING_INPUT_INVALID"
        if page_count <= 0 or page_count > self.max_pages:
            return "DOCLING_PAGE_LIMIT_EXCEEDED"
        return ""

    def analyze_pdf(self, path: str | os.PathLike[str]) -> DoclingAdapterResult:
        input_path = Path(path).resolve()
        reason = self._preflight_reason(input_path)
        if reason:
            return DoclingAdapterResult(status="layout_unavailable", reason_code=reason)
        with tempfile.TemporaryDirectory(prefix="lexibridge-docling-") as directory:
            output_path = Path(directory) / "layout.json"
            command = [
                self.python_executable,
                self.worker_path,
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--model-root",
                self.model_root,
                "--max-pages",
                str(self.max_pages),
                "--block-network",
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.timeout_seconds,
                    env=_worker_environment(self.model_root),
                )
            except subprocess.TimeoutExpired:
                return DoclingAdapterResult(status="failed", reason_code="DOCLING_TIMEOUT")
            except OSError:
                return DoclingAdapterResult(status="failed", reason_code="DOCLING_EXECUTION_FAILED")
            if completed.returncode != 0 or not output_path.is_file():
                return DoclingAdapterResult(status="failed", reason_code="DOCLING_EXECUTION_FAILED")
            try:
                if output_path.stat().st_size > self.max_output_bytes:
                    return DoclingAdapterResult(status="failed", reason_code="DOCLING_OUTPUT_SIZE_EXCEEDED")
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return DoclingAdapterResult(status="failed", reason_code="DOCLING_OUTPUT_INVALID")
        return self._validate_payload(payload)

    def _validate_payload(self, payload: Any) -> DoclingAdapterResult:
        if not isinstance(payload, dict) or payload.get("contract_version") != DOCLING_WORKER_CONTRACT:
            return DoclingAdapterResult(status="failed", reason_code="DOCLING_OUTPUT_CONTRACT_INVALID")
        if int(payload.get("external_request_count") or 0) != 0:
            return DoclingAdapterResult(status="failed", reason_code="DOCLING_EXTERNAL_REQUEST_DETECTED")
        if payload.get("status") != "ok":
            return DoclingAdapterResult(
                status="failed",
                reason_code=str(payload.get("error_code") or "DOCLING_PARSE_FAILED"),
            )
        try:
            page_count = int(payload.get("page_count") or 0)
        except (TypeError, ValueError):
            page_count = 0
        if page_count <= 0 or page_count > self.max_pages:
            return DoclingAdapterResult(status="failed", reason_code="DOCLING_PAGE_COUNT_INVALID")
        raw_blocks = payload.get("blocks")
        if not isinstance(raw_blocks, list) or len(raw_blocks) > DEFAULT_MAX_BLOCKS:
            return DoclingAdapterResult(status="failed", reason_code="DOCLING_BLOCKS_INVALID")
        blocks = []
        for index, raw in enumerate(raw_blocks, start=1):
            block = self._validated_block(raw, page_count, index)
            if block is None:
                return DoclingAdapterResult(status="failed", reason_code="DOCLING_PROVENANCE_INVALID")
            blocks.append(block)
        if not blocks:
            return DoclingAdapterResult(status="failed", reason_code="DOCLING_EMPTY_OUTPUT")
        return DoclingAdapterResult(
            status="ok",
            parser_version=str(payload.get("parser_version") or ""),
            page_count=page_count,
            blocks=tuple(blocks),
            warnings=tuple(str(item)[:120] for item in payload.get("warnings", []) if item),
        )

    @staticmethod
    def _validated_block(raw: Any, page_count: int, index: int) -> DoclingAdapterBlock | None:
        if not isinstance(raw, dict):
            return None
        try:
            page_number = int(raw["page_number"])
            text = str(raw.get("text") or "").strip()
            bbox = raw["bbox"]
            x0, y0, x1, y1 = (
                float(bbox["x0"]),
                float(bbox["y0"]),
                float(bbox["x1"]),
                float(bbox["y1"]),
            )
            page_width = float(raw["page_width"])
            page_height = float(raw["page_height"])
            reading_order = int(raw.get("reading_order") or index)
            confidence = float(raw.get("confidence", 1.0) or 1.0)
        except (KeyError, TypeError, ValueError):
            return None
        layout_type = str(raw.get("layout_type") or "text").strip().casefold()
        allowed_types = {
            "text", "title", "caption", "header_footer", "page_number",
            "table", "figure", "formula", "list",
        }
        if (
            page_number < 1
            or page_number > page_count
            or not text
            or len(text) > DEFAULT_MAX_BLOCK_TEXT_CHARS
            or layout_type not in allowed_types
            or page_width <= 0
            or page_height <= 0
            or x0 < 0
            or y0 < 0
            or x1 <= x0
            or y1 <= y0
            or x1 > page_width + 1
            or y1 > page_height + 1
        ):
            return None
        return DoclingAdapterBlock(
            page_number=page_number,
            text=text,
            bbox=(x0, y0, x1, y1),
            layout_type=layout_type,
            reading_order=reading_order,
            page_width=page_width,
            page_height=page_height,
            confidence=max(0.0, min(confidence, 1.0)),
        )
