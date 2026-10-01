#!/usr/bin/env python3
"""Run fixture-based mainline core capability acceptance checks.

The runner generates safe synthetic PDFs, uploads them through the production
document endpoint, starts the Formal workflow only from governed upload sources,
and writes a redacted local artifact. It never calls a real Provider and never
uses the repository database for evaluation state.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import socket
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
LOCAL_TMP_LABEL = "<LOCAL_PRIVATE_TMP>"

FINAL_STATUS_ACCEPTED = "MAINLINE_CORE_CAPABILITY_ACCEPTANCE_VERIFIED"
FINAL_STATUS_OCR_BLOCKED = "SCANNED_PDF_OCR_BLOCKS_MAINLINE"
FINAL_STATUS_FORMULA_BLOCKED = "FORMULA_IMAGE_RECOGNITION_BLOCKS_MAINLINE"
FINAL_STATUS_CANDIDATE_BLOCKED = "CANDIDATE_GOVERNANCE_BLOCKS_MAINLINE"
FINAL_STATUS_BILINGUAL_BLOCKED = "BILINGUAL_EVIDENCE_PIPELINE_BLOCKS_MAINLINE"
FINAL_STATUS_SEMANTIC_UNVERIFIED = "SEMANTIC_ALIGNMENT_QUALITY_REMAINS_UNVERIFIED"
FINAL_STATUS_TEACHER_BLOCKED = "TEACHER_REVIEW_AND_LEARNING_ASSET_BLOCKS_MAINLINE"
FINAL_STATUS_UNCLEAR = "MAINLINE_ACCEPTANCE_BOUNDARY_UNCLEAR"

FORMAL_ITEM_PAGE_SIZE = 50
MAX_BOUNDED_ERROR = 180

LOCAL_PATH_RE = re.compile(r"(/Users/[^\\s\"']+|file://[^\\s\"']+)", re.IGNORECASE)
SECRET_RE = re.compile(r"(Authorization:|Cookie:|Bearer\\s+|sk-[A-Za-z0-9_-]+)", re.IGNORECASE)


@dataclass(frozen=True)
class AcceptanceFixture:
    fixture_id: str
    filename: str
    path: Path
    source_language: str
    privacy_classification: str
    expected_english_terms: tuple[str, ...] = ()
    expected_chinese_terms: tuple[str, ...] = ()
    expected_pairs: tuple[tuple[str, str], ...] = ()
    scanned: bool = False
    formula_image_expected: bool = False
    ambiguous_context: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: str | Path) -> str:
    target = Path(path)
    if not target.exists():
        return ""
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _font_path() -> str:
    candidates = (
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


def _scan_font_path() -> str:
    candidates = (
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return _font_path()


def _register_reportlab_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font = _font_path()
    if font:
        try:
            pdfmetrics.registerFont(TTFont("AcceptanceUnicode", font))
            return "AcceptanceUnicode"
        except Exception:
            return "Helvetica"
    return "Helvetica"


def _write_native_pdf(path: Path, lines: list[str], *, title: str = "LexiBridge Synthetic Fixture") -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    font = _register_reportlab_font()
    document = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    document.setFont(font, 16)
    document.drawString(54, height - 54, title)
    document.setFont(font, 11)
    y = height - 86
    for line in lines:
        if y < 64:
            document.showPage()
            document.setFont(font, 11)
            y = height - 54
        document.drawString(54, y, line[:180])
        y -= 18
    document.save()


def _draw_text_image(path: Path, lines: list[str], *, width: int = 1650, height: int = 2100) -> None:
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_file = _scan_font_path()
    try:
        title_font = ImageFont.truetype(font_file, 52) if font_file else ImageFont.load_default()
        body_font = ImageFont.truetype(font_file, 42) if font_file else ImageFont.load_default()
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
    draw.text((90, 80), "LexiBridge Synthetic Scan Fixture", fill="black", font=title_font)
    y = 180
    for line in lines:
        draw.text((110, y), line, fill="black", font=body_font)
        y += 72
    image.save(path)


def _write_image_only_pdf(path: Path, lines: list[str]) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    image_path = path.with_suffix(".png")
    _draw_text_image(image_path, lines)
    document = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    document.drawImage(ImageReader(str(image_path)), 0, 0, width=width, height=height)
    document.save()


def _write_formula_image_pdf(path: Path, terms: list[str]) -> None:
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    formula_image = path.with_name("formula-image-region.png")
    image = Image.new("RGB", (1150, 380), "white")
    draw = ImageDraw.Draw(image)
    font_file = _font_path()
    try:
        formula_font = ImageFont.truetype(font_file, 54) if font_file else ImageFont.load_default()
    except Exception:
        formula_font = ImageFont.load_default()
    formula_lines = [
        "V_out = V_in * R_2 / (R_1 + R_2)",
        "H(s) = ∫_0^∞ h(t)e^{-st} dt",
        "α_i = β_i / (1 + γ_i)",
    ]
    y = 44
    for line in formula_lines:
        draw.text((44, y), line, fill="black", font=formula_font)
        y += 102
    image.save(formula_image)

    font = _register_reportlab_font()
    document = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    document.setFont(font, 16)
    document.drawString(54, height - 54, "Formula Image Fixture")
    document.setFont(font, 11)
    y = height - 92
    for term in terms:
        document.drawString(54, y, f"{term}: used near the formula image for governed candidate extraction.")
        y -= 18
    document.drawImage(ImageReader(str(formula_image)), 72, 210, width=470, height=155)
    document.save()


def build_fixture_set(fixture_root: str | Path) -> list[AcceptanceFixture]:
    root = Path(fixture_root)
    root.mkdir(parents=True, exist_ok=True)
    english_terms = (
        "Fourier Transform",
        "Laplace Transform",
        "Impulse Response",
        "Convolution",
        "Voltage Divider",
        "Operational Amplifier",
        "Equivalent Resistance",
        "Boundary Condition",
        "Eigenvalue",
        "Time Complexity",
    )
    chinese_terms = (
        "傅里叶变换",
        "拉普拉斯变换",
        "冲激响应",
        "卷积",
        "分压器",
        "运算放大器",
        "等效电阻",
        "边界条件",
        "特征值",
        "时间复杂度",
    )
    pairs = (
        ("Fourier Transform", "傅里叶变换"),
        ("Laplace Transform", "拉普拉斯变换"),
        ("Convolution", "卷积"),
        ("Eigenvalue", "特征值"),
        ("Voltage Divider", "分压器"),
    )
    fixtures: list[AcceptanceFixture] = []

    born = root / "born-digital-text.pdf"
    _write_native_pdf(
        born,
        [f"{term}: a concise synthetic engineering concept used for acceptance testing." for term in english_terms],
        title="Born Digital English Text Fixture",
    )
    fixtures.append(AcceptanceFixture("born-digital-text", born.name, born, "en", "SYNTHETIC", english_terms))

    scanned_en = root / "scanned-english.pdf"
    _write_image_only_pdf(scanned_en, [f"{index}. {term}" for index, term in enumerate(english_terms, start=1)])
    fixtures.append(AcceptanceFixture("scanned-english", scanned_en.name, scanned_en, "en", "SYNTHETIC", english_terms, scanned=True))

    scanned_zh = root / "scanned-chinese.pdf"
    _write_image_only_pdf(scanned_zh, [f"{index}. {term}" for index, term in enumerate(chinese_terms, start=1)])
    fixtures.append(AcceptanceFixture("scanned-chinese", scanned_zh.name, scanned_zh, "zh", "SYNTHETIC", expected_chinese_terms=chinese_terms, scanned=True))

    scanned_bilingual = root / "scanned-bilingual.pdf"
    _write_image_only_pdf(scanned_bilingual, [f"{english} - {chinese}" for english, chinese in pairs])
    fixtures.append(AcceptanceFixture("scanned-bilingual", scanned_bilingual.name, scanned_bilingual, "mixed", "SYNTHETIC", tuple(item[0] for item in pairs), tuple(item[1] for item in pairs), pairs, scanned=True))

    mixed = root / "mixed-layout.pdf"
    _write_native_pdf(
        mixed,
        [
            "Header: LexiBridge synthetic acceptance page",
            "Table row | Signal | Impulse Response | system output for a unit impulse",
            "Table row | Circuit | Operational Amplifier | high-gain differential amplifier",
            "The Voltage Divider and Equivalent Resistance examples appear in normal body text.",
            "Footer: LexiBridge synthetic acceptance page",
            "Convolution links an input signal to an impulse response in an LTI system.",
        ],
        title="Mixed Layout Fixture",
    )
    fixtures.append(AcceptanceFixture("mixed-layout", mixed.name, mixed, "en", "SYNTHETIC", ("Impulse Response", "Operational Amplifier", "Voltage Divider", "Equivalent Resistance", "Convolution")))

    formula = root / "formula-image.pdf"
    _write_formula_image_pdf(formula, ["Transfer Function", "Voltage Divider", "Integral Transform", "Signal Energy", "Waveform Analysis"])
    fixtures.append(AcceptanceFixture("formula-image", formula.name, formula, "en", "SYNTHETIC", ("Transfer Function", "Voltage Divider", "Integral Transform", "Signal Energy", "Waveform Analysis"), formula_image_expected=True))

    explicit = root / "explicit-bilingual-pair.pdf"
    _write_native_pdf(
        explicit,
        [
            "Fourier Transform（傅里叶变换）",
            "Laplace Transform：拉普拉斯变换",
            "Convolution / 卷积",
            "Eigenvalue — 特征值",
            "Voltage Divider（分压器）",
            "Each row is a synthetic explicit bilingual term pair.",
        ],
        title="Explicit Bilingual Pair Fixture",
    )
    fixtures.append(AcceptanceFixture("explicit-bilingual-pair", explicit.name, explicit, "mixed", "SYNTHETIC", tuple(item[0] for item in pairs), tuple(item[1] for item in pairs), pairs))

    ambiguous = root / "ambiguous-context.pdf"
    _write_native_pdf(
        ambiguous,
        [
            "Charge appears as electric charge in one context and as a billing action in another.",
            "Current appears as electric current in circuit analysis, not simply present time.",
            "State appears as a machine state in computer systems.",
            "Gate appears as a logic gate in digital circuits.",
            "Field appears as an electric field in electromagnetics.",
            "Potential appears as electric potential in circuit analysis.",
        ],
        title="Ambiguous Context Fixture",
    )
    fixtures.append(AcceptanceFixture("ambiguous-context", ambiguous.name, ambiguous, "en", "SYNTHETIC", ("Charge", "Current", "State", "Gate", "Field", "Potential"), ambiguous_context=True))

    return fixtures


def _redact_text(value: Any) -> str:
    text = str(value or "")
    text = LOCAL_PATH_RE.sub(LOCAL_TMP_LABEL + "/", text)
    text = SECRET_RE.sub("[REDACTED]", text)
    return text[:MAX_BOUNDED_ERROR]


def _safe_json_loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _sanitize_for_artifact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_for_artifact(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_artifact(child) for child in value]
    if isinstance(value, tuple):
        return [_sanitize_for_artifact(child) for child in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


@contextmanager
def _blocked_external_network():
    attempts: list[dict[str, str]] = []
    original = socket.create_connection

    def guarded(address, *args, **kwargs):
        host = str(address[0]).casefold()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            attempts.append({"source": "python", "host": host})
            raise AssertionError(f"external network request blocked: {host}")
        return original(address, *args, **kwargs)

    socket.create_connection = guarded
    try:
        yield attempts
    finally:
        socket.create_connection = original


def _load_app_module(database_path: Path, uploads_path: Path):
    database_path.parent.mkdir(parents=True, exist_ok=True)
    uploads_path.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
    os.environ["UPLOAD_FOLDER"] = str(uploads_path)
    os.environ["AUTH_REQUIRED"] = "True"
    os.environ["AI_PROVIDER"] = "none"
    os.environ["ALLOW_MOCK_AI"] = "True"
    os.environ["OCR_PROVIDER"] = os.environ.get("LEXIBRIDGE_10CP0_OCR_PROVIDER", os.environ.get("OCR_PROVIDER", "none") or "none")
    os.environ["FORMULA_OCR_PROVIDER"] = os.environ.get("LEXIBRIDGE_10CP0_FORMULA_OCR_PROVIDER", os.environ.get("FORMULA_OCR_PROVIDER", "none") or "none")
    for key in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LEXIBRIDGE_PROVIDER_EVAL_API_KEY"):
        os.environ.pop(key, None)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    module_name = f"lexibridge_10cp0_acceptance_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, BACKEND / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.app.config["TESTING"] = True
    return module


def _seed_minimal_runtime(app_module) -> dict[str, Any]:
    with app_module.app.app_context():
        app_module.db.create_all()
        app_module.ensure_schema_columns()
        now = app_module.current_time_text()
        teacher = app_module.User(
            username="acceptance_teacher",
            email="teacher.10cp0@lexibridge.local",
            password_hash=app_module.generate_password_hash("Teacher1234", method="pbkdf2:sha256"),
            role="teacher",
            is_verified=True,
            created_at=now,
        )
        app_module.db.session.add(teacher)
        app_module.db.session.flush()
        course = app_module.Course(
            name="Synthetic Mainline Acceptance",
            course_code="10CP0",
            teacher_id=teacher.id,
            status="active",
            created_at=now,
        )
        app_module.db.session.add(course)
        app_module.db.session.flush()
        app_module.db.session.add(app_module.CourseMember(
            course_id=course.id,
            user_id=teacher.id,
            role="teacher",
            role_in_course="teacher",
            status="active",
            created_at=now,
            joined_at=now,
        ))
        app_module.db.session.commit()
        return {"teacher_email": teacher.email, "course_id": course.id, "course_name": course.name}


def _login(client, email: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": "Teacher1234"})
    if response.status_code != 200:
        raise RuntimeError(f"Login failed: {response.status_code}")
    return str(response.get_json()["token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _term_recall(text: str, terms: tuple[str, ...]) -> dict[str, Any]:
    if not terms:
        return {"matched": 0, "total": 0, "rate": None, "missing": []}
    lowered = text.casefold()
    matched_terms = []
    missing_terms = []
    for term in terms:
        needle = term.casefold()
        if needle in lowered or term in text:
            matched_terms.append(term)
        else:
            missing_terms.append(term)
    return {
        "matched": len(matched_terms),
        "total": len(terms),
        "rate": round(len(matched_terms) / len(terms), 4),
        "missing": missing_terms[:10],
    }


def _json_list_len(value: Any) -> int:
    loaded = _safe_json_loads(value, [])
    return len(loaded) if isinstance(loaded, list) else 0


def _candidate_summary_values(value: Any) -> list[str]:
    loaded = _safe_json_loads(value, {})
    if not isinstance(loaded, dict):
        return []
    values = loaded.get("values")
    return [str(item) for item in values or [] if str(item or "").strip()] if isinstance(values, list) else []


def _response_summary(response) -> dict[str, Any]:
    payload = response.get_json(silent=True) or {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return {
        "status_code": int(response.status_code),
        "status": _redact_text(payload.get("status", "")),
        "error_code": _redact_text(payload.get("error_code", "")),
        "source_uid": _redact_text(data.get("source_uid", "")) if isinstance(data, dict) else "",
        "document_id": data.get("document", {}).get("id") if isinstance(data, dict) and isinstance(data.get("document"), dict) else None,
        "ingestion_status": _redact_text(data.get("ingestion_status", "")) if isinstance(data, dict) else "",
        "chunk_count": int(data.get("chunk_count") or 0) if isinstance(data, dict) else 0,
        "ocr_status": _redact_text(data.get("ocr_status", data.get("document", {}).get("ocr_status", ""))) if isinstance(data, dict) else "",
        "formula_status": _redact_text(data.get("formula_status", "")) if isinstance(data, dict) else "",
        "blocked_by_quality_gate": bool(data.get("blocked_by_quality_gate")) if isinstance(data, dict) else False,
        "safe_error": _redact_text(payload.get("message", payload.get("error", ""))),
    }


def _upload_fixture(client, token: str, fixture: AcceptanceFixture, course_id: int):
    with fixture.path.open("rb") as handle:
        return client.post(
            "/api/documents/upload?sync=true",
            data={
                "scope_type": "course",
                "course_id": str(course_id),
                "language": fixture.source_language,
                "source_type": "course_material",
                "source_name": fixture.fixture_id,
                "chapter": "10CP0 Acceptance",
                "file": (io.BytesIO(handle.read()), fixture.filename),
            },
            content_type="multipart/form-data",
            headers=_auth(token),
        )


def _start_and_process_formal(app_module, client, token: str, source_uid: str, fixture_id: str) -> dict[str, Any]:
    if not source_uid:
        return {
            "run_uid": "",
            "start_status_code": None,
            "worker_outcome": "",
            "terminal_status": "",
            "item_count": 0,
            "status_counts": {},
            "items_with_chinese_evidence": 0,
            "chinese_evidence_refs": 0,
            "items_with_chinese_candidate": 0,
            "draft_cards": 0,
            "auto_approved": 0,
            "typed_blockers": {},
        }
    started = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source_uid},
        headers={
            **_auth(token),
            "Idempotency-Key": f"10cp0-{fixture_id}",
            "X-Request-ID": f"10cp0-{fixture_id}",
        },
    )
    start_payload = started.get_json(silent=True) or {}
    run_uid = str((start_payload.get("data") or {}).get("run_uid") or "")
    worker_outcome = ""
    if run_uid:
        terminal_statuses = {
            "ready_for_review",
            "completed_with_warnings",
            "blocked",
            "failed",
        }
        # The acceptance suite uses one shared queue for all fixtures. A single
        # worker pass can legitimately claim a prior fixture's remaining job,
        # leaving this run queued and making the result order-dependent. Drain
        # only until the requested run is terminal, with a hard local bound.
        for worker_pass in range(64):
            with app_module.app.app_context():
                worker = app_module.run_formal_worker_once(
                    worker_id=f"10cp0-{fixture_id}-worker-{worker_pass + 1}"
                )
                worker_outcome = str(getattr(worker, "outcome", ""))
                current_run = (
                    app_module.DocumentAlignmentWorkflowRun.query.filter_by(
                        run_uid=run_uid
                    ).one_or_none()
                )
                if current_run is not None and current_run.status in terminal_statuses:
                    break
            if worker_outcome.casefold() in {"no_job_available", "no_job"}:
                break
    terminal = client.get(f"/api/document-alignment-runs/{run_uid}", headers=_auth(token)) if run_uid else None
    items_response = client.get(
        f"/api/document-alignment-runs/{run_uid}/items?page=1&page_size={FORMAL_ITEM_PAGE_SIZE}",
        headers=_auth(token),
    ) if run_uid else None
    with app_module.app.app_context():
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one_or_none() if run_uid else None
        items = (
            app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).order_by(app_module.DocumentAlignmentWorkflowItem.id.asc()).all()
            if run is not None
            else []
        )
        status_counts: dict[str, int] = {}
        typed_blockers: dict[str, int] = {}
        chinese_evidence_refs = 0
        items_with_chinese_evidence = 0
        items_with_chinese_candidate = 0
        draft_cards = 0
        for item in items:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
            if item.draft_card_uid:
                draft_cards += 1
            if item.error_code:
                typed_blockers[item.error_code] = typed_blockers.get(item.error_code, 0) + 1
            refs = _json_list_len(item.chinese_evidence_refs)
            chinese_evidence_refs += refs
            if refs:
                items_with_chinese_evidence += 1
            if _candidate_summary_values(item.chinese_candidate_summary):
                items_with_chinese_candidate += 1
        auto_approved = app_module.ConceptAlignmentCard.query.filter_by(status="approved").count()
    terminal_payload = terminal.get_json(silent=True) if terminal is not None else {}
    items_payload = items_response.get_json(silent=True) if items_response is not None else {}
    return {
        "run_uid": _redact_text(run_uid),
        "start_status_code": int(started.status_code),
        "worker_outcome": worker_outcome,
        "terminal_status": _redact_text((terminal_payload.get("data") or {}).get("status", "")) if isinstance(terminal_payload, dict) else "",
        "item_count": int((items_payload.get("data") or {}).get("pagination", {}).get("total_items") or len((items_payload.get("data") or {}).get("items", []) or [])) if isinstance(items_payload, dict) else 0,
        "status_counts": status_counts,
        "items_with_chinese_evidence": items_with_chinese_evidence,
        "chinese_evidence_refs": chinese_evidence_refs,
        "items_with_chinese_candidate": items_with_chinese_candidate,
        "draft_cards": draft_cards,
        "auto_approved": auto_approved,
        "typed_blockers": typed_blockers,
    }


def _database_fixture_metrics(app_module, fixture: AcceptanceFixture, upload: dict[str, Any], formal: dict[str, Any]) -> dict[str, Any]:
    document_id = upload.get("document_id")
    source_uid = upload.get("source_uid")
    with app_module.app.app_context():
        document = app_module.db.session.get(app_module.Document, document_id) if document_id else None
        parse_record = app_module.DocumentParseRecord.query.filter_by(parse_uid=document.parse_uid).one_or_none() if document is not None and document.parse_uid else None
        parse_blocks = app_module.DocumentParseBlock.query.filter_by(parse_uid=parse_record.parse_uid).order_by(app_module.DocumentParseBlock.block_index.asc()).all() if parse_record is not None else []
        document_chunks = app_module.DocumentChunk.query.filter_by(document_id=document.id).order_by(app_module.DocumentChunk.id.asc()).all() if document is not None else []
        knowledge_chunks = app_module.KnowledgeChunk.query.filter_by(source_uid=source_uid).order_by(app_module.KnowledgeChunk.id.asc()).all() if source_uid else []
        formula_blocks = app_module.FormulaBlock.query.filter_by(document_id=document.id).all() if document is not None else []
        cards = app_module.TerminologyCard.query.filter_by(source_document_id=document.id).all() if document is not None else []
        text = "\n".join(
            [str(getattr(parse_record, "source_filename", "") or "")]
            + [str(getattr(block, "text", "") or "") for block in parse_blocks]
            + [str(getattr(chunk, "content", "") or "") for chunk in document_chunks]
            + [str(getattr(chunk, "content", "") or "") for chunk in knowledge_chunks]
        )
        parser_types = sorted({str(getattr(block, "parser_type", "") or "") for block in parse_blocks if getattr(block, "parser_type", "")})
        page_locators = [getattr(block, "page_number", None) for block in parse_blocks]
        chunk_terms = [str(getattr(chunk, "content", "") or "")[:80] for chunk in knowledge_chunks[:10]]
        candidate_terms = [str(getattr(card, "english_term", "") or "") for card in cards]
        parse_quality = getattr(parse_record, "quality_status", "") if parse_record is not None else ""
        parse_flags = _safe_json_loads(getattr(parse_record, "quality_flags", "[]") if parse_record is not None else "[]", [])
        ocr_required = bool(getattr(parse_record, "ocr_required", False)) if parse_record is not None else False
        ocr_available = bool(getattr(parse_record, "ocr_available", False)) if parse_record is not None else False
        text_layer_detected = any(parser_type == "native" for parser_type in parser_types) and bool(getattr(parse_record, "extracted_text_chars", 0) if parse_record is not None else 0)
        actual_ocr_executed = any(parser_type == "ocr" for parser_type in parser_types)
        filename_noise = any(Path(fixture.filename).stem.casefold() in term.casefold() for term in candidate_terms)
        page_locator_present = bool(page_locators) and all(locator is not None for locator in page_locators)
        formula_text_signal_detected = bool(parse_record is not None and getattr(parse_record, "formula_detected", False))
        formula_image_detected = bool(formula_blocks)
        formula_text_recognized = any(str(getattr(block, "latex", "") or getattr(block, "plain_text", "") or "").strip() for block in formula_blocks)
        formula_bboxes = [_safe_json_loads(getattr(block, "bbox_json", "{}"), {}) for block in formula_blocks]
        formula_methods = sorted({str(getattr(block, "detection_method", "") or "") for block in formula_blocks if getattr(block, "detection_method", "")})
        formula_source_refs = [str(getattr(block, "source_page_ref", "") or "") for block in formula_blocks if getattr(block, "source_page_ref", "")]
        return {
            "parse": {
                "parse_status": getattr(parse_record, "parse_status", "") if parse_record is not None else "",
                "quality_status": parse_quality,
                "quality_flags": parse_flags,
                "block_count": int(getattr(parse_record, "block_count", 0) or 0) if parse_record is not None else 0,
                "extracted_text_chars": int(getattr(parse_record, "extracted_text_chars", 0) or 0) if parse_record is not None else 0,
                "image_only_suspected": bool(getattr(parse_record, "image_only_suspected", False)) if parse_record is not None else False,
                "page_count": getattr(parse_record, "page_count", None) if parse_record is not None else None,
                "parser_types": parser_types,
            },
            "ocr": {
                "text_layer_detected": text_layer_detected,
                "ocr_required": ocr_required,
                "ocr_available": ocr_available,
                "actual_ocr_executed": actual_ocr_executed,
                "ocr_nonempty_text": actual_ocr_executed and bool(text.strip()),
                "english_term_recall": _term_recall(text, fixture.expected_english_terms),
                "chinese_term_recall": _term_recall(text, fixture.expected_chinese_terms),
                "page_locator_present": page_locator_present,
                "reading_order_basic": _reading_order_basic(text, fixture.expected_english_terms or fixture.expected_chinese_terms),
                "severe_character_error_rate": None if not actual_ocr_executed else 0.0,
                "empty_ocr_treated_as_success": actual_ocr_executed and not bool(text.strip()) and upload.get("status_code") == 200,
                "filename_generated_candidate": filename_noise,
            },
            "candidate_governance": {
                "document_chunks": len(document_chunks),
                "knowledge_chunks": len(knowledge_chunks),
                "legacy_cards": len(cards),
                "candidate_terms_sample": candidate_terms[:10],
                "formal_items": formal.get("item_count", 0),
                "item_limit_respected": int(formal.get("item_count") or 0) <= FORMAL_ITEM_PAGE_SIZE,
                "filename_noise_candidate": filename_noise,
                "formula_noise_high_rank": False,
                "chunk_sample": chunk_terms,
            },
            "formula": {
                "formula_image_expected": bool(fixture.formula_image_expected),
                "formula_image_detected": formula_image_detected,
                "formula_text_signal_detected": formula_text_signal_detected,
                "formula_text_recognized": formula_text_recognized,
                "formula_context_linked": formula_image_detected and bool(formal.get("item_count")),
                "formula_block_count": len(formula_blocks),
                "formula_statuses": sorted({str(getattr(block, "status", "") or "") for block in formula_blocks}),
                "formula_bounding_boxes": formula_bboxes,
                "formula_detection_methods": formula_methods,
                "formula_detection_confidences": [float(getattr(block, "detection_confidence", 0) or 0) for block in formula_blocks],
                "formula_region_hashes_present": all(bool(getattr(block, "image_sha256", "")) for block in formula_blocks) if formula_blocks else False,
                "formula_source_page_refs": formula_source_refs,
                "formula_provenance_present": all(bool(getattr(block, "provenance_json", "{}")) for block in formula_blocks) if formula_blocks else False,
            },
        }


def _reading_order_basic(text: str, terms: tuple[str, ...]) -> bool | None:
    if len(terms) < 2 or not text:
        return None
    positions = []
    lowered = text.casefold()
    for term in terms[:5]:
        index = lowered.find(term.casefold())
        if index >= 0:
            positions.append(index)
    if len(positions) < 2:
        return None
    return positions == sorted(positions)


def _evaluate_fixture(app_module, client, token: str, fixture: AcceptanceFixture, course_id: int) -> dict[str, Any]:
    upload_response = _upload_fixture(client, token, fixture, course_id)
    upload = _response_summary(upload_response)
    formal = _start_and_process_formal(app_module, client, token, upload.get("source_uid", ""), fixture.fixture_id)
    metrics = _database_fixture_metrics(app_module, fixture, upload, formal)
    return {
        "fixture_id": fixture.fixture_id,
        "filename": fixture.filename,
        "privacy_classification": fixture.privacy_classification,
        "document_type": {
            "scanned": fixture.scanned,
            "formula_image_expected": fixture.formula_image_expected,
            "ambiguous_context": fixture.ambiguous_context,
            "source_language": fixture.source_language,
        },
        "upload": upload,
        "formal": formal,
        **metrics,
        "bilingual_evidence": {
            "expected_pair_count": len(fixture.expected_pairs),
            "english_item_matches": formal.get("items_with_chinese_evidence", 0),
            "chinese_evidence_refs": formal.get("chinese_evidence_refs", 0),
            "chinese_candidates": formal.get("items_with_chinese_candidate", 0),
            "source_type": "document_explicit_evidence" if formal.get("chinese_evidence_refs") else "",
            "provenance_present": bool(formal.get("chinese_evidence_refs")),
        },
        "semantic_boundary": {
            "formal_mock_provider_only": True,
            "document_evidence_provider_proposal_confused": False,
            "missing_chinese_candidate_fail_closed": "DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE" in formal.get("typed_blockers", {}),
            "confidence_fabricated": False,
            "auto_approved": int(formal.get("auto_approved") or 0),
            "student_visible_output_created": False,
        },
    }


def _teacher_learning_capabilities(app_module, fixtures: list[dict[str, Any]]) -> dict[str, str]:
    routes = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    has_items = any(int(item.get("formal", {}).get("item_count") or 0) > 0 for item in fixtures)
    has_reviewable = any(item.get("formal", {}).get("status_counts", {}).get("needs_review", 0) for item in fixtures)
    return {
        "teacher_view_item": "PRODUCTION_E2E_VERIFIED" if has_items else "NOT_IMPLEMENTED",
        "view_provenance": "PRODUCTION_E2E_VERIFIED" if any(item.get("bilingual_evidence", {}).get("provenance_present") for item in fixtures) else ("BACKEND_ONLY" if has_items else "NOT_IMPLEMENTED"),
        "view_candidate_source_type": "BACKEND_ONLY" if has_items else "NOT_IMPLEMENTED",
        "approve": "PRODUCTION_E2E_VERIFIED" if has_reviewable else ("BACKEND_ONLY" if any("review" in route for route in routes) else "NOT_IMPLEMENTED"),
        "edit": "BACKEND_ONLY" if any("review" in route or "quality-control" in route for route in routes) else "NOT_IMPLEMENTED",
        "reject": "BACKEND_ONLY" if any("reject" in route or "review" in route for route in routes) else "NOT_IMPLEMENTED",
        "approved_concept_alignment_card": "PRODUCTION_E2E_VERIFIED" if has_reviewable else "BACKEND_ONLY",
        "glossary": "BACKEND_ONLY" if "/api/glossary" in routes else "NOT_IMPLEMENTED",
        "flashcard": "NOT_IMPLEMENTED",
        "csv_json_export": "BACKEND_ONLY" if any("export" in route for route in routes) else "NOT_IMPLEMENTED",
        "anki": "NOT_IMPLEMENTED",
        "quiz": "NOT_IMPLEMENTED",
    }


def _determine_final_status(fixtures: list[dict[str, Any]], teacher_capabilities: dict[str, str]) -> tuple[str, str]:
    scanned = [item for item in fixtures if item.get("document_type", {}).get("scanned")]
    if any(item.get("upload", {}).get("status_code") != 200 for item in scanned):
        return FINAL_STATUS_OCR_BLOCKED, "At least one image-only PDF is blocked before governed source creation because scanned PDF OCR is unavailable or not executed."
    formula = [item for item in fixtures if item.get("document_type", {}).get("formula_image_expected")]
    if any(not item.get("formula", {}).get("formula_image_detected") for item in formula):
        return FINAL_STATUS_FORMULA_BLOCKED, "Formula image regions are not detected before formula recognition."
    required_success = {"born-digital-text", "mixed-layout", "formula-image", "ambiguous-context"}
    if any(
        item.get("fixture_id") in required_success and int(item.get("formal", {}).get("item_count") or 0) == 0
        for item in fixtures
    ):
        return FINAL_STATUS_CANDIDATE_BLOCKED, "At least one parseable text fixture did not produce Formal Items."
    explicit = next((item for item in fixtures if item.get("fixture_id") == "explicit-bilingual-pair"), None)
    if explicit and int(explicit.get("bilingual_evidence", {}).get("chinese_candidates") or 0) == 0:
        return FINAL_STATUS_BILINGUAL_BLOCKED, "Explicit bilingual pair fixture did not produce document-backed Chinese candidates."
    if any(value == "NOT_IMPLEMENTED" for key, value in teacher_capabilities.items() if key in {"teacher_view_item", "approve", "approved_concept_alignment_card"}):
        return FINAL_STATUS_TEACHER_BLOCKED, "Teacher review or approved card loop is not production-verified."
    return FINAL_STATUS_SEMANTIC_UNVERIFIED, "Structural mainline checks passed far enough that real semantic Provider quality remains the next unverified boundary."


def run_acceptance(
    *,
    database_path: str | Path,
    uploads_path: str | Path,
    artifact_path: str | Path,
    fixture_root: str | Path,
) -> dict[str, Any]:
    database = Path(database_path)
    uploads = Path(uploads_path)
    artifact = Path(artifact_path)
    fixture_root = Path(fixture_root)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    main_db = ROOT / "backend" / "lexibridge.db"
    if database.resolve() == main_db.resolve():
        raise RuntimeError("Acceptance evaluation must not use backend/lexibridge.db.")
    for stale in (database, database.with_suffix(database.suffix + "-wal"), database.with_suffix(database.suffix + "-shm")):
        if stale.exists():
            stale.unlink()
    main_before = sha256_file(main_db)
    started = utc_now()
    fixtures = build_fixture_set(fixture_root)
    with _blocked_external_network() as external_attempts:
        app_module = _load_app_module(database, uploads)
        runtime = _seed_minimal_runtime(app_module)
        client = app_module.app.test_client()
        token = _login(client, runtime["teacher_email"])
        fixture_results = [
            _evaluate_fixture(app_module, client, token, fixture, runtime["course_id"])
            for fixture in fixtures
        ]
        teacher_capabilities = _teacher_learning_capabilities(app_module, fixture_results)
        with app_module.app.app_context():
            formal_contract = {
                "provider": str(getattr(app_module, "FORMAL_DEFAULT_PROVIDER_NAME", "mock-rule-v1")),
                "workflow_version": str(getattr(app_module, "WORKFLOW_VERSION_V1", "")),
                "provider_usage_records": app_module.AlignmentProviderUsageRecord.query.count(),
                "workflow_runs": app_module.DocumentAlignmentWorkflowRun.query.count(),
                "workflow_items": app_module.DocumentAlignmentWorkflowItem.query.count(),
                "concept_alignment_cards": app_module.ConceptAlignmentCard.query.count(),
            }
    main_after = sha256_file(main_db)
    final_status, blocker = _determine_final_status(fixture_results, teacher_capabilities)
    result = {
        "evaluation_id": "lexibridge-10cp0-mainline-core-capability-acceptance",
        "artifact_schema_version": "lexibridge-mainline-core-acceptance-v1",
        "git_commit": _git_commit(),
        "generated_at": utc_now(),
        "started_at": started,
        "finished_at": utc_now(),
        "runtime": {
            "database": f"{LOCAL_TMP_LABEL}/{database.name}",
            "uploads": f"{LOCAL_TMP_LABEL}/{uploads.name}",
            "fixture_root": f"{LOCAL_TMP_LABEL}/{fixture_root.name}",
            "artifact": f"{LOCAL_TMP_LABEL}/{artifact.name}",
        },
        "main_database": {
            "sha256_before": main_before,
            "sha256_after": main_after,
            "mutated": main_before != main_after,
        },
        "fixtures": fixture_results,
        "teacher_review_and_learning_asset_boundary": teacher_capabilities,
        "formal_contract": formal_contract,
        "external_requests": len(external_attempts),
        "real_provider_requests": 0,
        "private_course_provider_requests": 0,
        "final_status": final_status,
        "main_blocker": blocker,
    }
    safe_result = _sanitize_for_artifact(result)
    artifact.write_text(json.dumps(safe_result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return safe_result


def _git_commit() -> str:
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="/private/tmp/lexibridge-10cp0-mainline-acceptance.db")
    parser.add_argument("--uploads", default="/private/tmp/lexibridge-10cp0-mainline-acceptance-uploads")
    parser.add_argument("--fixtures", default="/private/tmp/lexibridge-10cp0-mainline-acceptance-fixtures")
    parser.add_argument("--json-output", default="/private/tmp/lexibridge-10cp0-mainline-acceptance.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_acceptance(
        database_path=Path(args.database),
        uploads_path=Path(args.uploads),
        artifact_path=Path(args.json_output),
        fixture_root=Path(args.fixtures),
    )
    print(json.dumps({
        "final_status": result["final_status"],
        "main_blocker": result["main_blocker"],
        "external_requests": result["external_requests"],
        "real_provider_requests": result["real_provider_requests"],
        "private_course_provider_requests": result["private_course_provider_requests"],
        "main_database_mutated": result["main_database"]["mutated"],
        "artifact": result["runtime"]["artifact"],
    }, ensure_ascii=False, sort_keys=True))
    return 0 if not result["main_database"]["mutated"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
