#!/usr/bin/env python3
"""Export a safe JSON snapshot for final reports and presentation materials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PILOT_DIR = ROOT / "pilot_package"


def _load_demo_courses() -> list[dict]:
    path = ROOT / "demo_data" / "courses.json"
    if not path.exists():
        return []
    courses = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "course_code": item.get("course_code"),
            "course_name": item.get("course_name"),
            "discipline": item.get("discipline"),
        }
        for item in courses
    ]


def build_snapshot() -> dict:
    pilot_files = []
    if PILOT_DIR.exists():
        pilot_files = sorted(path.name for path in PILOT_DIR.glob("*.md"))

    return {
        "project_name": "LexiBridge AI",
        "version": "local-pilot-ready",
        "core_capabilities": [
            "multi-format document parsing",
            "image OCR and formula OCR architecture",
            "course knowledge base with evidence retrieval",
            "alignment status state machine",
            "confidence score and auto-approval gate",
            "evaluation harness and retrieval regression",
            "async background jobs",
            "role-based student/teacher/admin workflows",
            "pilot feedback loop and iteration backlog",
            "knowledge base versioning",
            "retrieval backend abstraction with hybrid/vector-ready interfaces",
        ],
        "demo_courses": _load_demo_courses(),
        "evaluation_metrics": {
            "required_smoke_metrics": [
                "extraction_precision",
                "extraction_recall",
                "evidence_accuracy",
                "alignment_accuracy",
                "false_positive_rate",
                "auto_approval_error_rate",
                "no_evidence_forced_alignment_rate",
            ],
            "critical_gate": "no_evidence_forced_alignment_rate must remain 0",
        },
        "knowledge_base_versions": {
            "supported": True,
            "scopes": ["course", "personal", "global"],
            "default_policy": "published versions only participate in default retrieval",
        },
        "retrieval_backend": {
            "default": "lexical",
            "supported_modes": ["lexical", "vector", "hybrid", "hybrid_rerank"],
            "production_note": "vector/hybrid promotion requires retrieval experiment evidence",
        },
        "ai_provider": {
            "governance_supported": True,
            "provider_modes": ["none", "mock", "local_heuristic", "live"],
            "auto_approval_policy": "mock/local results cannot auto-approve terminology cards",
        },
        "known_limitations": [
            "not production-ready",
            "SQLite and local storage are suitable only for local pilot use",
            "mock payment and mock email are not production capabilities",
            "demo data is synthetic and does not represent full real-course complexity",
            "real course materials require teacher authorization and review",
            "terminology output requires evidence, risk_note, and teacher review context",
        ],
        "pilot_package_files": pilot_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Output JSON path.")
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_snapshot(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Final project snapshot written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
