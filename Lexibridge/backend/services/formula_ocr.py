import base64
import json
import os
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional


def _env_float(name, default):
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class FormulaOCRResult:
    status: str
    latex: str = ""
    plain_text: str = ""
    confidence: float = 0
    provider: str = ""
    error: str = ""
    bbox: Optional[dict] = None
    quality_flags: list = field(default_factory=list)

    @property
    def ok(self):
        return self.status == "ok" and bool((self.latex or self.plain_text).strip())


class FormulaOCRProvider:
    provider_name = "none"

    def is_available(self):
        return False

    def recognize_formula(self, image_path, bbox=None):
        return FormulaOCRResult(
            status="needs_formula_ocr_engine",
            provider=self.provider_name,
            bbox=bbox,
            error="Formula OCR provider is not configured."
        )


class NoneFormulaOCRProvider(FormulaOCRProvider):
    provider_name = "none"


class MockFormulaOCRProvider(FormulaOCRProvider):
    provider_name = "mock"

    def recognize_formula(self, image_path, bbox=None):
        return FormulaOCRResult(
            status="needs_formula_ocr_engine",
            provider=self.provider_name,
            bbox=bbox,
            error="Mock formula OCR does not generate LaTeX."
        )


class LocalLatexOCRProvider(FormulaOCRProvider):
    provider_name = "local_latex"

    def __init__(self):
        self.command = os.environ.get("LOCAL_LATEX_OCR_COMMAND", "").strip()
        self.min_confidence = _env_float("FORMULA_OCR_MIN_CONFIDENCE", 60)

    def is_available(self):
        return bool(self.command)

    def recognize_formula(self, image_path, bbox=None):
        if not self.is_available():
            return FormulaOCRResult(
                status="needs_formula_ocr_engine",
                provider=self.provider_name,
                bbox=bbox,
                error="LOCAL_LATEX_OCR_COMMAND is not configured."
            )
        if not os.path.exists(image_path):
            return FormulaOCRResult(
                status="formula_ocr_failed",
                provider=self.provider_name,
                bbox=bbox,
                error=f"Formula image not found: {image_path}"
            )

        cmd = shlex.split(self.command) + [image_path]
        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=90
            )
        except Exception as exc:
            return FormulaOCRResult(
                status="formula_ocr_failed",
                provider=self.provider_name,
                bbox=bbox,
                error=f"Local formula OCR execution failed: {exc}"
            )

        if completed.returncode != 0:
            return FormulaOCRResult(
                status="formula_ocr_failed",
                provider=self.provider_name,
                bbox=bbox,
                error=completed.stderr.strip() or "Local formula OCR returned a non-zero exit code."
            )

        latex = completed.stdout.strip()
        if not latex:
            return FormulaOCRResult(
                status="no_formula_detected",
                provider=self.provider_name,
                bbox=bbox,
                error="Local formula OCR completed but returned no LaTeX."
            )

        return FormulaOCRResult(
            status="ok",
            latex=latex,
            plain_text=latex,
            confidence=80,
            provider=self.provider_name,
            bbox=bbox
        )


class MathpixFormulaOCRProvider(FormulaOCRProvider):
    provider_name = "mathpix"

    def __init__(self):
        self.app_id = os.environ.get("MATHPIX_APP_ID", "").strip()
        self.app_key = os.environ.get("MATHPIX_APP_KEY", "").strip()
        self.min_confidence = _env_float("FORMULA_OCR_MIN_CONFIDENCE", 60)

    def is_available(self):
        return bool(self.app_id and self.app_key)

    def recognize_formula(self, image_path, bbox=None):
        if not self.is_available():
            return FormulaOCRResult(
                status="needs_formula_ocr_engine",
                provider=self.provider_name,
                bbox=bbox,
                error="MATHPIX_APP_ID and MATHPIX_APP_KEY are not configured."
            )
        if not os.path.exists(image_path):
            return FormulaOCRResult(
                status="formula_ocr_failed",
                provider=self.provider_name,
                bbox=bbox,
                error=f"Formula image not found: {image_path}"
            )

        try:
            with open(image_path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode("ascii")
            payload = json.dumps({
                "src": f"data:image/png;base64,{encoded}",
                "formats": ["latex_styled", "text"],
                "data_options": {"include_asciimath": True}
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.mathpix.com/v3/text",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "app_id": self.app_id,
                    "app_key": self.app_key
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return FormulaOCRResult(
                status="formula_ocr_failed",
                provider=self.provider_name,
                bbox=bbox,
                error=f"Mathpix API returned HTTP {exc.code}."
            )
        except Exception as exc:
            return FormulaOCRResult(
                status="formula_ocr_failed",
                provider=self.provider_name,
                bbox=bbox,
                error=f"Mathpix API call failed: {exc}"
            )

        latex = (data.get("latex_styled") or data.get("latex") or "").strip()
        plain_text = (data.get("text") or "").strip()
        confidence = float(data.get("confidence", 0) or 0) * 100
        if not latex and not plain_text:
            return FormulaOCRResult(
                status="no_formula_detected",
                provider=self.provider_name,
                bbox=bbox,
                error="Mathpix returned no formula text."
            )

        status = "ok"
        quality_flags = []
        if confidence and confidence < self.min_confidence:
            status = "low_confidence"
            quality_flags.append("formula_ocr_low_confidence")

        return FormulaOCRResult(
            status=status,
            latex=latex,
            plain_text=plain_text,
            confidence=round(confidence, 2) if confidence else 0,
            provider=self.provider_name,
            bbox=bbox,
            quality_flags=quality_flags
        )


def get_formula_ocr_provider(provider_name):
    provider_name = (provider_name or "none").strip().lower()
    if provider_name == "mathpix":
        return MathpixFormulaOCRProvider()
    if provider_name in {"local", "local_latex", "latex"}:
        return LocalLatexOCRProvider()
    if provider_name == "mock":
        return MockFormulaOCRProvider()
    return NoneFormulaOCRProvider()
