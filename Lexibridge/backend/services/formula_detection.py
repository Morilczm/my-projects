from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from typing import Any


STRONG_FORMULA_SYMBOLS = (
    "∫", "∑", "√", "∞", "≤", "≥", "≠", "≈", "∂",
)
LEGACY_FORMULA_SYMBOLS = (
    "∫", "∑", "√", "∞", "≤", "≥", "≠", "≈", "θ", "λ", "μ", "σ", "ω",
    "π", "α", "β", "γ", "Δ", "∂", "^", "_", "=", "+", "-", "/", "(", ")",
    "[", "]",
)
LEGACY_FORMULA_WORDS = {
    "frac", "sqrt", "int", "sum", "lim", "sin", "cos", "tan", "log", "ln",
    "exp", "theta", "lambda", "omega", "alpha", "beta", "gamma", "sigma",
    "pi", "mu", "delta",
}

# Page/slide markers are parser provenance, not source mathematics.  The old
# detector treated the brackets in ``[Page 1]`` as a formula signal, which
# marked every otherwise clean PDF as requiring formula OCR.
_PARSER_LOCATION_LINE = re.compile(
    r"^\s*\[(?:page|slide)\s+\d+\]\s*$", re.IGNORECASE | re.MULTILINE
)
_EQUATION_PATTERN = re.compile(
    r"(?:^|[\s:;])"
    r"(?:[A-Za-zΑ-ω]\w*|\d+(?:\.\d+)?)"
    r"\s*(?:=|≤|≥|≠|≈)\s*"
    r"(?:[A-Za-zΑ-ω]\w*|\d+(?:\.\d+)?|[-+]?\d)"
)
_POWER_OR_SUBSCRIPT_PATTERN = re.compile(
    r"\b[A-Za-zΑ-ω]\w*\s*[\^_]\s*(?:\{?[-+]?\d+\}?|[A-Za-zΑ-ω]\w*)"
)
_MATH_FUNCTION_PATTERN = re.compile(
    r"\b(?:frac|sqrt|int|sum|lim|sin|cos|tan|log|ln|exp)\s*(?:\{|\()",
    re.IGNORECASE,
)


def _without_parser_location_lines(text: str) -> str:
    return _PARSER_LOCATION_LINE.sub("", str(text or ""))


def contains_formula_text(text):
    """Preserve the governed legacy detector for non-Personal workflows."""
    text = _without_parser_location_lines(text)
    if any(symbol in text for symbol in LEGACY_FORMULA_SYMBOLS):
        return True
    tokens = re.findall(r"[A-Za-z]+", text.lower())
    return any(token in LEGACY_FORMULA_WORDS for token in tokens)


def contains_substantive_formula_text(text):
    """Return true only for substantive mathematical notation.

    Punctuation, unit abbreviations such as ``(C)``/``N/C``, page markers,
    and prose hyphens are not formula regions.  Treating any slash,
    parenthesis, or dash as mathematics made clean course PDFs require formula
    OCR even when the layout detector found zero formula blocks.
    """
    text = _without_parser_location_lines(text)
    if any(symbol in text for symbol in STRONG_FORMULA_SYMBOLS):
        return True
    if _EQUATION_PATTERN.search(text):
        return True
    if _POWER_OR_SUBSCRIPT_PATTERN.search(text):
        return True
    if _MATH_FUNCTION_PATTERN.search(text):
        return True
    return False


@dataclass(frozen=True)
class FormulaRecognitionResult:
    status: str
    latex_candidate: str = ""
    mathml_candidate: str = ""
    plain_text: str = ""
    provider_id: str = "none"
    model_id: str = "none"
    confidence: float | None = None
    abstention_reason: str = ""
    safe_error: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    cost_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "FORMULA_RECOGNIZED" and bool((self.latex_candidate or self.mathml_candidate).strip())


@dataclass(frozen=True)
class FormulaRegion:
    formula_region_uid: str
    source_uid: str = ""
    document_uid: str = ""
    page_number: int | None = None
    bounding_box: dict[str, float] = field(default_factory=dict)
    region_image_hash: str = ""
    detection_method: str = ""
    detection_confidence: float = 0.0
    surrounding_text_refs: list[str] = field(default_factory=list)
    source_page_ref: str = ""
    recognizer_status: str = "FORMULA_RECOGNIZER_UNAVAILABLE"
    recognizer_provider: str = "none"
    recognizer_model: str = "none"
    recognition_confidence: float | None = None
    latex_candidate: str = ""
    mathml_candidate: str = ""
    abstention_reason: str = "Formula recognizer is not configured."
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "formula_region_uid": self.formula_region_uid,
            "source_uid": self.source_uid,
            "document_uid": self.document_uid,
            "page_number": self.page_number,
            "bounding_box": dict(self.bounding_box or {}),
            "region_image_hash": self.region_image_hash,
            "detection_method": self.detection_method,
            "detection_confidence": self.detection_confidence,
            "surrounding_text_refs": list(self.surrounding_text_refs or []),
            "source_page_ref": self.source_page_ref,
            "recognizer_status": self.recognizer_status,
            "recognizer_provider": self.recognizer_provider,
            "recognizer_model": self.recognizer_model,
            "recognition_confidence": self.recognition_confidence,
            "latex_candidate": self.latex_candidate,
            "mathml_candidate": self.mathml_candidate,
            "abstention_reason": self.abstention_reason,
            "provenance": dict(self.provenance or {}),
            "created_at": self.created_at,
        }


class FormulaRecognizer:
    provider_id = "none"
    model_id = "none"

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "model_id": self.model_id, "ready": False}

    def recognize(self, region: FormulaRegion) -> FormulaRecognitionResult:
        return FormulaRecognitionResult(
            status="FORMULA_RECOGNIZER_UNAVAILABLE",
            provider_id=self.provider_id,
            model_id=self.model_id,
            abstention_reason="Formula recognizer is not configured.",
            provenance={"formula_region_uid": region.formula_region_uid},
        )


class UnavailableFormulaRecognizer(FormulaRecognizer):
    provider_id = "none"
    model_id = "none"


class DeterministicTestFormulaRecognizer(FormulaRecognizer):
    provider_id = "deterministic-test-fake"
    model_id = "formula-test-v1"

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = dict(responses or {})

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "model_id": self.model_id, "ready": True, "test_only": True}

    def recognize(self, region: FormulaRegion) -> FormulaRecognitionResult:
        response = self.responses.get(region.formula_region_uid, "")
        if response == "__TIMEOUT__":
            return FormulaRecognitionResult(
                status="FORMULA_RECOGNIZER_TIMEOUT",
                provider_id=self.provider_id,
                model_id=self.model_id,
                abstention_reason="Deterministic test recognizer timeout.",
            )
        if not isinstance(response, str):
            return FormulaRecognitionResult(
                status="FORMULA_RECOGNIZER_MALFORMED_RESULT",
                provider_id=self.provider_id,
                model_id=self.model_id,
                safe_error="Malformed deterministic recognizer response.",
            )
        if not response.strip():
            return FormulaRecognitionResult(
                status="FORMULA_RECOGNIZER_UNAVAILABLE",
                provider_id=self.provider_id,
                model_id=self.model_id,
                abstention_reason="No deterministic test fake response was configured.",
            )
        return FormulaRecognitionResult(
            status="FORMULA_RECOGNIZED_BY_TEST_FAKE",
            latex_candidate=response.strip(),
            plain_text=response.strip(),
            provider_id=self.provider_id,
            model_id=self.model_id,
            confidence=1.0,
            provenance={"formula_region_uid": region.formula_region_uid, "test_only": True},
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bbox_dict(bbox: Any) -> dict[str, float]:
    try:
        x0, y0, x1, y1 = [float(value) for value in bbox]
    except Exception:
        return {}
    return {
        "x": round(x0, 2),
        "y": round(y0, 2),
        "width": round(max(0.0, x1 - x0), 2),
        "height": round(max(0.0, y1 - y0), 2),
    }


def _bbox_area(box: dict[str, float]) -> float:
    return float(box.get("width", 0) or 0) * float(box.get("height", 0) or 0)


def _is_full_page_image(box: dict[str, float], page_rect: Any) -> bool:
    page_area = max(1.0, float(page_rect.width) * float(page_rect.height))
    return _bbox_area(box) / page_area >= 0.70


def _image_component_metrics(image_bytes: bytes) -> dict[str, Any]:
    try:
        from PIL import Image
    except Exception:
        return {"component_count": 0, "small_component_count": 0, "large_component_count": 0}
    try:
        image = Image.open(BytesIO(image_bytes)).convert("L")
    except Exception:
        return {"component_count": 0, "small_component_count": 0, "large_component_count": 0}
    if image.width > 360:
        ratio = 360 / max(1, image.width)
        image = image.resize((360, max(1, int(image.height * ratio))))
    width, height = image.size
    dark: set[tuple[int, int]] = set()
    for y in range(height):
        for x in range(width):
            if image.getpixel((x, y)) < 180:
                dark.add((x, y))
    seen: set[tuple[int, int]] = set()
    component_count = 0
    small_component_count = 0
    large_component_count = 0
    for point in list(dark):
        if point in seen:
            continue
        component_count += 1
        queue = [point]
        seen.add(point)
        xs: list[int] = []
        ys: list[int] = []
        for x, y in queue:
            xs.append(x)
            ys.append(y)
            for nx in (x - 1, x, x + 1):
                for ny in (y - 1, y, y + 1):
                    if (nx, ny) in dark and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        queue.append((nx, ny))
        size = len(queue)
        component_width = max(xs) - min(xs) + 1
        component_height = max(ys) - min(ys) + 1
        if 2 <= size <= 600 and component_width <= 80 and component_height <= 60:
            small_component_count += 1
        if size > 1200 or component_width > 160 or component_height > 100:
            large_component_count += 1
    return {
        "component_count": component_count,
        "small_component_count": small_component_count,
        "large_component_count": large_component_count,
    }


def _looks_like_formula_region(image_bytes: bytes) -> tuple[bool, float, dict[str, Any]]:
    metrics = _image_component_metrics(image_bytes)
    small_components = int(metrics.get("small_component_count") or 0)
    large_components = int(metrics.get("large_component_count") or 0)
    detected = small_components >= 10 and large_components == 0
    confidence = min(0.9, 0.55 + min(small_components, 45) / 100) if detected else 0.0
    return detected, round(confidence, 4), metrics


def _text_refs_for_page(page_dict: dict[str, Any], page_number: int) -> list[str]:
    refs = []
    for block in page_dict.get("blocks") or []:
        if block.get("type") != 0:
            continue
        number = int(block.get("number", len(refs) + 1) or len(refs) + 1)
        refs.append(f"page:{page_number};text-block:{number}")
    return refs[:6]


def detect_pdf_formula_regions(path: str, *, surrounding_text_refs: list[str] | None = None) -> list[FormulaRegion]:
    try:
        import fitz
    except Exception:
        return []
    regions: list[FormulaRegion] = []
    with fitz.open(path) as document:
        for page_index, page in enumerate(document, start=1):
            page_dict = page.get_text("dict")
            page_text_refs = list(surrounding_text_refs or []) or _text_refs_for_page(page_dict, page_index)
            for block in page_dict.get("blocks") or []:
                if block.get("type") != 1:
                    continue
                box = _bbox_dict(block.get("bbox"))
                if not box or _is_full_page_image(box, page.rect):
                    continue
                image_bytes = block.get("image") or b""
                detected, confidence, metrics = _looks_like_formula_region(image_bytes)
                if not detected:
                    continue
                image_hash = hashlib.sha256(image_bytes).hexdigest() if image_bytes else ""
                regions.append(FormulaRegion(
                    formula_region_uid=str(uuid.uuid4()),
                    page_number=page_index,
                    bounding_box=box,
                    region_image_hash=image_hash,
                    detection_method="pdf_raster_image_formula_heuristic",
                    detection_confidence=confidence,
                    surrounding_text_refs=page_text_refs,
                    source_page_ref=f"page:{page_index}",
                    recognizer_status="FORMULA_RECOGNIZER_UNAVAILABLE",
                    recognizer_provider="none",
                    recognizer_model="none",
                    recognition_confidence=None,
                    latex_candidate="",
                    mathml_candidate="",
                    abstention_reason="Formula recognizer is not configured.",
                    provenance={
                        "page_image_ref": f"page:{page_index}",
                        "image_block_number": int(block.get("number", 0) or 0),
                        "image_width": int(block.get("width", 0) or 0),
                        "image_height": int(block.get("height", 0) or 0),
                        "component_metrics": metrics,
                    },
                    created_at=_utc_now(),
                ))
    return regions


def looks_like_formula_image(image_path, ocr_text=""):
    """
    Lightweight formula-region heuristic.
    It intentionally avoids claiming formula OCR success; it only decides whether
    a region should be handed to a formula OCR provider or recorded as needing one.
    """
    if contains_formula_text(ocr_text):
        return True

    mode = os.environ.get("FORMULA_DETECTION_MODE", "heuristic").strip().lower()
    if mode == "off":
        return False

    basename = os.path.basename(str(image_path or "")).lower()
    if any(marker in basename for marker in ("formula", "equation", "math")):
        return True

    # In absence of CV dependencies, use file-size and OCR emptiness as a weak
    # signal only for explicit formula-ish filenames. Empty OCR alone is too broad.
    return False
