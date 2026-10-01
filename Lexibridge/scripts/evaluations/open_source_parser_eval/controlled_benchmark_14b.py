#!/usr/bin/env python3
"""Controlled current/Docling/MinerU parser benchmark for LexiBridge.

The module deliberately normalizes parser output into the existing parse-block
and KnowledgeChunk contracts.  It is evaluation-only: importing it does not
load a third-party parser, open a database, download a model, or change
production parser routing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
PARSER_IDS = (
    "baseline_native_tesseract_formula_region",
    "docling",
    "mineru",
)
SCHEMA_VERSION = "controlled-parser-benchmark-14b@1.0.0"
LOCAL_PATH_RE = re.compile(
    r"(?:/Users/|/private/(?:tmp|var)/|file://)[^\s\"']+", re.IGNORECASE
)
SECRET_RE = re.compile(
    r"(?:authorization|cookie)\s*[:=][^\s,}]+|Bearer\s+[^\s,}]+|sk-[A-Za-z0-9_-]+",
    re.IGNORECASE,
)
BODY_KEYS = frozenset(
    {
        "request_body",
        "response_body",
        "source_body",
        "full_source",
        "raw_output",
        "prompt_body",
    }
)
NOISE_TYPES = frozenset({"header", "footer", "page_number"})
CONTENT_TYPES = frozenset(
    {"heading", "paragraph", "list_item", "table", "formula", "image", "caption"}
)


@dataclass(frozen=True)
class BenchmarkFixture:
    fixture_id: str
    filename: str
    path: Path
    privacy_classification: str
    expected_anchors: tuple[Any, ...] = ()
    expected_heading_definition_pairs: tuple[tuple[str, str], ...] = ()
    expected_noise: tuple[str, ...] = ()
    expected_table_rows: int = 0
    expected_table_cols: int = 0
    expected_formula_count: int = 0
    language: str = "unknown"
    purpose: str = "parser_quality"


@dataclass(frozen=True)
class RetrievalConcept:
    concept_id: str
    english_term: str
    english_definition: str
    chinese_term: str
    chinese_definition: str
    discipline: str


RETRIEVAL_CONCEPTS: tuple[RetrievalConcept, ...] = (
    RetrievalConcept(
        "electric_charge",
        "Electric Charge",
        "A conserved property of matter that determines electrical interaction and can be positive or negative.",
        "电荷",
        "物质的一种守恒属性，决定物体参与电相互作用的方式，并可表现为正或负。",
        "physics",
    ),
    RetrievalConcept(
        "electric_field",
        "Electric Field",
        "A vector field assigning the force per unit positive test charge at each point in space.",
        "电场",
        "空间中每一点对单位正试探电荷作用力的矢量场。",
        "physics",
    ),
    RetrievalConcept(
        "electric_potential",
        "Electric Potential",
        "The electric potential energy per unit charge at a point, measured relative to a reference.",
        "电势",
        "某点单位电荷具有的电势能，以选定参考点为基准进行度量。",
        "physics",
    ),
    RetrievalConcept(
        "momentum",
        "Momentum",
        "A vector quantity equal to mass times velocity that describes translational motion.",
        "动量",
        "质量与速度乘积构成的矢量物理量，用于描述物体的平动状态。",
        "mechanics",
    ),
    RetrievalConcept(
        "impulse",
        "Impulse",
        "The time integral of force, equal to the change in momentum over an interval.",
        "冲量",
        "力对时间的积分，数值上等于物体在该时间间隔内动量的变化。",
        "mechanics",
    ),
    RetrievalConcept(
        "torque",
        "Torque",
        "The moment of a force about an axis that measures its tendency to cause rotation.",
        "力矩",
        "力对某一转轴的矩，用于度量该力使物体产生转动的趋势。",
        "mechanics",
    ),
    RetrievalConcept(
        "moment_of_inertia",
        "Moment of Inertia",
        "A mass-distribution property describing resistance to changes in rotational motion.",
        "转动惯量",
        "由质量分布决定、描述物体抵抗转动状态改变能力的物理量。",
        "mechanics",
    ),
    RetrievalConcept(
        "damping_ratio",
        "Damping Ratio",
        "A dimensionless ratio comparing actual damping with critical damping in a second-order system.",
        "阻尼比",
        "二阶系统实际阻尼与临界阻尼之比，是描述振动衰减程度的无量纲参数。",
        "control engineering",
    ),
    RetrievalConcept(
        "boundary_condition",
        "Boundary Condition",
        "A constraint imposed on a differential-equation solution at the boundary of its domain.",
        "边界条件",
        "在定义域边界处对微分方程解施加的约束条件。",
        "applied mathematics",
    ),
    RetrievalConcept(
        "transfer_function",
        "Transfer Function",
        "The ratio of output to input in the transform domain for a linear time-invariant system under zero initial conditions.",
        "传递函数",
        "在线性时不变系统零初始条件下，变换域中输出与输入之比。",
        "control engineering",
    ),
)


def _anchor(text: str, order: int) -> Any:
    return SimpleNamespace(text=text, block_type="paragraph", order=order)


def _write_concept_pdf(
    path: Path,
    *,
    document_title: str,
    concepts: Sequence[tuple[str, str]],
    language: str,
) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from scripts.evaluations.open_source_parser_eval import evaluate

    path.parent.mkdir(parents=True, exist_ok=True)
    font = evaluate._register_font()
    document = canvas.Canvas(str(path), pagesize=letter)
    _, height = letter
    document.setTitle(document_title)
    y = height - 56
    document.setFont(font, 18)
    document.drawString(54, y, document_title)
    y -= 42
    for term, definition in concepts:
        if y < 120:
            document.showPage()
            y = height - 56
        document.setFont(font, 14)
        document.drawString(54, y, term)
        y -= 24
        document.setFont(font, 10.5)
        # Keep the synthetic definition on one line so every parser receives
        # the same explicit heading-definition relation.
        document.drawString(68, y, definition[:165])
        y -= 42
    document.save()


def _write_repeated_header_footer_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from scripts.evaluations.open_source_parser_eval import evaluate

    path.parent.mkdir(parents=True, exist_ok=True)
    font = evaluate._register_font()
    document = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    for page_number, body in enumerate(
        (
            "Conservation law body paragraph for the first page.",
            "Rotational dynamics body paragraph for the second page.",
            "Control-system response body paragraph for the third page.",
        ),
        start=1,
    ):
        document.setFont(font, 8)
        document.drawString(54, height - 24, "LexiBridge Evaluation Header")
        document.drawString(54, 22, "LexiBridge Evaluation Footer")
        document.drawRightString(width - 54, 22, f"Page {page_number}")
        document.setFont(font, 15)
        document.drawString(54, height - 90, f"Section {page_number}")
        document.setFont(font, 11)
        document.drawString(54, height - 122, body)
        document.showPage()
    document.save()


def build_controlled_fixture_set(root: Path) -> list[BenchmarkFixture]:
    """Build the bounded safe corpus used by the 14B comparison."""

    from scripts.evaluations.open_source_parser_eval import evaluate

    root.mkdir(parents=True, exist_ok=True)
    baseline_fixtures = {
        fixture.fixture_id: fixture for fixture in evaluate.build_fixture_set(root / "legacy")
    }
    selected_ids = (
        "single_column_born_digital",
        "two_column_born_digital",
        "scanned_english",
        "scanned_chinese",
        "mixed_layout_blocker",
        "simple_table",
        "raster_formula",
        "negative_no_terms",
    )
    fixtures = [
        BenchmarkFixture(
            fixture_id=fixture.fixture_id,
            filename=fixture.filename,
            path=fixture.path,
            privacy_classification="SYNTHETIC",
            expected_anchors=fixture.expected_anchors,
            expected_table_rows=fixture.expected_table_rows,
            expected_table_cols=fixture.expected_table_cols,
            expected_formula_count=fixture.expected_formula_count,
            language=("zh" if fixture.fixture_id == "scanned_chinese" else "en"),
        )
        for fixture in (baseline_fixtures[fixture_id] for fixture_id in selected_ids)
    ]

    repeated = root / "repeated-header-footer.pdf"
    _write_repeated_header_footer_pdf(repeated)
    fixtures.append(
        BenchmarkFixture(
            fixture_id="repeated_header_footer",
            filename=repeated.name,
            path=repeated,
            privacy_classification="SYNTHETIC",
            expected_anchors=(
                _anchor("Conservation law body paragraph", 1),
                _anchor("Rotational dynamics body paragraph", 2),
                _anchor("Control-system response body paragraph", 3),
            ),
            expected_heading_definition_pairs=(
                ("Section 1", "Conservation law body paragraph"),
                ("Section 2", "Rotational dynamics body paragraph"),
                ("Section 3", "Control-system response body paragraph"),
            ),
            expected_noise=(
                "LexiBridge Evaluation Header",
                "LexiBridge Evaluation Footer",
                "Page 1",
                "Page 2",
                "Page 3",
            ),
            language="en",
        )
    )

    english_path = root / "retrieval-english-concepts.pdf"
    chinese_path = root / "retrieval-chinese-evidence.pdf"
    _write_concept_pdf(
        english_path,
        document_title="Engineering Concept Notes",
        concepts=[(item.english_term, item.english_definition) for item in RETRIEVAL_CONCEPTS],
        language="en",
    )
    _write_concept_pdf(
        chinese_path,
        document_title="工程概念参考资料",
        concepts=[(item.chinese_term, item.chinese_definition) for item in RETRIEVAL_CONCEPTS],
        language="zh",
    )
    fixtures.extend(
        (
            BenchmarkFixture(
                fixture_id="retrieval_english",
                filename=english_path.name,
                path=english_path,
                privacy_classification="SYNTHETIC",
                expected_anchors=tuple(
                    _anchor(item.english_term, index)
                    for index, item in enumerate(RETRIEVAL_CONCEPTS, start=1)
                ),
                expected_heading_definition_pairs=tuple(
                    (item.english_term, item.english_definition[:40])
                    for item in RETRIEVAL_CONCEPTS
                ),
                language="en",
                purpose="downstream_retrieval",
            ),
            BenchmarkFixture(
                fixture_id="retrieval_chinese",
                filename=chinese_path.name,
                path=chinese_path,
                privacy_classification="SYNTHETIC",
                expected_anchors=tuple(
                    _anchor(item.chinese_term, index)
                    for index, item in enumerate(RETRIEVAL_CONCEPTS, start=1)
                ),
                expected_heading_definition_pairs=tuple(
                    (item.chinese_term, item.chinese_definition[:20])
                    for item in RETRIEVAL_CONCEPTS
                ),
                language="zh",
                purpose="downstream_retrieval",
            ),
        )
    )
    return fixtures


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split()).strip()


def _normalized(value: Any) -> str:
    return _text(value).casefold()


def _flatten_content(value: Any) -> str:
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            if node.strip():
                parts.append(node.strip())
            return
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if not isinstance(node, dict):
            return
        for key, child in node.items():
            if key in {"content", "text", "title", "latex", "html"}:
                walk(child)
            elif key.endswith("_content"):
                walk(child)

    walk(value)
    ordered: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = _normalized(part)
        if normalized and normalized not in seen:
            ordered.append(_text(part))
            seen.add(normalized)
    return "\n".join(ordered)


def _mineru_type(value: Any) -> str:
    kind = str(value or "").strip().casefold()
    if kind in {"title", "heading", "section_header"}:
        return "heading"
    if kind in {"paragraph", "text"}:
        return "paragraph"
    if kind in {"list", "list_item"}:
        return "list_item"
    if kind in {"table"}:
        return "table"
    if kind in {"equation", "formula", "interline_equation", "inline_equation"}:
        return "formula"
    if kind in {"image", "figure", "picture"}:
        return "image"
    if "caption" in kind:
        return "caption"
    if "header" in kind:
        return "header"
    if "footer" in kind:
        return "footer"
    if kind in {"page_number", "page-number"}:
        return "page_number"
    return "unknown"


def _bbox(value: Any) -> dict[str, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        try:
            x0, y0, x1, y1 = (float(value[index]) for index in range(4))
            return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
        except (TypeError, ValueError):
            return {}
    if not isinstance(value, dict):
        return {}
    aliases = {
        "x0": value.get("x0", value.get("l", value.get("left"))),
        "y0": value.get("y0", value.get("t", value.get("top"))),
        "x1": value.get("x1", value.get("r", value.get("right"))),
        "y1": value.get("y1", value.get("b", value.get("bottom"))),
    }
    try:
        return {key: float(child) for key, child in aliases.items() if child is not None}
    except (TypeError, ValueError):
        return {}


def normalize_mineru_content_list_v2(
    pages: Sequence[Any], *, fixture_id: str
) -> list[dict[str, Any]]:
    """Normalize MinerU's page-grouped content-list-v2 without raw bodies."""

    blocks: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages or (), start=1):
        if isinstance(page, dict):
            page_items = page.get("blocks") or page.get("content") or []
        else:
            page_items = page
        if not isinstance(page_items, list):
            continue
        for item in page_items:
            if not isinstance(item, dict):
                continue
            block_type = _mineru_type(item.get("type"))
            content = item.get("content")
            text = _flatten_content(content)
            if not text:
                text = _text(item.get("text") or item.get("img_caption"))
            order = len(blocks) + 1
            block_id = f"mineru-{fixture_id}-p{page_index}-b{order}"
            table_structure = None
            if block_type == "table":
                table_structure = _mineru_table_shape(content)
            blocks.append(
                {
                    "parser_id": "mineru",
                    "fixture_id": fixture_id,
                    "block_id": block_id,
                    "parent_block_id": "",
                    "block_type": block_type,
                    "text": text,
                    "page_number": page_index,
                    "bbox": _bbox(item.get("bbox")),
                    "reading_order": order,
                    "confidence": item.get("score"),
                    "language": "",
                    "is_ocr": False,
                    "table_structure": table_structure,
                    "formula_text": text if block_type == "formula" else "",
                    "formula_format": "latex" if block_type == "formula" and text else "",
                    "image_ref": "",
                    "provenance": {
                        "source_parser": "mineru",
                        "source_item_ref": block_id,
                        "page_index_zero_based": page_index - 1,
                    },
                }
            )
    return blocks


def _mineru_table_shape(content: Any) -> dict[str, int] | None:
    text = _flatten_content(content)
    html = text if "<table" in text.casefold() else ""
    if html:
        rows = len(re.findall(r"<tr\b", html, flags=re.IGNORECASE))
        cells = [
            len(re.findall(r"<t[dh]\b", row, flags=re.IGNORECASE))
            for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
        ]
        return {"rows": rows, "cols": max(cells, default=0)}
    return None


def _ordered_blocks(blocks: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        list(blocks or ()),
        key=lambda block: (
            int(block.get("page_number") or 0),
            int(block.get("reading_order") or 0),
            str(block.get("block_id") or ""),
        ),
    )


def _anchor_text(anchor: Any) -> str:
    return str(getattr(anchor, "text", anchor if isinstance(anchor, str) else "") or "")


def reading_order_accuracy(
    blocks: Iterable[Mapping[str, Any]], expected_anchors: Sequence[Any]
) -> float | None:
    expected = [_anchor_text(anchor) for anchor in expected_anchors if _anchor_text(anchor)]
    if len(expected) < 2:
        return None
    body = "\n".join(str(block.get("text") or "") for block in _ordered_blocks(blocks)).casefold()
    positions = {anchor: body.find(anchor.casefold()) for anchor in expected}
    present = [anchor for anchor in expected if positions[anchor] >= 0]
    if len(present) < 2:
        return 0.0
    correct = 0
    total = 0
    for left_index, left in enumerate(present):
        for right in present[left_index + 1 :]:
            total += 1
            correct += int(positions[left] < positions[right])
    return round(correct / total, 4) if total else 0.0


def heading_definition_integrity(
    blocks: Iterable[Mapping[str, Any]], pairs: Sequence[tuple[str, str]]
) -> float | None:
    if not pairs:
        return None
    ordered = _ordered_blocks(blocks)
    matched = 0
    for heading, definition in pairs:
        heading_norm = heading.casefold()
        definition_norm = definition.casefold()
        heading_indexes = [
            index
            for index, block in enumerate(ordered)
            if heading_norm in str(block.get("text") or "").casefold()
        ]
        definition_indexes = [
            index
            for index, block in enumerate(ordered)
            if definition_norm in str(block.get("text") or "").casefold()
        ]
        if any(abs(left - right) <= 1 for left in heading_indexes for right in definition_indexes):
            matched += 1
    return round(matched / len(pairs), 4)


def duplicate_block_count(blocks: Iterable[Mapping[str, Any]]) -> int:
    counts = Counter(
        _normalized(block.get("text"))
        for block in blocks or ()
        if _normalized(block.get("text")) and str(block.get("block_type") or "") not in NOISE_TYPES
    )
    return sum(max(0, count - 1) for count in counts.values())


def _bbox_complete(block: Mapping[str, Any]) -> bool:
    bbox = _bbox(block.get("bbox"))
    return (
        len(bbox) == 4
        and bbox["x1"] > bbox["x0"]
        and bbox["y1"] > bbox["y0"]
    )


def _rate(values: Sequence[bool]) -> float:
    return round(sum(bool(value) for value in values) / len(values), 4) if values else 0.0


def _noise_filter_rate(blocks: Sequence[Mapping[str, Any]], expected: Sequence[str]) -> float | None:
    if not expected:
        return None
    body_text = "\n".join(
        str(block.get("text") or "")
        for block in blocks
        if str(block.get("block_type") or "") not in NOISE_TYPES
    ).casefold()
    filtered = sum(1 for noise in expected if noise.casefold() not in body_text)
    return round(filtered / len(expected), 4)


def _table_retention(blocks: Sequence[Mapping[str, Any]], fixture: Any) -> float | None:
    rows = int(getattr(fixture, "expected_table_rows", 0) or 0)
    cols = int(getattr(fixture, "expected_table_cols", 0) or 0)
    if not rows and not cols:
        return None
    tables = [block for block in blocks if block.get("block_type") == "table"]
    if not tables:
        return 0.0
    shapes = [block.get("table_structure") for block in tables if isinstance(block.get("table_structure"), dict)]
    if not shapes:
        return 0.5
    best_rows = max(int(shape.get("rows") or 0) for shape in shapes)
    best_cols = max(int(shape.get("cols") or 0) for shape in shapes)
    return round(min(1.0, min(best_rows / max(rows, 1), best_cols / max(cols, 1))), 4)


def _formula_retention(blocks: Sequence[Mapping[str, Any]], fixture: Any) -> float | None:
    expected = int(getattr(fixture, "expected_formula_count", 0) or 0)
    if not expected:
        return None
    found = sum(1 for block in blocks if block.get("block_type") == "formula")
    return round(min(1.0, found / expected), 4)


def score_document(fixture: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    blocks = list(result.get("blocks") or [])
    content = [
        block
        for block in blocks
        if str(block.get("block_type") or "") in CONTENT_TYPES
        and str(block.get("text") or "").strip()
    ]
    return {
        "fixture_id": getattr(fixture, "fixture_id", ""),
        "parser_id": result.get("parser_id"),
        "parse_success": bool(content) and not bool(result.get("errors")),
        "block_count": len(content),
        "reading_order_accuracy": reading_order_accuracy(
            content, getattr(fixture, "expected_anchors", ())
        ),
        "heading_definition_integrity": heading_definition_integrity(
            content, getattr(fixture, "expected_heading_definition_pairs", ())
        ),
        "page_provenance_completeness": _rate(
            [block.get("page_number") not in (None, "") for block in content]
        ),
        "block_provenance_completeness": _rate(
            [
                bool(block.get("block_id"))
                and isinstance(block.get("provenance"), dict)
                and bool(block.get("provenance"))
                for block in content
            ]
        ),
        "bbox_provenance_completeness": _rate([_bbox_complete(block) for block in content]),
        "table_retention": _table_retention(content, fixture),
        "formula_retention": _formula_retention(content, fixture),
        "header_footer_filter_rate": _noise_filter_rate(
            blocks, getattr(fixture, "expected_noise", ())
        ),
        "duplicate_block_count": duplicate_block_count(content),
        "runtime_ms": float(result.get("parse_duration_ms") or 0),
        "peak_rss_mb": float(result.get("peak_rss_mb") or 0),
        "errors": list(result.get("errors") or []),
        "warnings": list(result.get("warnings") or []),
    }


def parser_result_to_ingestion_contract(
    *,
    parser_id: str,
    parser_version: str,
    fixture_id: str,
    blocks: Sequence[Mapping[str, Any]],
    language: str,
) -> tuple[Any, list[Any]]:
    parse_uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"14b:{parser_id}:{fixture_id}"))
    parse_record = SimpleNamespace(
        parse_uid=parse_uid,
        source_filename=f"{fixture_id}.pdf",
        file_type="pdf",
        parser_name=parser_id,
        parser_version=parser_version,
        quality_status="native_text_ok",
        quality_flags=["layout_applied", f"parser_backend_{parser_id}"],
        warnings=[],
    )
    parse_blocks = []
    for index, block in enumerate(_ordered_blocks(blocks), start=1):
        block_type = str(block.get("block_type") or "text")
        if block_type in NOISE_TYPES or not str(block.get("text") or "").strip():
            continue
        bbox = _bbox(block.get("bbox"))
        locator = f"page:{block.get('page_number') or 'unknown'}"
        if len(bbox) == 4:
            locator += ";bbox:{x0},{y0},{x1},{y1}".format(**bbox)
        parse_blocks.append(
            SimpleNamespace(
                block_uid=str(block.get("block_id") or f"{parser_id}-{fixture_id}-{index}"),
                page_number=block.get("page_number"),
                block_index=index,
                block_type=("title" if block_type == "heading" else block_type),
                text=str(block.get("text") or ""),
                confidence=block.get("confidence"),
                parser_type=parser_id,
                source_locator=locator[:160],
                quality_flags=["layout", f"layout_type_{block_type}"],
                language=language,
            )
        )
    return parse_record, parse_blocks


def build_existing_pipeline_chunks(
    *, parse_record: Any, parse_blocks: list[Any], source_uid: str, language: str
) -> list[dict[str, Any]]:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from services import knowledge_governance

    return knowledge_governance.build_knowledge_chunks_from_parse_blocks(
        parse_record,
        parse_blocks,
        source_uid,
        {
            "language": language,
            "course": "14B Synthetic Parser Benchmark",
            "source_type": "reference" if language == "zh" else "course_material",
            "trust_level": "reference_material",
            "scope_type": "personal",
            "knowledge_base_type": "synthetic_evaluation",
        },
    )


def rank_metrics(rankings: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    denominator = len(rankings)
    ranks: list[int] = []
    no_result = 0
    for expected, observed in rankings.items():
        if not observed:
            no_result += 1
            continue
        try:
            ranks.append(list(observed).index(expected) + 1)
        except ValueError:
            continue
    return {
        "denominator": denominator,
        "hit_at_1": round(sum(rank == 1 for rank in ranks) / denominator, 4) if denominator else 0.0,
        "hit_at_3": round(sum(rank <= 3 for rank in ranks) / denominator, 4) if denominator else 0.0,
        "mrr": round(sum(1 / rank for rank in ranks) / denominator, 4) if denominator else 0.0,
        "no_result_count": no_result,
        "average_correct_rank": round(sum(ranks) / len(ranks), 4) if ranks else None,
    }


def evaluate_downstream_retrieval(
    *,
    parser_id: str,
    parser_version: str,
    english_result: Mapping[str, Any],
    chinese_result: Mapping[str, Any],
    model_cache_dir: str | Path,
) -> dict[str, Any]:
    """Run the existing multilingual retrieval over existing-pipeline chunks.

    Gold concept ids are consulted only after parser output has been converted
    to KnowledgeChunk-shaped records.  They never enter parser input, chunk
    construction, embedding text, or ranking.
    """

    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from services.cross_language_retrieval import (
        CrossLanguageRetrievalQuery,
        SemanticPassage,
        rank_chinese_passages,
    )
    from services.local_multilingual_embedding import LocalMultilingualEmbeddingBackend

    en_record, en_blocks = parser_result_to_ingestion_contract(
        parser_id=parser_id,
        parser_version=parser_version,
        fixture_id="retrieval_english",
        blocks=list(english_result.get("blocks") or []),
        language="en",
    )
    zh_record, zh_blocks = parser_result_to_ingestion_contract(
        parser_id=parser_id,
        parser_version=parser_version,
        fixture_id="retrieval_chinese",
        blocks=list(chinese_result.get("blocks") or []),
        language="zh",
    )
    english_chunks = build_existing_pipeline_chunks(
        parse_record=en_record,
        parse_blocks=en_blocks,
        source_uid=f"14b-{parser_id}-en",
        language="en",
    )
    chinese_chunks = build_existing_pipeline_chunks(
        parse_record=zh_record,
        parse_blocks=zh_blocks,
        source_uid=f"14b-{parser_id}-zh",
        language="zh",
    )
    passages = [
        SemanticPassage(
            source_uid=chunk["source_uid"],
            chunk_uid=chunk["chunk_uid"],
            content=chunk["text"],
            language="zh",
            source_status="active",
            quality_status=chunk.get("quality_status") or "native_text_ok",
            content_hash=chunk["content_hash"],
            page_number=chunk.get("page_number"),
            block_uid=chunk.get("parse_block_uid") or "",
            heading_path=chunk.get("source_section") or "",
        )
        for chunk in chinese_chunks
    ]
    backend = LocalMultilingualEmbeddingBackend(model_cache_dir=model_cache_dir)
    rankings: dict[str, list[str]] = {}
    representation_cache: dict[str, list[float]] = {}
    for concept in RETRIEVAL_CONCEPTS:
        english_chunk = next(
            (
                chunk
                for chunk in english_chunks
                if concept.english_term.casefold() in str(chunk.get("text") or "").casefold()
            ),
            None,
        )
        if english_chunk is None:
            rankings[concept.concept_id] = []
            continue
        query = CrossLanguageRetrievalQuery(
            english_candidate_uid=f"14b-{parser_id}-{concept.concept_id}",
            canonical_english_term=concept.english_term,
            normalized_english_term=concept.english_term.casefold(),
            english_context=str(english_chunk.get("text") or ""),
            discipline=concept.discipline,
            allowed_chinese_source_uids=(f"14b-{parser_id}-zh",),
            top_k=3,
            retrieval_budget=100,
        )
        results = rank_chinese_passages(
            query,
            passages,
            backend,
            representation_cache=representation_cache,
        )
        observed: list[str] = []
        by_uid = {chunk["chunk_uid"]: chunk for chunk in chinese_chunks}
        for result in results:
            content = str(by_uid.get(result.chunk_uid, {}).get("text") or "")
            matched = [
                item.concept_id
                for item in RETRIEVAL_CONCEPTS
                if item.chinese_term in content
            ]
            observed.append(matched[0] if len(matched) == 1 else f"ambiguous:{result.chunk_uid}")
        rankings[concept.concept_id] = observed
    metrics = rank_metrics(rankings)
    return {
        **metrics,
        "parser_id": parser_id,
        "parser_version": parser_version,
        "english_chunk_count": len(english_chunks),
        "chinese_chunk_count": len(chinese_chunks),
        "rankings": rankings,
        "model_id": backend.model_id,
        "model_revision": backend.model_revision,
        "backend_id": backend.backend_id,
        "gold_used_in_parser": False,
        "gold_used_in_retrieval": False,
        "gold_used_post_ranking": True,
        "external_api_used": False,
    }


def _aggregate_value(rows: Sequence[Mapping[str, Any]], field_name: str) -> float | None:
    values = [float(row[field_name]) for row in rows if row.get(field_name) is not None]
    return round(statistics.fmean(values), 4) if values else None


def aggregate_parser(
    parser_id: str,
    document_scores: Sequence[Mapping[str, Any]],
    retrieval: Mapping[str, Any],
    *,
    license_gate: str,
) -> dict[str, Any]:
    rows = [row for row in document_scores if row.get("parser_id") == parser_id]
    succeeded = sum(bool(row.get("parse_success")) for row in rows)
    by_fixture = {str(row.get("fixture_id")): row for row in rows}

    def fixture_value(fixture_id: str, field_name: str) -> Any:
        return by_fixture.get(fixture_id, {}).get(field_name)

    return {
        "parser_id": parser_id,
        "document_count": len(rows),
        "parse_success_rate": round(succeeded / len(rows), 4) if rows else 0.0,
        "reading_order_accuracy": _aggregate_value(rows, "reading_order_accuracy"),
        "heading_definition_integrity": _aggregate_value(rows, "heading_definition_integrity"),
        "page_provenance_completeness": _aggregate_value(rows, "page_provenance_completeness"),
        "block_provenance_completeness": _aggregate_value(rows, "block_provenance_completeness"),
        "bbox_provenance_completeness": _aggregate_value(rows, "bbox_provenance_completeness"),
        "table_retention": _aggregate_value(rows, "table_retention"),
        "formula_retention": _aggregate_value(rows, "formula_retention"),
        "header_footer_filter_rate": _aggregate_value(rows, "header_footer_filter_rate"),
        "duplicate_block_count": sum(int(row.get("duplicate_block_count") or 0) for row in rows),
        "median_runtime_ms": round(statistics.median([float(row.get("runtime_ms") or 0) for row in rows]), 2) if rows else None,
        "peak_rss_mb": max((float(row.get("peak_rss_mb") or 0) for row in rows), default=0.0),
        "retrieval_hit_at_1": retrieval.get("hit_at_1"),
        "retrieval_hit_at_3": retrieval.get("hit_at_3"),
        "retrieval_mrr": retrieval.get("mrr"),
        "retrieval_english_chunk_count": retrieval.get("english_chunk_count"),
        "retrieval_chinese_chunk_count": retrieval.get("chinese_chunk_count"),
        # Aggregate means are useful for comparison but may conceal a
        # catastrophic document class.  Keep every routing-critical fixture
        # explicit so a high average cannot silently authorize production.
        "critical_fixture_gates": {
            "two_column_reading_order_accuracy": fixture_value(
                "two_column_born_digital", "reading_order_accuracy"
            ),
            "scanned_english_parse_success": fixture_value(
                "scanned_english", "parse_success"
            ),
            "scanned_chinese_parse_success": fixture_value(
                "scanned_chinese", "parse_success"
            ),
            "mixed_layout_table_retention": fixture_value(
                "mixed_layout_blocker", "table_retention"
            ),
            "simple_table_retention": fixture_value(
                "simple_table", "table_retention"
            ),
            "formula_retention": fixture_value("raster_formula", "formula_retention"),
            "repeated_header_footer_filter_rate": fixture_value(
                "repeated_header_footer", "header_footer_filter_rate"
            ),
        },
        "license_gate": license_gate,
    }


def select_candidate(aggregates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = {str(item.get("parser_id")): dict(item) for item in aggregates}
    baseline = by_id.get("baseline_native_tesseract_formula_region", {})
    baseline_hit3 = float(baseline.get("retrieval_hit_at_3") or 0)

    def eligible(item: Mapping[str, Any]) -> bool:
        return (
            item.get("parser_id") != "baseline_native_tesseract_formula_region"
            and item.get("license_gate") == "pass"
            and float(item.get("parse_success_rate") or 0) >= 0.95
            and float(item.get("reading_order_accuracy") or 0) >= 0.9
            and float(item.get("heading_definition_integrity") or 0) >= 0.9
            and float(item.get("bbox_provenance_completeness") or 0) >= 0.9
            and float(item.get("retrieval_hit_at_3") or 0) >= baseline_hit3
        )

    candidates = [dict(item) for item in aggregates if eligible(item)]
    candidates.sort(
        key=lambda item: (
            float(item.get("retrieval_hit_at_3") or 0),
            float(item.get("heading_definition_integrity") or 0),
            float(item.get("reading_order_accuracy") or 0),
            float(item.get("bbox_provenance_completeness") or 0),
            -float(item.get("median_runtime_ms") or math.inf),
        ),
        reverse=True,
    )
    selected = candidates[0] if candidates else None
    gates = dict((selected or {}).get("critical_fixture_gates") or {})
    recommended_scope: list[str] = []
    excluded_scope: list[str] = []
    composition_requirements = [
        "per_document_quality_routing",
        "current_native_parser_fallback",
    ]
    if selected:
        if bool(gates.get("scanned_english_parse_success")) and bool(
            gates.get("scanned_chinese_parse_success")
        ):
            recommended_scope.append("scanned_pdf")
        if float(gates.get("simple_table_retention") or 0) >= 1.0:
            recommended_scope.append("simple_table_pdf")
        if float(gates.get("two_column_reading_order_accuracy") or 0) < 0.9:
            excluded_scope.append("multi_column_pdf")
        if float(gates.get("mixed_layout_table_retention") or 0) < 1.0:
            excluded_scope.append("mixed_layout_table_pdf")
        if float(gates.get("formula_retention") or 0) < 1.0:
            excluded_scope.append("formula_pdf_without_existing_formula_region")
            composition_requirements.append("existing_formula_region")
    return {
        "selected_parser_id": selected.get("parser_id") if selected else None,
        "selected_role": (
            "conditional_complex_document_parser_candidate"
            if selected
            else "no_candidate_selected"
        ),
        "fallback_parser_id": "baseline_native_tesseract_formula_region",
        "simple_document_policy": "retain_current_native_parser",
        "recommended_scope": recommended_scope,
        "excluded_scope": excluded_scope,
        "composition_requirements": composition_requirements,
        # Task 14B selects an integration candidate only.  Production routing
        # remains unchanged until the next, separately verified adapter task.
        "production_adapter_authorized": False,
        "mineru_eligible": eligible(by_id.get("mineru", {})),
        "reason": (
            "Selected a conditional integration candidate; failed document-class gates remain excluded and production routing is unchanged."
            if selected
            else "No candidate passed all quality, provenance, retrieval and license gates."
        ),
    }


def sanitize_artifact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_artifact(child)
            for key, child in value.items()
            if str(key).casefold() not in BODY_KEYS
        }
    if isinstance(value, list):
        return [sanitize_artifact(child) for child in value]
    if isinstance(value, tuple):
        return [sanitize_artifact(child) for child in value]
    if isinstance(value, Path):
        return "<LOCAL_EVALUATION_PATH>"
    if isinstance(value, str):
        return SECRET_RE.sub("[REDACTED]", LOCAL_PATH_RE.sub("<LOCAL_EVALUATION_PATH>", value))
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sanitize_artifact(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_metric_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = (
        "parser_id",
        "fixture_id",
        "parse_success",
        "reading_order_accuracy",
        "heading_definition_integrity",
        "page_provenance_completeness",
        "block_provenance_completeness",
        "bbox_provenance_completeness",
        "table_retention",
        "formula_retention",
        "header_footer_filter_rate",
        "duplicate_block_count",
        "runtime_ms",
        "peak_rss_mb",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 14B controlled parser benchmark utilities")
    parser.add_argument("--validate-json", default="")
    args = parser.parse_args(argv)
    if args.validate_json:
        payload = json.loads(Path(args.validate_json).read_text(encoding="utf-8"))
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise SystemExit("invalid benchmark schema version")
        print(json.dumps({"valid": True, "schema_version": SCHEMA_VERSION}, sort_keys=True))
        return 0
    parser.error("one command is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
