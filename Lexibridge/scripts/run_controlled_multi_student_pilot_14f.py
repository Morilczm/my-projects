#!/usr/bin/env python3
"""Run the content-minimized controlled multi-student pilot rehearsal.

The default mode creates five isolated, self-simulated Student identities in a
repository-external SQLite database and drives the existing student-pilot API.
It is deliberately not a real-user study and never calls an external Provider.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PILOT_ID = "personal-workspace-one-concept@1.0.0"
CONSENT_VERSION = "student-pilot-consent-zh@1.0.0"
PYTHON = Path(sys.executable)


def _env(database: Path, uploads: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{database}",
            "UPLOAD_FOLDER": str(uploads),
            "AUTH_REQUIRED": "True",
            "AI_PROVIDER": "none",
            "ALLOW_MOCK_AI": "True",
            "OCR_PROVIDER": "none",
            "FORMULA_OCR_PROVIDER": "none",
            "LEXIBRIDGE_SKIP_ENV_FILE": "true",
            "DEEPSEEK_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }
    )
    return env


def _load_app(env: dict[str, str]):
    os.environ.update(env)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    module_name = f"lexibridge_controlled_pilot_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, BACKEND / "app.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load backend application.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with module.app.app_context():
        module.db.create_all()
        module.ensure_schema_columns()
    module.app.config["TESTING"] = True
    module.app.config["STUDENT_REAL_PILOT_ENABLED"] = True
    return module


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_student(app_module: Any, index: int) -> tuple[int, str]:
    email = f"pilot14f-persona-{index}@lexibridge.local"
    with app_module.app.app_context():
        user = app_module.User(
            username=f"pilot14f_persona_{index}",
            email=email,
            password_hash=app_module.generate_password_hash(
                "Student1234", method="pbkdf2:sha256"
            ),
            role="student",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
        return int(user.id), app_module.create_auth_token(user)


def _create_admin(app_module: Any) -> str:
    with app_module.app.app_context():
        user = app_module.User(
            username="pilot14f_admin",
            email="pilot14f-admin@lexibridge.local",
            password_hash=app_module.generate_password_hash(
                "Admin1234", method="pbkdf2:sha256"
            ),
            role="admin",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
        return app_module.create_auth_token(user)


class _PilotEmbeddingBackend:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        return [[1.0, 0.0] if "电势" in text else [0.0, 1.0] for text in texts]


class _PilotRerankerBackend:
    backend_id = "local_bge_reranker_v2_m3_cpu_v1"
    model_id = "BAAI/bge-reranker-v2-m3"
    model_revision = "79c481748842b7efa0a12db59915db91731f0b93"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def score_pairs(self, pairs):
        return [5.0 for _ in pairs]


def _pdf_bytes(language: str) -> bytes:
    """Create a tiny synthetic fixture in memory; it never enters Git."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    if language == "zh":
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        pdf.setFont("STSong-Light", 12)
        pdf.drawString(72, 720, "电势")
        pdf.drawString(72, 690, "电势表示单位电荷在电场中的电势能。")
    else:
        pdf.drawString(72, 720, "Electric potential")
        pdf.drawString(72, 690, "Electric potential is potential energy per unit charge.")
    pdf.save()
    return buffer.getvalue()


def _upload_personal_material(
    client: Any,
    token: str,
    *,
    content: bytes,
    language: str,
    role: str,
    index: int,
) -> dict[str, Any]:
    response = client.post(
        "/api/documents/upload",
        data={
            "file": (io.BytesIO(content), f"pilot14f-{index}-{language}.pdf"),
            "scope_type": "personal",
            "language": language,
            "personal_workspace_contract": "13C2",
            "personal_material_role": role,
            "usage_rights_confirmed": "true",
            "source_name": f"Synthetic pilot {language} evidence",
            "chapter": "Electrostatics",
            "discipline": "physics",
        },
        content_type="multipart/form-data",
        headers={**_bearer(token), "X-Request-ID": f"pilot14f-upload-{index}-{language}"},
    )
    return _expect(response, 200, f"{language} material upload")


def _process_material(app_module: Any, payload: dict[str, Any], index: int, language: str) -> str:
    with app_module.app.app_context():
        app_module.run_background_job(payload["job_id"], worker_id=f"pilot14f-{index}-{language}")
        source = app_module.KnowledgeSource.query.filter_by(
            document_id=payload["document_id"]
        ).one()
        if str(source.status or "") != "active":
            raise RuntimeError(f"{language} personal source did not become active.")
        if str(source.authorization_status or "") != "allowed_for_private_use":
            raise RuntimeError(f"{language} personal source governance is incomplete.")
        return str(source.source_uid)


def _query_from_reader(client: Any, token: str, source_uid: str, index: int) -> dict[str, Any]:
    reader = _expect(
        client.get(
            f"/api/student/concept-materials/{source_uid}/reader?page=1",
            headers=_bearer(token),
        ),
        200,
        "personal reader",
    )
    items = reader.get("reader", {}).get("items", [])
    item = next(
        (candidate for candidate in items if "electric potential" in str(candidate.get("text", "")).lower()),
        None,
    )
    if item is None:
        raise RuntimeError("Synthetic English material did not expose a selectable concept.")
    text = str(item["text"])
    start = text.lower().index("electric potential")
    end = start + len("electric potential")
    return _expect(
        client.post(
            "/api/student/concept-queries",
            headers={**_bearer(token), "X-Request-ID": f"pilot14f-query-{index}"},
            json={
                "workspace_scope": "PERSONAL",
                "source_uid": source_uid,
                "chunk_uid": item["chunk_uid"],
                "selected_text": text[start:end],
                "selection_start": start,
                "selection_end": end,
            },
        ),
        200,
        "concept query",
    )


def _expect(response, status: int, label: str) -> dict[str, Any]:
    if response.status_code != status:
        raise RuntimeError(f"{label} failed: HTTP {response.status_code} {response.get_data(as_text=True)[:240]}")
    body = response.get_json() or {}
    return body.get("data") or {}


def run_rehearsal(personas: int = 5) -> dict[str, Any]:
    if personas < 5:
        raise ValueError("The controlled pilot requires at least five personas.")
    with tempfile.TemporaryDirectory(prefix="lexibridge-14f-") as temp:
        temp_root = Path(temp)
        database = temp_root / "pilot.db"
        uploads = temp_root / "uploads"
        uploads.mkdir()
        env = _env(database, uploads)
        subprocess.run([str(PYTHON), str(ROOT / "scripts" / "migrate_db.py"), "--apply"], cwd=ROOT, env=env, check=True)
        app_module = _load_app(env)
        from services import multi_student_pilot

        app_module.app.config["STUDENT_CROSS_LANGUAGE_EMBEDDING_BACKEND"] = _PilotEmbeddingBackend()
        app_module.app.config["STUDENT_BILINGUAL_RERANKER_BACKEND"] = _PilotRerankerBackend()
        client = app_module.app.test_client()
        admin_token = _create_admin(app_module)
        identities: list[dict[str, Any]] = []
        for index in range(1, personas + 1):
            student_id, token = _create_student(app_module, index)
            chinese_payload = _upload_personal_material(
                client,
                token,
                content=_pdf_bytes("zh"),
                language="zh",
                role="CHINESE_REFERENCE_EVIDENCE",
                index=index,
            )
            chinese_source_uid = _process_material(app_module, chinese_payload, index, "zh")
            english_payload = _upload_personal_material(
                client,
                token,
                content=_pdf_bytes("en"),
                language="en",
                role="ENGLISH_COURSE_MATERIAL",
                index=index,
            )
            english_source_uid = _process_material(app_module, english_payload, index, "en")
            identities.append(
                {
                    "persona_uid": f"persona-{index:02d}",
                    "student_id": student_id,
                    "token": token,
                    "english_source_uid": english_source_uid,
                    "chinese_source_uid": chinese_source_uid,
                }
            )

        outcomes: list[dict[str, Any]] = []
        for position, identity in enumerate(identities):
            token = identity["token"]
            prefix = f"pilot14f-{position + 1}"
            enrollment = _expect(
                client.post(
                    "/api/student/pilot/enrollment",
                    headers={**_bearer(token), "Idempotency-Key": f"{prefix}-enroll"},
                    json={
                        "pilot_id": PILOT_ID,
                        "consent_version": CONSENT_VERSION,
                        "consent": True,
                        "eligibility_attested": True,
                    },
                ),
                200,
                "consent",
            )
            _expect(
                client.post(
                    "/api/student/pilot/enrollment",
                    headers={**_bearer(token), "Idempotency-Key": f"{prefix}-enroll"},
                    json={
                        "pilot_id": PILOT_ID,
                        "consent_version": CONSENT_VERSION,
                        "consent": True,
                        "eligibility_attested": True,
                    },
                ),
                200,
                "consent idempotent replay",
            )
            started = _expect(
                client.post(
                    "/api/student/pilot/sessions",
                    headers={**_bearer(token), "Idempotency-Key": f"{prefix}-start"},
                    json={"pilot_id": PILOT_ID},
                ),
                200,
                "session start",
            )
            session = started["session"]
            query_payload = _query_from_reader(
                client, token, identity["english_source_uid"], position + 1
            )
            query = query_payload.get("query") or {}
            query_uid = str(query.get("query_uid") or "")
            if not query_uid or str(query.get("workspace_scope") or "") != "PERSONAL":
                raise RuntimeError("Personal concept query did not return a private query.")
            # The same selection request is deterministic and idempotent.
            replay = _query_from_reader(
                client, token, identity["english_source_uid"], position + 1
            )
            if not replay.get("idempotent_replay"):
                raise RuntimeError("Repeated concept selection did not replay idempotently.")
            # Attempt to complete another persona's query. The existing
            # student-pilot route must reject it by owner, not leak content.
            foreign_identity = identities[(position + 1) % len(identities)]
            # Create the next persona's query before the cross-account probe;
            # its upload and selection path is still owned by that persona.
            if "query_uid" not in foreign_identity:
                foreign_query_payload = _query_from_reader(
                    client,
                    foreign_identity["token"],
                    foreign_identity["english_source_uid"],
                    (position + 1) % len(identities) + 1,
                )
                foreign_identity["query_uid"] = str(
                    (foreign_query_payload.get("query") or {}).get("query_uid") or ""
                )
            foreign = foreign_identity["query_uid"]
            foreign_response = client.put(
                f"/api/student/pilot/sessions/{session['session_uid']}/complete",
                    headers={**_bearer(token), "Idempotency-Key": f"{prefix}-foreign"},
                    json={"query_uid": foreign, "expected_version": 1},
            )
            if foreign_response.status_code != 404:
                raise RuntimeError("Cross-persona query access was not blocked.")
            record = _expect(
                client.put(
                    f"/api/student/concept-queries/{query_uid}/personal-record",
                    headers={**_bearer(token), "Idempotency-Key": f"{prefix}-record"},
                    json={
                        "saved": True,
                        "note": "private synthetic note",
                        "understanding_state": "UNDERSTOOD",
                        "expected_version": 0,
                    },
                ),
                200,
                "personal learning record",
            )
            notebook = _expect(
                client.post(
                    f"/api/student/personal-concept-notebook/{query_uid}/revisit",
                    headers={**_bearer(token), "Idempotency-Key": f"{prefix}-revisit"},
                    json={"expected_version": 1},
                ),
                200,
                "personal notebook revisit",
            )
            completed = _expect(
                client.put(
                    f"/api/student/pilot/sessions/{session['session_uid']}/complete",
                    headers={**_bearer(token), "Idempotency-Key": f"{prefix}-complete"},
                    json={"query_uid": query_uid, "expected_version": 1},
                ),
                200,
                "session completion",
            )
            survey = _expect(
                client.put(
                    f"/api/student/pilot/sessions/{session['session_uid']}/survey",
                    headers={**_bearer(token), "Idempotency-Key": f"{prefix}-survey"},
                    json={
                        "helpfulness": 5,
                        "evidence_helpfulness": 4,
                        "uncertainty_understanding": 4,
                        "task_difficulty": 2,
                        "would_use_again": True,
                    },
                ),
                200,
                "survey",
            )
            outcomes.append(
                {
                    "persona_uid": identity["persona_uid"],
                    "consent_recorded": bool(enrollment.get("enrollment")),
                    "session_started": True,
                    "session_completed": completed.get("session", {}).get("status") == "COMPLETED",
                    "duration_ms": int(completed.get("session", {}).get("duration_ms") or 0),
                    "alignment_status": completed.get("session", {}).get("alignment_status", ""),
                    "evidence_complete": bool(completed.get("session", {}).get("evidence_complete")),
                    "saved": bool(completed.get("session", {}).get("saved")) and bool(record),
                    "note_present": bool(completed.get("session", {}).get("note_present")),
                    "understanding_state": completed.get("session", {}).get("understanding_state", ""),
                    "survey": {
                        key: survey.get("survey", {}).get(key)
                        for key in (
                            "helpfulness",
                            "evidence_helpfulness",
                            "uncertainty_understanding",
                            "task_difficulty",
                            "would_use_again",
                        )
                    },
                    "cross_account_access_blocked": True,
                    "external_requests": 0,
                    "real_provider_requests": 0,
                }
            )

        summary = multi_student_pilot.summarize_controlled_run(
            outcomes, participant_mode="self_simulated"
        )
        aggregate = _expect(
            client.get("/api/admin/student-pilot/aggregate", headers=_bearer(admin_token)),
            200,
            "admin aggregate",
        )
        if aggregate.get("counts", {}).get("sessions_completed") != personas:
            raise RuntimeError("Admin aggregate does not match completed pilot sessions.")
        return {
            "summary": summary,
            "aggregate_contract": {
                "metrics_suppressed": bool(aggregate.get("metrics_suppressed")),
                "sessions_completed": int(aggregate.get("counts", {}).get("sessions_completed") or 0),
                "individual_rows_returned": bool(
                    aggregate.get("privacy", {}).get("individual_rows_returned")
                ),
            },
            "outcomes": [multi_student_pilot.sanitize_outcome(row) for row in outcomes],
        }


def _write_artifacts(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = result["summary"]
    result_path = output_dir / "14F-multi-student-pilot-results.json"
    result_path.write_text(json.dumps({"summary": summary}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    matrix_path = output_dir / "14F-multi-student-pilot-matrix.csv"
    rows = result["outcomes"]
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            lineterminator="\n",
            fieldnames=[
                "persona_uid",
                "consent_recorded",
                "session_started",
                "session_completed",
                "duration_ms",
                "alignment_status",
                "evidence_complete",
                "saved",
                "note_present",
                "understanding_state",
                "cross_account_access_blocked",
            ],
        )
        writer.writeheader()
        writer.writerows(
            {
                field: row.get(field, "")
                for field in writer.fieldnames
            }
            for row in rows
        )
    privacy_path = output_dir / "14F-multi-student-pilot-privacy-audit.json"
    privacy_path.write_text(
        json.dumps(
            {
                "contract_id": summary["contract_id"],
                "participant_mode": summary["participant_mode"],
                "content_collected": False,
                "individual_rows_returned": False,
                "isolation": summary["privacy"]["isolation_audit"],
                "admin_aggregate": result["aggregate_contract"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (result_path, matrix_path, privacy_path)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--personas", type=int, default=5)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "evaluations" / "artifacts",
    )
    args = parser.parse_args(argv)
    result = run_rehearsal(args.personas)
    hashes = _write_artifacts(result, args.output_dir)
    print(json.dumps({"summary": result["summary"], "artifact_hashes": hashes}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
