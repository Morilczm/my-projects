"""PDF layout analysis with an optional DocLayout-YOLO ONNX provider.

The rule-based provider derives a lightweight layout model from embedded PDF
text and is always available. The DocLayout-YOLO ONNX provider is an optional
heavy dependency: this module stays importable without ``onnxruntime`` /
``numpy`` / a model file, and unavailable configurations degrade to a clear
``layout_unavailable`` status (or a rule-based fallback with a warning).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from statistics import median

from services.docling_parser_adapter import (
    DOCLING_POLICY_ID,
    DOCLING_PROVIDER_ID,
    DoclingParserAdapter,
    classify_pdf_for_docling,
)


LAYOUT_PROVIDER_ENV = "LAYOUT_PROVIDER"
LAYOUT_MODEL_PATH_ENV = "LAYOUT_MODEL_PATH"
PROVIDER_RULE_BASED = "rule_based"
PROVIDER_DOCLAYOUT_YOLO_ONNX = "doclayout_yolo_onnx"
PROVIDER_DOCLING = DOCLING_PROVIDER_ID
PROVIDER_CONDITIONAL_DOCLING = "conditional_docling"
LAYOUT_TYPE_TEXT = "text"
LAYOUT_TYPE_TITLE = "title"
LAYOUT_TYPE_CAPTION = "caption"
LAYOUT_TYPE_HEADER_FOOTER = "header_footer"
LAYOUT_TYPE_PAGE_NUMBER = "page_number"
LAYOUT_TYPE_TABLE = "table"
LAYOUT_TYPE_FIGURE = "figure"
LAYOUT_TYPE_FORMULA = "formula"
LAYOUT_TYPE_LIST = "list"

SKIPPED_TEXT_LAYOUT_TYPES = {
    LAYOUT_TYPE_HEADER_FOOTER,
    LAYOUT_TYPE_PAGE_NUMBER,
    LAYOUT_TYPE_FIGURE,
    LAYOUT_TYPE_FORMULA,
}
CAPTION_PATTERN = re.compile(r"^(fig(?:ure)?\.?|table|tab\.?)\s*\d+", re.IGNORECASE)
PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:page\s*)?\d+\s*$|^第\s*\d+\s*页$",
    re.IGNORECASE,
)
MODEL_IMAGE_SIZE = 1024
DEFAULT_MODEL_SCORE_THRESHOLD = 0.25
DEFAULT_MODEL_NMS_IOU_THRESHOLD = 0.45
DOCLAYOUT_YOLO_CLASSES = (
    LAYOUT_TYPE_TITLE,
    "plain_text",
    "abandon",
    LAYOUT_TYPE_FIGURE,
    "figure_caption",
    LAYOUT_TYPE_TABLE,
    "table_caption",
    "table_footnote",
    "isolate_formula",
    "formula_caption",
)

_ONNX_SESSION_CACHE = {}


class UnsupportedModelOutput(ValueError):
    pass


def _env_float(name, default):
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self):
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self):
        return max(0.0, self.y1 - self.y0)

    @property
    def center_x(self):
        return self.x0 + self.width / 2

    @property
    def center_y(self):
        return self.y0 + self.height / 2

    def to_dict(self):
        return {
            "x0": round(self.x0, 2),
            "y0": round(self.y0, 2),
            "x1": round(self.x1, 2),
            "y1": round(self.y1, 2),
        }


@dataclass(frozen=True)
class LayoutBlock:
    page_number: int
    text: str
    bbox: BoundingBox
    layout_type: str
    reading_order: int
    page_width: float
    page_height: float
    provider: str = PROVIDER_RULE_BASED
    confidence: float = 1.0

    def to_dict(self):
        return {
            "page_number": self.page_number,
            "text": self.text,
            "bbox": self.bbox.to_dict(),
            "layout_type": self.layout_type,
            "reading_order": self.reading_order,
            "page_width": round(self.page_width, 2),
            "page_height": round(self.page_height, 2),
            "provider": self.provider,
            "confidence": self.confidence,
        }


@dataclass
class LayoutAnalysisResult:
    status: str
    provider: str = ""
    parser_version: str = ""
    page_count: int = 0
    blocks: tuple = ()
    needs_ocr_engine: bool = False
    warnings: tuple = ()
    error: str = ""
    quality_flags: list = field(default_factory=list)

    @property
    def ok(self):
        return self.status == "ok"


def normalize_block_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_provider_name(value):
    provider = (value or PROVIDER_RULE_BASED).strip().lower()

    if provider in {"onnx", "doclayout_yolo", "doclayout-yolo", "doclayout_yolo_onnx"}:
        return PROVIDER_DOCLAYOUT_YOLO_ONNX

    if provider in {"", "rule", "rules", "rule_based", "rule-based"}:
        return PROVIDER_RULE_BASED

    if provider in {"docling", "docling_offline"}:
        return PROVIDER_DOCLING

    if provider in {
        "conditional_docling",
        "conditional-docling",
        "docling_conditional",
    }:
        return PROVIDER_CONDITIONAL_DOCLING

    return provider


def layout_blocks_to_text(blocks):
    parts = []
    current_page = None

    for block in sorted(blocks, key=lambda item: (item.page_number, item.reading_order)):
        if block.layout_type in SKIPPED_TEXT_LAYOUT_TYPES:
            continue

        if block.page_number != current_page:
            current_page = block.page_number
            parts.append(f"[Page {current_page}]")

        parts.append(block.text)

    return "\n".join(parts).strip()


class LayoutAnalyzer:
    provider_name = "none"

    def is_available(self):
        return False

    def analyze_pdf(self, path):
        return LayoutAnalysisResult(
            status="layout_unavailable",
            provider=self.provider_name,
            error="No layout analyzer is configured.",
        )


class NoneLayoutAnalyzer(LayoutAnalyzer):
    provider_name = "none"


class RuleBasedLayoutAnalyzer(LayoutAnalyzer):
    """Deterministic layout model extracted from embedded PDF text.

    This provider is intentionally small: it gives the application a stable
    data contract and a dependency-free fallback before the heavier ONNX
    layout model provider is enabled.
    """

    provider_name = PROVIDER_RULE_BASED

    def is_available(self):
        return True

    def analyze_pdf(self, path):
        try:
            import fitz
        except ImportError:
            return LayoutAnalysisResult(
                status="layout_unavailable",
                provider=self.provider_name,
                error="PyMuPDF is not installed.",
            )

        blocks = []
        warnings = []

        with fitz.open(path) as doc:
            for page_index, page in enumerate(doc, start=1):
                blocks.extend(_extract_page_blocks(page, page_index))

            page_count = doc.page_count

        ordered = _with_reading_order(blocks)
        needs_ocr_engine = _needs_ocr_engine(page_count, ordered)

        if needs_ocr_engine:
            warnings.append("no_embedded_text_blocks")

        return LayoutAnalysisResult(
            status="ok",
            provider=self.provider_name,
            page_count=page_count,
            blocks=tuple(ordered),
            needs_ocr_engine=needs_ocr_engine,
            warnings=tuple(warnings),
        )


class DocLayoutYoloOnnxLayoutAnalyzer(LayoutAnalyzer):
    provider_name = PROVIDER_DOCLAYOUT_YOLO_ONNX

    def __init__(self, model_path=None):
        self.model_path = (model_path or os.environ.get(LAYOUT_MODEL_PATH_ENV, "")).strip()
        self.score_threshold = _env_float("LAYOUT_MODEL_SCORE_THRESHOLD", DEFAULT_MODEL_SCORE_THRESHOLD)
        self.nms_iou_threshold = _env_float("LAYOUT_MODEL_NMS_IOU_THRESHOLD", DEFAULT_MODEL_NMS_IOU_THRESHOLD)
        self._availability_error = self._check_availability()

    def _check_availability(self):
        if not self.model_path:
            return "LAYOUT_MODEL_PATH is not set"
        if not os.path.exists(self.model_path):
            return "LAYOUT_MODEL_PATH does not exist"
        try:
            import numpy  # noqa: F401
            import onnxruntime  # noqa: F401
        except ImportError as exc:
            return str(exc)
        return ""

    def is_available(self):
        return not self._availability_error

    def _get_session(self, ort):
        cached = _ONNX_SESSION_CACHE.get(self.model_path)

        if cached is not None:
            return cached

        session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
        _ONNX_SESSION_CACHE[self.model_path] = session

        return session

    def analyze_pdf(self, path):
        if not self.is_available():
            return LayoutAnalysisResult(
                status="layout_unavailable",
                provider=self.provider_name,
                error=f"DocLayout-YOLO ONNX provider is not available: {self._availability_error}",
            )

        import fitz
        import numpy as np
        import onnxruntime as ort

        try:
            session = self._get_session(ort)
        except Exception as exc:
            return LayoutAnalysisResult(
                status="layout_unavailable",
                provider=self.provider_name,
                error=f"Failed to load ONNX model: {exc}",
            )

        blocks = []
        warnings = []

        with fitz.open(path) as doc:
            for page_index, page in enumerate(doc, start=1):
                try:
                    blocks.extend(
                        _detect_model_blocks(
                            page,
                            page_index,
                            session,
                            np,
                            fitz,
                            score_threshold=self.score_threshold,
                            nms_iou_threshold=self.nms_iou_threshold,
                        )
                    )
                except Exception as exc:
                    warnings.append(f"page_{page_index}_model_failed:{exc}")

            page_count = doc.page_count

        ordered = _with_reading_order(blocks)
        needs_ocr_engine = _needs_ocr_engine(page_count, ordered)

        if needs_ocr_engine:
            warnings.append("no_embedded_text_blocks")

        return LayoutAnalysisResult(
            status="ok",
            provider=self.provider_name,
            page_count=page_count,
            blocks=tuple(ordered),
            needs_ocr_engine=needs_ocr_engine,
            warnings=tuple(warnings),
        )


class DoclingLayoutAnalyzer(LayoutAnalyzer):
    """Translate the isolated Docling worker contract into layout blocks."""

    provider_name = PROVIDER_DOCLING

    def __init__(self):
        self.adapter = DoclingParserAdapter()

    def is_available(self):
        # Availability is deliberately resolved by the adapter's local-only
        # preflight so no credential or network probe is needed here.
        return True

    def analyze_pdf(self, path):
        result = self.adapter.analyze_pdf(path)
        if result.status != "ok":
            return LayoutAnalysisResult(
                status=result.status,
                provider=self.provider_name,
                error=result.reason_code or "DOCLING_PARSE_FAILED",
                warnings=result.warnings,
                quality_flags=["docling_fail_closed"],
            )
        blocks = []
        for item in result.blocks:
            blocks.append(
                LayoutBlock(
                    page_number=item.page_number,
                    text=item.text,
                    bbox=BoundingBox(*item.bbox),
                    layout_type=item.layout_type,
                    reading_order=item.reading_order,
                    page_width=item.page_width,
                    page_height=item.page_height,
                    provider=self.provider_name,
                    confidence=item.confidence,
                )
            )
        return LayoutAnalysisResult(
            status="ok",
            provider=self.provider_name,
            parser_version=result.parser_version,
            page_count=result.page_count,
            blocks=tuple(blocks),
            needs_ocr_engine=_needs_ocr_engine(result.page_count, blocks),
            warnings=result.warnings,
            quality_flags=[
                "docling_offline_adapter",
                f"docling_version_{result.parser_version or 'unknown'}",
            ],
        )


def get_layout_analyzer(name=None):
    provider = normalize_provider_name(name or os.environ.get(LAYOUT_PROVIDER_ENV, PROVIDER_RULE_BASED))

    if provider == PROVIDER_DOCLAYOUT_YOLO_ONNX:
        return DocLayoutYoloOnnxLayoutAnalyzer()

    if provider == PROVIDER_DOCLING:
        return DoclingLayoutAnalyzer()

    if provider == PROVIDER_RULE_BASED:
        return RuleBasedLayoutAnalyzer()

    return NoneLayoutAnalyzer()


def parse_pdf_layout(path, provider=None):
    """Analyze a PDF with the requested provider, degrading gracefully.

    An unavailable or unknown ONNX provider falls back to the deterministic
    rule-based provider with an explanatory warning attached to the result.
    """
    explicit_provider = provider is not None
    requested = normalize_provider_name(
        provider or os.environ.get(LAYOUT_PROVIDER_ENV, PROVIDER_RULE_BASED)
    )

    if requested == PROVIDER_DOCLAYOUT_YOLO_ONNX:
        analyzer = DocLayoutYoloOnnxLayoutAnalyzer()
        result = analyzer.analyze_pdf(path)

        if result.ok:
            return result

        fallback = RuleBasedLayoutAnalyzer().analyze_pdf(path)
        return _with_warning(fallback, f"onnx_provider_unavailable:{result.error}")

    if requested == PROVIDER_CONDITIONAL_DOCLING:
        decision = classify_pdf_for_docling(path)
        route_flag = decision.reason_codes[0].casefold() if decision.reason_codes else "docling_route_unknown"
        route_flag = re.sub(r"[^a-z0-9]+", "_", route_flag).strip("_")
        if not decision.docling_allowed:
            fallback = RuleBasedLayoutAnalyzer().analyze_pdf(path)
            return replace(
                fallback,
                quality_flags=list(fallback.quality_flags)
                + [
                    f"docling_policy_{DOCLING_POLICY_ID.replace('@', '_').replace('.', '_').replace('-', '_')}",
                    route_flag,
                ],
            )
        result = DoclingLayoutAnalyzer().analyze_pdf(path)
        if result.ok:
            return replace(
                result,
                quality_flags=list(result.quality_flags)
                + [
                    f"docling_policy_{DOCLING_POLICY_ID.replace('@', '_').replace('.', '_').replace('-', '_')}",
                    route_flag,
                ],
            )
        fallback = RuleBasedLayoutAnalyzer().analyze_pdf(path)
        return replace(
            _with_warning(fallback, f"docling_fallback:{result.error or result.status}"),
            quality_flags=list(fallback.quality_flags)
            + ["docling_fallback_rule_based", route_flag],
        )

    if requested == PROVIDER_DOCLING:
        if not explicit_provider:
            fallback = RuleBasedLayoutAnalyzer().analyze_pdf(path)
            return replace(
                _with_warning(fallback, "docling_direct_provider_rejected"),
                quality_flags=list(fallback.quality_flags)
                + ["docling_conditional_policy_required"],
            )
        result = DoclingLayoutAnalyzer().analyze_pdf(path)
        if result.ok:
            return result
        fallback = RuleBasedLayoutAnalyzer().analyze_pdf(path)
        return replace(
            _with_warning(fallback, f"docling_fallback:{result.error or result.status}"),
            quality_flags=list(fallback.quality_flags) + ["docling_fallback_rule_based"],
        )

    if requested != PROVIDER_RULE_BASED:
        fallback = RuleBasedLayoutAnalyzer().analyze_pdf(path)
        return _with_warning(fallback, f"unknown_layout_provider:{requested}")

    return RuleBasedLayoutAnalyzer().analyze_pdf(path)


def extract_pdf_text_with_layout(path, provider=None):
    result = parse_pdf_layout(path, provider=provider)

    if result.needs_ocr_engine or not result.ok:
        return ""

    return layout_blocks_to_text(result.blocks)


def _detect_model_blocks(page, page_number, session, np, fitz, *, score_threshold, nms_iou_threshold):
    tensor, scale, pad_x, pad_y = _render_page_tensor(page, np, fitz)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: tensor})

    if not outputs:
        return []

    detections = _normalize_model_output(outputs[0], np, score_threshold=score_threshold, nms_iou_threshold=nms_iou_threshold)
    page_width = float(page.rect.width)
    page_height = float(page.rect.height)
    blocks = []

    for detection in detections:
        x0, y0, x1, y1, score, class_id = detection[:6]

        if score < score_threshold:
            continue

        bbox = _model_bbox_to_page_bbox(
            x0,
            y0,
            x1,
            y1,
            scale,
            pad_x,
            pad_y,
            page_width,
            page_height,
        )

        if bbox.width < 1 or bbox.height < 1:
            continue

        class_index = int(round(class_id))
        model_class = (
            DOCLAYOUT_YOLO_CLASSES[class_index]
            if 0 <= class_index < len(DOCLAYOUT_YOLO_CLASSES)
            else "plain_text"
        )
        layout_type = _model_class_to_layout_type(model_class)
        text = _extract_text_in_bbox(page, fitz, bbox)

        blocks.append(
            LayoutBlock(
                page_number=page_number,
                text=text,
                bbox=bbox,
                layout_type=layout_type,
                reading_order=0,
                page_width=page_width,
                page_height=page_height,
                provider=PROVIDER_DOCLAYOUT_YOLO_ONNX,
                confidence=round(float(score), 4),
            )
        )

    return _deduplicate_model_blocks(blocks)


def _render_page_tensor(page, np, fitz):
    scale = min(MODEL_IMAGE_SIZE / float(page.rect.width), MODEL_IMAGE_SIZE / float(page.rect.height))
    # PyMuPDF has no direct target-size render call; use a matrix scaled to the
    # model input while preserving aspect ratio.
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csRGB)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

    if image.shape[2] > 3:
        image = image[:, :, :3]

    render_width = min(pix.width, MODEL_IMAGE_SIZE)
    render_height = min(pix.height, MODEL_IMAGE_SIZE)
    canvas = np.full((MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE, 3), 114, dtype=np.uint8)
    pad_x = max(0, (MODEL_IMAGE_SIZE - render_width) // 2)
    pad_y = max(0, (MODEL_IMAGE_SIZE - render_height) // 2)
    canvas[pad_y:pad_y + render_height, pad_x:pad_x + render_width, :] = image[:render_height, :render_width, :]

    tensor = canvas.transpose(2, 0, 1).astype(np.float32) / 255.0

    return tensor[None, :, :, :], scale, pad_x, pad_y


def _deduplicate_model_blocks(blocks):
    deduplicated = []

    for index, block in enumerate(blocks):
        if _is_contained_duplicate_model_block(block, blocks, index):
            continue

        confidence = _aggregated_duplicate_confidence(block, blocks, index)
        if confidence > block.confidence:
            block = replace(block, confidence=confidence)

        deduplicated.append(block)

    return deduplicated


def _aggregated_duplicate_confidence(block, blocks, block_index):
    text = _normalized_text_for_duplicate(block.text)
    best_confidence = block.confidence

    if not text:
        return best_confidence

    for other_index, other in enumerate(blocks):
        if other_index == block_index:
            continue

        if other.page_number != block.page_number or other.layout_type != block.layout_type:
            continue

        other_text = _normalized_text_for_duplicate(other.text)

        if not other_text:
            continue

        other_area = _bbox_area(other.bbox)

        if other_area <= 0:
            continue

        intersection = _bbox_intersection_area(block.bbox, other.bbox)
        contained_ratio = intersection / other_area

        if contained_ratio < 0.9:
            continue

        if other_text == text or other_text in text:
            best_confidence = max(best_confidence, other.confidence)

    return round(best_confidence, 4)


def _is_contained_duplicate_model_block(block, blocks, block_index):
    text = _normalized_text_for_duplicate(block.text)

    if not text:
        return False

    block_area = _bbox_area(block.bbox)

    if block_area <= 0:
        return False

    for other_index, other in enumerate(blocks):
        if other_index == block_index:
            continue

        if other.page_number != block.page_number or other.layout_type != block.layout_type:
            continue

        other_text = _normalized_text_for_duplicate(other.text)

        if not other_text:
            continue

        intersection = _bbox_intersection_area(block.bbox, other.bbox)
        contained_ratio = intersection / block_area

        if contained_ratio < 0.9:
            continue

        if text == other_text:
            if other.confidence > block.confidence:
                return True

            if other.confidence == block.confidence and other_index < block_index:
                return True

            continue

        if text in other_text and _bbox_area(other.bbox) > block_area:
            return True

    return False


def _normalized_text_for_duplicate(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _bbox_area(bbox):
    return bbox.width * bbox.height


def _bbox_intersection_area(first, second):
    x0 = max(first.x0, second.x0)
    y0 = max(first.y0, second.y0)
    x1 = min(first.x1, second.x1)
    y1 = min(first.y1, second.y1)

    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _normalize_model_output(output, np, *, score_threshold=DEFAULT_MODEL_SCORE_THRESHOLD, nms_iou_threshold=DEFAULT_MODEL_NMS_IOU_THRESHOLD):
    data = np.asarray(output)

    if data.ndim == 3 and data.shape[0] == 1:
        data = data[0]

    if data.ndim != 2:
        raise UnsupportedModelOutput(f"unsupported output rank: {data.shape}")

    class_count = len(DOCLAYOUT_YOLO_CLASSES)
    raw_attribute_count = 4 + class_count

    if data.shape[-1] == 6:
        return data

    if data.shape[0] == 6:
        return data.T

    if data.shape[0] == raw_attribute_count:
        return _decode_raw_yolo_output(data.T, np, score_threshold=score_threshold, nms_iou_threshold=nms_iou_threshold)

    if data.shape[-1] == raw_attribute_count:
        return _decode_raw_yolo_output(data, np, score_threshold=score_threshold, nms_iou_threshold=nms_iou_threshold)

    raise UnsupportedModelOutput(f"unsupported output shape: {data.shape}")


def _decode_raw_yolo_output(predictions, np, *, score_threshold=DEFAULT_MODEL_SCORE_THRESHOLD, nms_iou_threshold=DEFAULT_MODEL_NMS_IOU_THRESHOLD):
    """
    Decode Ultralytics-style raw ONNX output.

    Supported raw shape after normalization is (num_predictions, 4 + classes),
    where columns are xywh + per-class scores. This is the traditional YOLO
    export contract when NMS/end-to-end postprocessing is not embedded.
    """
    if predictions.shape[1] != 4 + len(DOCLAYOUT_YOLO_CLASSES):
        raise UnsupportedModelOutput(f"unsupported raw prediction shape: {predictions.shape}")

    boxes_xywh = predictions[:, :4].astype(np.float32)
    class_scores = predictions[:, 4:].astype(np.float32)

    class_ids = np.argmax(class_scores, axis=1).astype(np.float32)
    scores = np.max(class_scores, axis=1).astype(np.float32)
    keep = scores >= score_threshold

    if not np.any(keep):
        return np.empty((0, 6), dtype=np.float32)

    boxes_xywh = boxes_xywh[keep]
    scores = scores[keep]
    class_ids = class_ids[keep]

    if boxes_xywh.size and np.nanmax(np.abs(boxes_xywh)) <= 2.0:
        boxes_xywh = boxes_xywh * float(MODEL_IMAGE_SIZE)

    boxes_xyxy = _xywh_to_xyxy(boxes_xywh, np)
    keep_indices = _nms(boxes_xyxy, scores, np, iou_threshold=nms_iou_threshold)

    if not keep_indices:
        return np.empty((0, 6), dtype=np.float32)

    keep_indices = np.asarray(keep_indices, dtype=np.int64)

    return np.concatenate(
        [
            boxes_xyxy[keep_indices],
            scores[keep_indices, None],
            class_ids[keep_indices, None],
        ],
        axis=1,
    ).astype(np.float32)


def _xywh_to_xyxy(boxes_xywh, np):
    boxes = np.empty_like(boxes_xywh, dtype=np.float32)
    boxes[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
    boxes[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
    boxes[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
    boxes[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2

    return boxes


def _nms(boxes, scores, np, *, iou_threshold=DEFAULT_MODEL_NMS_IOU_THRESHOLD):
    if boxes.size == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = scores.argsort()[::-1]
    keep = []

    while order.size > 0:
        index = int(order[0])
        keep.append(index)

        if order.size == 1:
            break

        rest = order[1:]
        xx1 = np.maximum(x1[index], x1[rest])
        yy1 = np.maximum(y1[index], y1[rest])
        xx2 = np.minimum(x2[index], x2[rest])
        yy2 = np.minimum(y2[index], y2[rest])
        widths = np.maximum(0, xx2 - xx1)
        heights = np.maximum(0, yy2 - yy1)
        intersection = widths * heights
        union = areas[index] + areas[rest] - intersection
        iou = intersection / np.maximum(union, 1e-9)
        order = rest[iou <= iou_threshold]

    return keep


def _model_bbox_to_page_bbox(x0, y0, x1, y1, scale, pad_x, pad_y, page_width, page_height):
    px0 = (float(x0) - pad_x) / scale
    py0 = (float(y0) - pad_y) / scale
    px1 = (float(x1) - pad_x) / scale
    py1 = (float(y1) - pad_y) / scale

    left = min(px0, px1)
    right = max(px0, px1)
    top = min(py0, py1)
    bottom = max(py0, py1)

    return BoundingBox(
        x0=max(0.0, min(page_width, left)),
        y0=max(0.0, min(page_height, top)),
        x1=max(0.0, min(page_width, right)),
        y1=max(0.0, min(page_height, bottom)),
    )


def _model_class_to_layout_type(model_class):
    if model_class == "plain_text" or model_class == "table_footnote":
        return LAYOUT_TYPE_TEXT

    if model_class == "abandon":
        return LAYOUT_TYPE_HEADER_FOOTER

    if model_class in {"figure_caption", "table_caption", "formula_caption"}:
        return LAYOUT_TYPE_CAPTION

    if model_class == "isolate_formula":
        return LAYOUT_TYPE_FORMULA

    return model_class


def _extract_text_in_bbox(page, fitz, bbox):
    rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    return normalize_block_text(page.get_text("text", clip=rect, sort=True) or "")


def _needs_ocr_engine(page_count, blocks):
    return page_count > 0 and not any(
        block.text.strip() and block.layout_type not in SKIPPED_TEXT_LAYOUT_TYPES
        for block in blocks
    )


def _with_warning(result, warning):
    warnings = tuple(list(result.warnings) + [warning])

    return LayoutAnalysisResult(
        status=result.status,
        provider=result.provider,
        parser_version=result.parser_version,
        page_count=result.page_count,
        blocks=result.blocks,
        needs_ocr_engine=result.needs_ocr_engine,
        warnings=warnings,
        error=result.error,
        quality_flags=list(result.quality_flags),
    )


def _extract_page_blocks(page, page_number):
    page_width = float(page.rect.width)
    page_height = float(page.rect.height)
    raw_blocks = page.get_text("dict").get("blocks", [])
    candidates = []
    font_sizes = []

    for raw_block in raw_blocks:
        if raw_block.get("type") != 0:
            continue

        text, sizes = _text_and_sizes(raw_block)
        text = normalize_block_text(text)

        if not text:
            continue

        bbox = BoundingBox(*[float(value) for value in raw_block.get("bbox", (0, 0, 0, 0))])
        if bbox.width < 1 or bbox.height < 1:
            continue

        candidates.append((text, bbox, sizes))
        font_sizes.extend(sizes)

    body_font_size = median(font_sizes) if font_sizes else 10.0
    blocks = []

    for index, (text, bbox, sizes) in enumerate(candidates):
        max_font_size = max(sizes) if sizes else body_font_size
        layout_type = _classify_block(text, bbox, page_width, page_height, max_font_size, body_font_size)
        blocks.append(
            LayoutBlock(
                page_number=page_number,
                text=text,
                bbox=bbox,
                layout_type=layout_type,
                reading_order=index,
                page_width=page_width,
                page_height=page_height,
            )
        )

    return blocks


def _text_and_sizes(raw_block):
    lines = []
    sizes = []

    for line in raw_block.get("lines", []):
        parts = []

        for span in line.get("spans", []):
            text = span.get("text", "")
            if text:
                parts.append(text)
            size = span.get("size")
            if isinstance(size, (int, float)) and size > 0:
                sizes.append(float(size))

        if parts:
            lines.append(" ".join(parts))

    return "\n".join(lines), sizes


def _classify_block(text, bbox, page_width, page_height, max_font_size, body_font_size):
    normalized = normalize_block_text(text)

    if PAGE_NUMBER_PATTERN.fullmatch(normalized):
        return LAYOUT_TYPE_PAGE_NUMBER

    if CAPTION_PATTERN.match(normalized):
        return LAYOUT_TYPE_CAPTION

    if _looks_like_title(normalized, max_font_size, body_font_size):
        return LAYOUT_TYPE_TITLE

    if _is_header_or_footer(normalized, bbox, page_height, max_font_size, body_font_size):
        return LAYOUT_TYPE_HEADER_FOOTER

    if re.match(r"^(?:[-•·▪◦]|\d+[.)、])\s*", normalized):
        return LAYOUT_TYPE_LIST

    if "|" in normalized or "\t" in text:
        return LAYOUT_TYPE_TABLE

    if re.search(r"(?:=|∫|∑|√|≈|≤|≥)", normalized) and len(normalized) <= 180:
        return LAYOUT_TYPE_FORMULA

    return LAYOUT_TYPE_TEXT


def _looks_like_title(text, max_font_size, body_font_size):
    if len(text) > 180:
        return False

    return max_font_size >= max(13.0, body_font_size * 1.22)


def _is_header_or_footer(text, bbox, page_height, max_font_size, body_font_size):
    if len(text) > 140:
        return False

    top_margin = page_height * 0.08
    bottom_margin = page_height * 0.92
    in_margin = bbox.center_y <= top_margin or bbox.center_y >= bottom_margin

    if not in_margin:
        return False

    return max_font_size <= body_font_size * 1.15


def _with_reading_order(blocks):
    ordered = sorted(blocks, key=_reading_order_key)

    return [
        LayoutBlock(
            page_number=block.page_number,
            text=block.text,
            bbox=block.bbox,
            layout_type=block.layout_type,
            reading_order=index,
            page_width=block.page_width,
            page_height=block.page_height,
            provider=block.provider,
            confidence=block.confidence,
        )
        for index, block in enumerate(ordered, start=1)
    ]


def _reading_order_key(block):
    column = _column_index(block)

    return (block.page_number, column, block.bbox.y0, block.bbox.x0)


def _column_index(block):
    if block.bbox.width >= block.page_width * 0.62:
        return 0

    return 0 if block.bbox.center_x < block.page_width / 2 else 1
