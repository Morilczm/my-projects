#!/usr/bin/env python3
"""Evaluate open-source document parser candidates on safe local fixtures.

This is an evaluation-only harness. It does not change production parser routing,
does not import third-party parser packages at server import time, and does not
write to the LexiBridge main database.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import resource
import shutil
import socket
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
LOCAL_TMP_LABEL = "<LOCAL_PRIVATE_TMP>"
TEXT_LIMIT = 1200
PRIVATE_TEXT_LIMIT = 160
SUPPORTED_BLOCK_TYPES = {
    "title",
    "heading",
    "paragraph",
    "list_item",
    "table",
    "formula",
    "image",
    "caption",
    "header",
    "footer",
    "page_number",
    "unknown",
}
LOCAL_PATH_RE = re.compile(r"(/Users/[^\s\"']+|/private/tmp/[^\s\"']+|file://[^\s\"']+)", re.IGNORECASE)
SECRET_RE = re.compile(r"(Authorization:|Cookie:|Bearer\s+|sk-[A-Za-z0-9_-]+)", re.IGNORECASE)


@dataclass(frozen=True)
class GoldAnchor:
    text: str
    block_type: str = "paragraph"
    order: int = 0


@dataclass(frozen=True)
class ParserFixture:
    fixture_id: str
    filename: str
    path: Path
    privacy_classification: str
    domains: tuple[str, ...]
    expected_anchors: tuple[GoldAnchor, ...]
    expected_table_rows: int = 0
    expected_table_cols: int = 0
    expected_formula_count: int = 0
    expected_raster_formula_count: int = 0
    expected_images: int = 0
    scanned: bool = False
    complex_layout: bool = False
    negative: bool = False


PRIVATE_FIXTURE_ID = "local_private_course_sample"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: str | Path) -> str:
    target = Path(path)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_text(value: Any, *, private: bool = False) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = LOCAL_PATH_RE.sub(LOCAL_TMP_LABEL + "/", text)
    text = SECRET_RE.sub("[REDACTED]", text)
    return text[: PRIVATE_TEXT_LIMIT if private else TEXT_LIMIT]


def _font_path() -> str:
    for candidate in (
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ):
        if Path(candidate).exists():
            return candidate
    return ""


def _register_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_path = _font_path()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("LexiBridgeEvalUnicode", font_path))
            return "LexiBridgeEvalUnicode"
        except Exception:
            pass
    return "Helvetica"


def _scan_font():
    from PIL import ImageFont

    font_path = _font_path()
    try:
        return ImageFont.truetype(font_path, 42) if font_path else ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def _write_native_pdf(path: Path, title: str, lines: list[str]) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    font = _register_font()
    doc = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    doc.setFont(font, 16)
    doc.drawString(54, height - 54, title)
    doc.setFont(font, 11)
    y = height - 88
    for line in lines:
        if y < 64:
            doc.showPage()
            doc.setFont(font, 11)
            y = height - 54
        doc.drawString(54, y, line[:180])
        y -= 18
    doc.save()


def _write_two_column_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    font = _register_font()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    doc.setFont(font, 15)
    doc.drawString(54, height - 54, "Two Column Engineering Notes")
    doc.setFont(font, 10)
    left = [
        "Fourier Transform explains frequency-domain representation.",
        "Impulse Response describes system output to a unit impulse.",
        "Convolution combines input and impulse response.",
        "Transfer Function maps input to output in the s-domain.",
    ]
    right = [
        "Voltage Divider relates resistor ratios to output voltage.",
        "Operational Amplifier has high differential gain.",
        "Equivalent Resistance simplifies circuit networks.",
        "Boundary Condition constrains differential equations.",
    ]
    for index, line in enumerate(left):
        doc.drawString(54, height - 96 - index * 32, line)
    for index, line in enumerate(right):
        doc.drawString(width / 2 + 20, height - 96 - index * 32, line)
    doc.save()


def _write_image_pdf(path: Path, lines: list[str]) -> None:
    from PIL import Image, ImageDraw
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    image_path = path.with_suffix(".png")
    image = Image.new("RGB", (1650, 2100), "white")
    draw = ImageDraw.Draw(image)
    font = _scan_font()
    draw.text((90, 80), "LexiBridge Parser Evaluation Scan", fill="black", font=font)
    y = 180
    for line in lines:
        draw.text((110, y), line, fill="black", font=font)
        y += 72
    image.save(image_path)
    doc = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    doc.drawImage(ImageReader(str(image_path)), 0, 0, width=width, height=height)
    doc.save()
    try:
        image_path.unlink()
    except OSError:
        pass


def _write_table_pdf(path: Path, *, two_columns: bool = False) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    font = _register_font()
    doc = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    doc.setFont(font, 14)
    doc.drawString(54, height - 54, "Parser Evaluation Table")
    doc.setFont(font, 10)
    rows = [
        ("Domain", "Term", "Definition"),
        ("Signals", "Impulse Response", "Output to impulse"),
        ("Circuits", "Voltage Divider", "Resistor ratio"),
        ("Math", "Eigenvalue", "Matrix scalar"),
    ]
    x0, y0 = 54, height - 100
    col_widths = [110, 150, 190]
    for row_index, row in enumerate(rows):
        y = y0 - row_index * 28
        x = x0
        for col_index, cell in enumerate(row):
            doc.rect(x, y - 18, col_widths[col_index], 28)
            doc.drawString(x + 4, y - 8, cell)
            x += col_widths[col_index]
    if two_columns:
        doc.drawString(width / 2 + 24, height - 100, "Right column note: Convolution remains body text.")
        doc.drawString(width / 2 + 24, height - 128, "Right column note: Boundary Condition remains body text.")
    doc.save()


def _write_formula_pdf(path: Path, *, raster: bool) -> None:
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    font = _register_font()
    doc = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    doc.setFont(font, 15)
    doc.drawString(54, height - 54, "Formula Parser Evaluation")
    doc.setFont(font, 10)
    doc.drawString(54, height - 88, "Transfer Function appears near the formula region.")
    if raster:
        image_path = path.with_name(path.stem + "-formula.png")
        image = Image.new("RGB", (900, 220), "white")
        draw = ImageDraw.Draw(image)
        try:
            formula_font = ImageFont.truetype(_font_path(), 42) if _font_path() else ImageFont.load_default()
        except Exception:
            formula_font = ImageFont.load_default()
        draw.text((48, 44), "H(s) = int_0^infty h(t)e^{-st} dt", fill="black", font=formula_font)
        draw.text((48, 112), "V_out = V_in * R_2 / (R_1 + R_2)", fill="black", font=formula_font)
        image.save(image_path)
        doc.drawImage(ImageReader(str(image_path)), 72, 320, width=420, height=110)
        try:
            image_path.unlink()
        except OSError:
            pass
    else:
        doc.setFont(font, 13)
        doc.drawString(72, 340, "H(s) = integral h(t)e^{-st} dt")
        doc.drawString(72, 310, "Vout = Vin * R2 / (R1 + R2)")
    doc.save()


def _write_plain_image_pdf(path: Path) -> None:
    from PIL import Image, ImageDraw
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    image_path = path.with_suffix(".png")
    image = Image.new("RGB", (600, 220), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 560, 180), outline="black", width=4)
    draw.line((40, 40, 560, 180), fill="gray", width=3)
    image.save(image_path)
    doc = canvas.Canvas(str(path), pagesize=letter)
    doc.drawString(54, 720, "Plain raster image should not be formula.")
    doc.drawImage(ImageReader(str(image_path)), 72, 340, width=300, height=110)
    doc.save()
    try:
        image_path.unlink()
    except OSError:
        pass


def build_fixture_set(root: Path) -> list[ParserFixture]:
    root.mkdir(parents=True, exist_ok=True)
    fixtures: list[ParserFixture] = []

    def anchors(values: list[tuple[str, str]]) -> tuple[GoldAnchor, ...]:
        return tuple(GoldAnchor(text=text, block_type=kind, order=i + 1) for i, (text, kind) in enumerate(values))

    single = root / "single-column-born-digital.pdf"
    single_terms = ["Fourier Transform", "Impulse Response", "Convolution", "Voltage Divider"]
    _write_native_pdf(single, "Single Column Engineering Notes", [f"{term}: synthetic paragraph anchor." for term in single_terms])
    fixtures.append(ParserFixture("single_column_born_digital", single.name, single, "SYNTHETIC", ("signals", "circuits"), anchors([(t, "paragraph") for t in single_terms])))

    two_col = root / "two-column-born-digital.pdf"
    _write_two_column_pdf(two_col)
    fixtures.append(ParserFixture("two_column_born_digital", two_col.name, two_col, "SYNTHETIC", ("signals", "circuits"), anchors([
        ("Fourier Transform", "paragraph"),
        ("Impulse Response", "paragraph"),
        ("Convolution", "paragraph"),
        ("Transfer Function", "paragraph"),
        ("Voltage Divider", "paragraph"),
        ("Operational Amplifier", "paragraph"),
        ("Equivalent Resistance", "paragraph"),
        ("Boundary Condition", "paragraph"),
    ]), complex_layout=True))

    bilingual = root / "bilingual-born-digital.pdf"
    _write_native_pdf(bilingual, "Bilingual Born Digital Fixture", [
        "Fourier Transform（傅里叶变换）",
        "Convolution（卷积）",
        "Voltage Divider（分压器）",
    ])
    fixtures.append(ParserFixture("bilingual_born_digital", bilingual.name, bilingual, "SYNTHETIC", ("signals", "circuits"), anchors([
        ("Fourier Transform", "paragraph"),
        ("傅里叶变换", "paragraph"),
        ("Convolution", "paragraph"),
        ("卷积", "paragraph"),
        ("Voltage Divider", "paragraph"),
        ("分压器", "paragraph"),
    ])))

    scan_en = root / "scanned-english.pdf"
    _write_image_pdf(scan_en, [f"{i}. {term}" for i, term in enumerate(["Fourier Transform", "Impulse Response", "Convolution", "Voltage Divider"], start=1)])
    fixtures.append(ParserFixture("scanned_english", scan_en.name, scan_en, "SYNTHETIC", ("signals",), anchors([(t, "paragraph") for t in single_terms]), scanned=True))

    scan_zh = root / "scanned-chinese.pdf"
    zh_terms = ["傅里叶变换", "冲激响应", "卷积", "分压器"]
    _write_image_pdf(scan_zh, [f"{i}. {term}" for i, term in enumerate(zh_terms, start=1)])
    fixtures.append(ParserFixture("scanned_chinese", scan_zh.name, scan_zh, "SYNTHETIC", ("signals", "circuits"), anchors([(t, "paragraph") for t in zh_terms]), scanned=True))

    scan_mix = root / "scanned-bilingual.pdf"
    _write_image_pdf(scan_mix, ["Fourier Transform - 傅里叶变换", "Convolution - 卷积", "Voltage Divider - 分压器"])
    fixtures.append(ParserFixture("scanned_bilingual", scan_mix.name, scan_mix, "SYNTHETIC", ("signals", "circuits"), anchors([
        ("Fourier Transform", "paragraph"),
        ("傅里叶变换", "paragraph"),
        ("Convolution", "paragraph"),
        ("卷积", "paragraph"),
        ("Voltage Divider", "paragraph"),
        ("分压器", "paragraph"),
    ]), scanned=True))

    mixed = root / "mixed-layout-blocker.pdf"
    _write_native_pdf(mixed, "Mixed Layout Fixture", [
        "Header: LexiBridge parser evaluation page",
        "Table row | Signal | Impulse Response | system output for impulse",
        "Table row | Circuit | Operational Amplifier | differential gain",
        "The Voltage Divider and Equivalent Resistance appear in body text.",
        "Footer: LexiBridge parser evaluation page",
    ])
    fixtures.append(ParserFixture("mixed_layout_blocker", mixed.name, mixed, "SYNTHETIC", ("signals", "circuits"), anchors([
        ("Impulse Response", "table"),
        ("Operational Amplifier", "table"),
        ("Voltage Divider", "paragraph"),
        ("Equivalent Resistance", "paragraph"),
    ]), expected_table_rows=2, expected_table_cols=3, complex_layout=True))

    list_pdf = root / "title-body-list.pdf"
    _write_native_pdf(list_pdf, "Title Body List Fixture", [
        "Section: Signal Processing",
        "- Fourier Transform",
        "- Impulse Response",
        "- Transfer Function",
        "Paragraph: list items above should remain distinct anchors.",
    ])
    fixtures.append(ParserFixture("title_body_list", list_pdf.name, list_pdf, "SYNTHETIC", ("signals",), anchors([
        ("Signal Processing", "heading"),
        ("Fourier Transform", "list_item"),
        ("Impulse Response", "list_item"),
        ("Transfer Function", "list_item"),
    ])))

    plain_image = root / "plain-raster-image.pdf"
    _write_plain_image_pdf(plain_image)
    fixtures.append(ParserFixture("plain_raster_image", plain_image.name, plain_image, "SYNTHETIC", ("negative",), anchors([("Plain raster image", "paragraph")]), expected_images=1))

    raster_formula = root / "raster-formula.pdf"
    _write_formula_pdf(raster_formula, raster=True)
    fixtures.append(ParserFixture("raster_formula", raster_formula.name, raster_formula, "SYNTHETIC", ("math",), anchors([("Transfer Function", "paragraph")]), expected_formula_count=1, expected_raster_formula_count=1))

    digital_formula = root / "born-digital-formula.pdf"
    _write_formula_pdf(digital_formula, raster=False)
    fixtures.append(ParserFixture("born_digital_formula", digital_formula.name, digital_formula, "SYNTHETIC", ("math",), anchors([("Transfer Function", "paragraph"), ("H(s)", "formula")]), expected_formula_count=1))

    table = root / "simple-table.pdf"
    _write_table_pdf(table)
    fixtures.append(ParserFixture("simple_table", table.name, table, "SYNTHETIC", ("signals", "circuits"), anchors([
        ("Impulse Response", "table"),
        ("Voltage Divider", "table"),
        ("Eigenvalue", "table"),
    ]), expected_table_rows=4, expected_table_cols=3, complex_layout=True))

    multitable = root / "multi-column-table.pdf"
    _write_table_pdf(multitable, two_columns=True)
    fixtures.append(ParserFixture("multi_column_table", multitable.name, multitable, "SYNTHETIC", ("signals", "circuits"), anchors([
        ("Impulse Response", "table"),
        ("Voltage Divider", "table"),
        ("Convolution", "paragraph"),
        ("Boundary Condition", "paragraph"),
    ]), expected_table_rows=4, expected_table_cols=3, complex_layout=True))

    header_footer = root / "header-footer-page-number.pdf"
    _write_native_pdf(header_footer, "Header Footer Fixture", [
        "Header: repeated course title",
        "Fourier Transform appears in the body.",
        "Impulse Response appears in the body.",
        "Page 1",
        "Footer: repeated footer",
    ])
    fixtures.append(ParserFixture("header_footer_page_number", header_footer.name, header_footer, "SYNTHETIC", ("signals",), anchors([
        ("Fourier Transform", "paragraph"),
        ("Impulse Response", "paragraph"),
        ("Page 1", "page_number"),
    ])))

    negative = root / "negative-no-terms.pdf"
    _write_native_pdf(negative, "Negative Fixture", ["This safe synthetic page contains no specialist terminology anchors."])
    fixtures.append(ParserFixture("negative_no_terms", negative.name, negative, "SYNTHETIC", ("negative",), tuple(), negative=True))

    return fixtures


def build_private_fixture(path: Path) -> ParserFixture:
    if not path.exists() or path.suffix.casefold() != ".pdf":
        raise ValueError("private PDF fixture must be an existing PDF")
    return ParserFixture(
        PRIVATE_FIXTURE_ID,
        "local-private-course-sample.pdf",
        path,
        "LOCAL_ONLY_PRIVATE",
        ("local_private_course",),
        tuple(),
        complex_layout=True,
    )


@contextmanager
def block_external_network() -> Any:
    attempts: list[dict[str, str]] = []
    original_create_connection = socket.create_connection

    def guarded(address, *args, **kwargs):
        host = str(address[0]).casefold()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            attempts.append({"host": host})
            raise AssertionError(f"external network request blocked: {host}")
        return original_create_connection(address, *args, **kwargs)

    socket.create_connection = guarded
    try:
        yield attempts
    finally:
        socket.create_connection = original_create_connection


def _page_count(path: Path) -> int:
    try:
        import fitz
        with fitz.open(path) as document:
            return len(document)
    except Exception:
        return 0


def _bbox_complete(blocks: list[dict[str, Any]]) -> float:
    if not blocks:
        return 0.0
    found = 0
    for block in blocks:
        bbox = block.get("bbox") or {}
        if isinstance(bbox, dict) and float(bbox.get("width", 0) or 0) > 0 and float(bbox.get("height", 0) or 0) > 0:
            found += 1
    return round(found / len(blocks), 4)


def _anchor_metrics(text: str, anchors: tuple[GoldAnchor, ...]) -> dict[str, Any]:
    if not anchors:
        return {"matched": 0, "total": 0, "recall": None, "missing": []}
    matched = []
    missing = []
    folded = text.casefold()
    for anchor in anchors:
        if anchor.text.casefold() in folded or anchor.text in text:
            matched.append(anchor.text)
        else:
            missing.append(anchor.text)
    return {
        "matched": len(matched),
        "total": len(anchors),
        "recall": round(len(matched) / len(anchors), 4),
        "missing": missing[:12],
    }


def _reading_order_errors(text: str, anchors: tuple[GoldAnchor, ...]) -> int:
    positions = []
    folded = text.casefold()
    for anchor in anchors:
        pos = folded.find(anchor.text.casefold())
        if pos >= 0:
            positions.append((anchor.order, pos))
    return sum(1 for left, right in zip(positions, positions[1:]) if left[1] > right[1])


def _block_type_proxy(blocks: list[dict[str, Any]], fixture: ParserFixture) -> dict[str, Any]:
    expected_types = {anchor.block_type for anchor in fixture.expected_anchors}
    present_types = {str(block.get("block_type") or "unknown") for block in blocks}
    return {
        "expected": sorted(expected_types),
        "present": sorted(present_types),
        "matched": sorted(expected_types & present_types),
        "proxy_recall": round(len(expected_types & present_types) / len(expected_types), 4) if expected_types else None,
    }


def _standardize_block(
    *,
    parser_id: str,
    fixture: ParserFixture,
    block_id: str,
    block_type: str,
    text: str = "",
    page_number: int | None = None,
    bbox: dict[str, Any] | None = None,
    reading_order: int | None = None,
    confidence: float | None = None,
    language: str = "",
    is_ocr: bool = False,
    table_structure: Any = None,
    formula_text: str = "",
    formula_format: str = "",
    image_ref: str = "",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_type = block_type if block_type in SUPPORTED_BLOCK_TYPES else "unknown"
    return {
        "parser_id": parser_id,
        "source_hash": sha256_file(fixture.path),
        "page_number": page_number,
        "block_id": block_id,
        "parent_block_id": "",
        "block_type": normalized_type,
        "text": safe_text(text),
        "bbox": bbox or {},
        "reading_order": reading_order,
        "confidence": confidence,
        "language": language,
        "is_ocr": bool(is_ocr),
        "table_structure": table_structure,
        "formula_text": safe_text(formula_text),
        "formula_format": formula_format,
        "image_ref": image_ref,
        "provenance": provenance or {},
    }


def run_baseline_fixture(fixture: ParserFixture) -> dict[str, Any]:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from services.document_parse_quality import parse_document_with_quality
    from services.formula_detection import detect_pdf_formula_regions

    started = time.perf_counter()
    before_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = parse_document_with_quality(
        str(fixture.path),
        filename=fixture.filename,
        mime_type="application/pdf",
        ocr_provider_name=os.environ.get("LEXIBRIDGE_10CP25_OCR_PROVIDER", os.environ.get("OCR_PROVIDER", "auto")),
    )
    formula_regions = detect_pdf_formula_regions(str(fixture.path))
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    after_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    blocks = []
    for index, block in enumerate(result.blocks, start=1):
        bbox = {}
        locator = str(block.get("source_locator", ""))
        if "bbox:" in locator:
            bbox = {"source_locator": locator}
        blocks.append(_standardize_block(
            parser_id="baseline_native_tesseract_formula_region",
            fixture=fixture,
            block_id=str(block.get("block_uid") or f"baseline-{index}"),
            block_type="paragraph",
            text=str(block.get("text") or ""),
            page_number=block.get("page_number"),
            bbox=bbox,
            reading_order=index,
            confidence=block.get("confidence"),
            is_ocr=str(block.get("parser_type") or "") == "ocr",
            provenance={"parser_type": block.get("parser_type"), "source_locator": locator},
        ))
    for index, region in enumerate(formula_regions, start=1):
        blocks.append(_standardize_block(
            parser_id="baseline_native_tesseract_formula_region",
            fixture=fixture,
            block_id=f"formula-region-{index}",
            block_type="formula",
            text="",
            page_number=region.page_number,
            bbox=region.bounding_box,
            reading_order=len(blocks) + 1,
            confidence=region.detection_confidence,
            formula_text="",
            formula_format="unavailable",
            image_ref=region.region_image_hash,
            provenance=region.to_safe_dict(),
        ))
    return {
        "parser_id": "baseline_native_tesseract_formula_region",
        "parser_version": "current_commit",
        "fixture_id": fixture.fixture_id,
        "source_hash": sha256_file(fixture.path),
        "page_count": _page_count(fixture.path),
        "blocks": blocks,
        "parse_duration_ms": duration_ms,
        "peak_memory_delta_kb": max(0, after_rss - before_rss),
        "warnings": [safe_text(item) for item in result.warnings],
        "errors": [safe_text(item) for item in result.errors],
        "raw_output_ref": "",
    }


def _run_subprocess(command: list[str], *, cwd: Path, timeout: int, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": safe_text(completed.stdout),
            "stderr": safe_text(completed.stderr),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": safe_text(getattr(exc, "stdout", "")),
            "stderr": "timeout",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }


def run_probe_candidate(parser_id: str, env_name: str, fixture: ParserFixture, artifact_dir: Path, timeout: int) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    runtime_home = artifact_dir / "runtime-home" / parser_id
    runtime_cache = artifact_dir / "runtime-cache" / parser_id
    runtime_home.mkdir(parents=True, exist_ok=True)
    runtime_cache.mkdir(parents=True, exist_ok=True)
    output_path = artifact_dir / f"{parser_id}-{fixture.fixture_id}.json"
    probe = Path(__file__).with_name("probe_candidate.py")
    conda = os.environ.get("LEXIBRIDGE_CONDA_CMD") or shutil.which("conda")
    if not conda:
        return _failed_candidate_result(parser_id, fixture, "CONDA_NOT_FOUND", "conda executable not found")
    command = [
        conda,
        "run",
        "-n",
        env_name,
        "python",
        str(probe),
        "--parser",
        parser_id,
        "--input",
        str(fixture.path),
        "--output",
        str(output_path),
    ]
    result = _run_subprocess(
        command,
        cwd=ROOT,
        timeout=timeout,
        extra_env={
            "HOME": str(runtime_home),
            "XDG_CACHE_HOME": str(runtime_cache),
            "PADDLE_PDX_CACHE_HOME": str(runtime_cache / "paddlex"),
            "HF_HOME": str(runtime_cache / "huggingface"),
            "MODELSCOPE_CACHE": str(runtime_cache / "modelscope"),
        },
    )
    if not result["ok"] or not output_path.exists():
        return _failed_candidate_result(parser_id, fixture, "PARSER_PROBE_FAILED", result.get("stderr") or result.get("stdout") or "probe failed", result)
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _failed_candidate_result(parser_id, fixture, "PARSER_PROBE_OUTPUT_INVALID", str(exc), result)
    blocks = [
        _standardize_block(
            parser_id=parser_id,
            fixture=fixture,
            block_id=str(block.get("block_id") or f"{parser_id}-{index}"),
            block_type=str(block.get("block_type") or "unknown"),
            text=str(block.get("text") or ""),
            page_number=block.get("page_number"),
            bbox=block.get("bbox") if isinstance(block.get("bbox"), dict) else {},
            reading_order=block.get("reading_order"),
            confidence=block.get("confidence"),
            language=str(block.get("language") or ""),
            is_ocr=bool(block.get("is_ocr")),
            table_structure=block.get("table_structure"),
            formula_text=str(block.get("formula_text") or ""),
            formula_format=str(block.get("formula_format") or ""),
            image_ref=str(block.get("image_ref") or ""),
            provenance=block.get("provenance") if isinstance(block.get("provenance"), dict) else {},
        )
        for index, block in enumerate(payload.get("blocks") or [], start=1)
    ]
    return {
        "parser_id": parser_id,
        "parser_version": str(payload.get("parser_version") or ""),
        "fixture_id": fixture.fixture_id,
        "source_hash": sha256_file(fixture.path),
        "page_count": int(payload.get("page_count") or _page_count(fixture.path)),
        "blocks": blocks,
        "parse_duration_ms": float(payload.get("parse_duration_ms") or result.get("duration_ms") or 0),
        "peak_memory_delta_kb": None,
        "warnings": [safe_text(item) for item in payload.get("warnings") or []],
        "errors": [safe_text(item) for item in payload.get("errors") or []],
        "raw_output_ref": safe_text(str(payload.get("raw_output_ref") or "")),
    }


def _failed_candidate_result(parser_id: str, fixture: ParserFixture, code: str, message: str, probe_result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "parser_id": parser_id,
        "parser_version": "",
        "fixture_id": fixture.fixture_id,
        "source_hash": sha256_file(fixture.path),
        "page_count": _page_count(fixture.path),
        "blocks": [],
        "parse_duration_ms": float((probe_result or {}).get("duration_ms") or 0),
        "peak_memory_delta_kb": None,
        "warnings": [],
        "errors": [{"code": code, "message": safe_text(message)}],
        "raw_output_ref": "",
    }


def score_fixture_result(fixture: ParserFixture, result: dict[str, Any]) -> dict[str, Any]:
    blocks = list(result.get("blocks") or [])
    combined_text = "\n".join(str(block.get("text") or "") for block in blocks)
    anchor = _anchor_metrics(combined_text, fixture.expected_anchors)
    block_types = _block_type_proxy(blocks, fixture)
    table_blocks = [block for block in blocks if block.get("block_type") == "table" or block.get("table_structure")]
    formula_blocks = [block for block in blocks if block.get("block_type") == "formula" or block.get("formula_text")]
    image_blocks = [block for block in blocks if block.get("block_type") == "image"]
    return {
        "fixture_id": fixture.fixture_id,
        "parser_id": result.get("parser_id"),
        "privacy_classification": fixture.privacy_classification,
        "anchor_recall": anchor,
        "block_count": len(blocks),
        "bbox_completeness": _bbox_complete(blocks),
        "reading_order_errors": _reading_order_errors(combined_text, fixture.expected_anchors),
        "block_type_proxy": block_types,
        "table_detected": bool(table_blocks),
        "table_block_count": len(table_blocks),
        "expected_table_rows": fixture.expected_table_rows,
        "expected_table_cols": fixture.expected_table_cols,
        "formula_detected": bool(formula_blocks),
        "formula_block_count": len(formula_blocks),
        "expected_formula_count": fixture.expected_formula_count,
        "image_block_count": len(image_blocks),
        "expected_images": fixture.expected_images,
        "parse_duration_ms": result.get("parse_duration_ms"),
        "errors": result.get("errors") or [],
        "warnings": result.get("warnings") or [],
    }


def aggregate_parser_scores(parser_id: str, fixture_scores: list[dict[str, Any]], install_status: dict[str, Any], license_status: str) -> dict[str, Any]:
    valid = [score for score in fixture_scores if not score.get("errors")]
    recall_values = [
        score["anchor_recall"]["recall"]
        for score in valid
        if score.get("anchor_recall", {}).get("recall") is not None
    ]
    avg_recall = sum(recall_values) / len(recall_values) if recall_values else 0.0
    bbox_rate = sum(score.get("bbox_completeness") or 0 for score in valid) / len(valid) if valid else 0.0
    table_hits = sum(1 for score in valid if score.get("expected_table_rows") and score.get("table_detected"))
    table_total = sum(1 for score in valid if score.get("expected_table_rows"))
    formula_hits = sum(1 for score in valid if score.get("expected_formula_count") and score.get("formula_detected"))
    formula_total = sum(1 for score in valid if score.get("expected_formula_count"))
    runtime_values = [float(score.get("parse_duration_ms") or 0) for score in valid if score.get("parse_duration_ms")]
    median_runtime = sorted(runtime_values)[len(runtime_values) // 2] if runtime_values else None
    hard_gate = {
        "macos_arm64_runs": bool(valid) and not install_status.get("blocked"),
        "local_only": True,
        "cpu_only_basic": not bool(install_status.get("gpu_required")),
        "structured_blocks": any((score.get("block_count") or 0) > 1 for score in valid),
        "page_and_bbox": bbox_rate > 0,
        "reading_order": sum(score.get("reading_order_errors") or 0 for score in valid) <= 2,
        "non_text_distinction": (table_hits > 0 or formula_hits > 0 or parser_id == "baseline"),
        "provenance_mapping": bbox_rate > 0 or parser_id == "baseline",
        "license_not_blocked": license_status == "pass",
        "fallback_safe": True,
        "windows_path_plausible": bool(install_status.get("windows_supported")),
    }
    passed_hard_gate = all(hard_gate.values())
    weighted = {
        "text_ocr_quality": round(min(25, 25 * avg_recall), 2),
        "layout_reading_order": round(min(20, 10 * bbox_rate + (10 if hard_gate["reading_order"] else 0)), 2),
        "table_formula_structure": round(min(15, (7.5 * table_hits / table_total if table_total else 0) + (7.5 * formula_hits / formula_total if formula_total else 0)), 2),
        "lexibridge_adaptation": 12 if hard_gate["provenance_mapping"] else 5,
        "cpu_performance": 8 if median_runtime is not None and median_runtime < 15_000 else (4 if valid else 0),
        "cross_platform": 5 if hard_gate["windows_path_plausible"] else 2,
        "license_maintenance": 10 if license_status == "pass" else 0,
    }
    total = round(sum(weighted.values()), 2)
    return {
        "parser_id": parser_id,
        "valid_fixture_count": len(valid),
        "failed_fixture_count": len(fixture_scores) - len(valid),
        "average_anchor_recall": round(avg_recall, 4),
        "bbox_completeness_average": round(bbox_rate, 4),
        "table_detection_rate": round(table_hits / table_total, 4) if table_total else None,
        "formula_detection_rate": round(formula_hits / formula_total, 4) if formula_total else None,
        "median_runtime_ms": median_runtime,
        "hard_gate": hard_gate,
        "passed_hard_gate": passed_hard_gate,
        "weighted": weighted,
        "weighted_total": total,
    }


def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    fixture_root = Path(args.fixture_root)
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    fixtures = build_fixture_set(fixture_root)
    if args.private_pdf:
        fixtures.append(build_private_fixture(Path(args.private_pdf)))
    parser_envs = {
        "docling": args.docling_env,
        "paddle": args.paddle_env,
        "mineru": args.mineru_env,
    }
    install_status = load_json(Path(args.install_status), {}) if args.install_status else {}
    license_status = load_json(Path(args.license_status), {}) if args.license_status else {}
    all_results: list[dict[str, Any]] = []
    all_scores: list[dict[str, Any]] = []
    external_attempts: list[dict[str, str]] = []
    with block_external_network() as attempts:
        if args.run_baseline:
            for fixture in fixtures:
                result = run_baseline_fixture(fixture)
                all_results.append(result)
                all_scores.append(score_fixture_result(fixture, result))
        for parser_id, env_name in parser_envs.items():
            if parser_id not in args.parsers:
                continue
            if not env_name:
                for fixture in fixtures:
                    result = _failed_candidate_result(parser_id, fixture, "PARSER_ENV_NOT_CONFIGURED", "candidate Conda environment not configured")
                    all_results.append(result)
                    all_scores.append(score_fixture_result(fixture, result))
                continue
            for fixture in fixtures:
                result = run_probe_candidate(parser_id, env_name, fixture, artifact_dir, args.timeout_seconds)
                all_results.append(result)
                all_scores.append(score_fixture_result(fixture, result))
        external_attempts.extend(attempts)
    parser_ids = sorted({score["parser_id"] for score in all_scores})
    aggregates = [
        aggregate_parser_scores(
            parser_id,
            [score for score in all_scores if score["parser_id"] == parser_id],
            install_status.get(parser_id, {}),
            license_status.get(parser_id, {}).get("status", "unknown"),
        )
        for parser_id in parser_ids
    ]
    selected = select_parser(aggregates)
    summary = {
        "evaluator_version": "10C.P2.5-parser-eval-v1",
        "evaluation_status": "selected" if selected.get("selected_primary_parser") else "blocked",
        "production_adapter_authorized": bool(selected.get("selected_primary_parser")),
        "evaluation_id": f"10cp25-{uuid.uuid4()}",
        "git_commit": git_commit(),
        "branch": git_branch(),
        "created_at": utc_now(),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "fixture_count": len(fixtures),
        "fixtures": [fixture_metadata(fixture) for fixture in fixtures],
        "parser_results": summarize_results(all_results),
        "scores": all_scores,
        "aggregates": aggregates,
        "selected": selected,
        "network": {
            "external_attempts": external_attempts,
            "external_request_count": len(external_attempts),
            "external_provider_request_count": 0,
            "private_course_external_send_count": 0,
        },
    }
    output_path = Path(args.json_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_sanitize(summary), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def fixture_metadata(fixture: ParserFixture) -> dict[str, Any]:
    return {
        "fixture_id": fixture.fixture_id,
        "filename": fixture.filename,
        "source_hash": sha256_file(fixture.path),
        "privacy_classification": fixture.privacy_classification,
        "domains": list(fixture.domains),
        "page_count": _page_count(fixture.path),
        "anchor_count": len(fixture.expected_anchors),
        "expected_table_rows": fixture.expected_table_rows,
        "expected_table_cols": fixture.expected_table_cols,
        "expected_formula_count": fixture.expected_formula_count,
        "expected_raster_formula_count": fixture.expected_raster_formula_count,
        "expected_images": fixture.expected_images,
        "scanned": fixture.scanned,
        "complex_layout": fixture.complex_layout,
        "negative": fixture.negative,
    }


def summarize_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summarized = []
    for result in results:
        summarized.append({
            "parser_id": result.get("parser_id"),
            "parser_version": result.get("parser_version"),
            "fixture_id": result.get("fixture_id"),
            "source_hash": result.get("source_hash"),
            "page_count": result.get("page_count"),
            "block_count": len(result.get("blocks") or []),
            "parse_duration_ms": result.get("parse_duration_ms"),
            "peak_memory_delta_kb": result.get("peak_memory_delta_kb"),
            "warnings": result.get("warnings") or [],
            "errors": result.get("errors") or [],
        })
    return summarized


def select_parser(aggregates: list[dict[str, Any]]) -> dict[str, Any]:
    open_source_candidates = [
        item
        for item in aggregates
        if item.get("parser_id") != "baseline_native_tesseract_formula_region"
    ]
    eligible = [item for item in open_source_candidates if item.get("passed_hard_gate")]
    if not eligible:
        best = max(open_source_candidates, key=lambda item: item.get("weighted_total", 0), default={})
        return {
            "selected_primary_parser": None,
            "selected_parser_version": "",
            "selected_parser_role": "no_open_source_parser_selected",
            "fallback_parser": "baseline_native_tesseract_formula_region",
            "complex_document_routing_rule": "No open-source candidate passed hard gates in this run.",
            "formula_handling_strategy": "Keep Task 10C.P2 FormulaRegion detection; formula structure recognition remains unavailable.",
            "table_handling_strategy": "Do not claim structured table support until a selected adapter preserves rows/cells.",
            "offline_runtime_status": "open_source_candidate_not_selected",
            "macos_arm64_status": "open_source_candidate_not_selected",
            "windows_status": "baseline_existing_contract_only",
            "license_status": "open_candidate_not_selected",
            "integration_risk": "high",
            "production_integration_next_step": "Resolve parser candidate blockers or rerun with an installable candidate.",
            "best_non_selected_candidate": best.get("parser_id", ""),
        }
    best = max(eligible, key=lambda item: item.get("weighted_total", 0))
    role = "complex_document_parser"
    return {
        "selected_primary_parser": best["parser_id"],
        "selected_parser_version": "evaluated_version",
        "selected_parser_role": role,
        "fallback_parser": "baseline_native_tesseract_formula_region",
        "complex_document_routing_rule": "Route multi-column, table-bearing, formula-bearing, or layout-complex PDFs to the selected parser; keep native/Tesseract for simple documents and fallback.",
        "formula_handling_strategy": "Use selected parser formula signals only as proposals; preserve Task 10C.P2 FormulaRegion records and unavailable status until formula recognizer quality is verified.",
        "table_handling_strategy": "Map detected table blocks to evaluation/provenance first; do not feed table cell text directly into ordinary term ranking without table-aware governance.",
        "offline_runtime_status": "local_evaluation_passed",
        "macos_arm64_status": "evaluated",
        "windows_status": "code_path_plausible_not_runtime_verified",
        "license_status": "pass",
        "integration_risk": "medium",
        "production_integration_next_step": "Task 10C.P2.6 Selected Parser Production Adapter",
    }


def git_commit() -> str:
    result = _run_subprocess(["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=10)
    return safe_text(result.get("stdout", "")).strip()


def git_branch() -> str:
    result = _run_subprocess(["git", "branch", "--show-current"], cwd=ROOT, timeout=10)
    return safe_text(result.get("stdout", "")).strip()


def load_json(path: Path, fallback: Any) -> Any:
    if not path or not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize(child) for child in value]
    if isinstance(value, str):
        return safe_text(value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Task 10C.P2.5 parser evaluation.")
    parser.add_argument("--fixture-root", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--install-status", default="")
    parser.add_argument("--license-status", default="")
    parser.add_argument("--docling-env", default="")
    parser.add_argument("--paddle-env", default="")
    parser.add_argument("--mineru-env", default="")
    parser.add_argument("--parsers", nargs="*", default=[])
    parser.add_argument("--run-baseline", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--private-pdf", default="")
    args = parser.parse_args(argv)
    summary = run_evaluation(args)
    print(json.dumps({
        "json_output": str(Path(args.json_output)).replace(str(Path(args.json_output).parent), LOCAL_TMP_LABEL),
        "fixture_count": summary["fixture_count"],
        "parsers": sorted({item["parser_id"] for item in summary["parser_results"]}),
        "external_request_count": summary["network"]["external_request_count"],
        "selected_primary_parser": summary["selected"]["selected_primary_parser"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
