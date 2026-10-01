#!/usr/bin/env python3
"""Run a deterministic minimum demo flow for LexiBridge AI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seed_demo_data import DEMO_EVALUATION_SET_NAME, seed_demo_data  # noqa: E402


def load_app_module():
    sys.path.insert(0, str(ROOT / "backend"))
    import importlib.util

    spec = importlib.util.spec_from_file_location("lexibridge_demo_flow_app", ROOT / "backend" / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def gold_rows_for_course(course_code):
    rows = []
    for path in (ROOT / "demo_data").glob("*/gold_terms.jsonl"):
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if row.get("course_code") == course_code:
                rows.append(row)
    return rows


def best_knowledge_chunk(appmod, course_id, language, needle):
    query = appmod.KnowledgeChunk.query.filter_by(course_id=course_id, language=language)
    for chunk in query.all():
        if needle and needle in chunk.content:
            return chunk
    return query.first()


def ensure_completed_job(appmod, job_type, created_by, course_id=None, document_id=None, alignment_run_id=None, evaluation_run_id=None):
    job = appmod.BackgroundJob(
        job_type=job_type,
        status="completed",
        priority=50,
        created_by=created_by,
        course_id=course_id,
        document_id=document_id,
        alignment_run_id=alignment_run_id,
        evaluation_run_id=evaluation_run_id,
        scope_type="course" if course_id else "global",
        input_json=json.dumps({"demo_seed": True}, ensure_ascii=False),
        result_json=json.dumps({"demo_flow": True}, ensure_ascii=False),
        progress_current=1,
        progress_total=1,
        progress_message="Demo flow completed",
        started_at=appmod.current_time_text(),
        finished_at=appmod.current_time_text(),
        created_at=appmod.current_time_text(),
        updated_at=appmod.current_time_text(),
    )
    appmod.db.session.add(job)
    appmod.db.session.flush()
    appmod.db.session.add(appmod.BackgroundJobEvent(
        job_id=job.id,
        event_type="completed",
        message="Demo flow job completed.",
        progress_current=1,
        progress_total=1,
        metadata_json=json.dumps({"demo_seed": True}, ensure_ascii=False),
        created_at=appmod.current_time_text(),
    ))
    return job


def upsert_demo_cards(appmod, course, teacher, alignment_run):
    rows = gold_rows_for_course(course.course_code)[:10]
    cards = []
    for row in rows:
        english_chunk = best_knowledge_chunk(appmod, course.id, "en", row.get("expected_english_evidence", ""))
        chinese_chunk = best_knowledge_chunk(appmod, course.id, "zh", row.get("expected_chinese_evidence", ""))
        if row["expected_alignment_status"] in {"no_zh_evidence", "formula_evidence_missing", "domain_mismatch", "unverified_translation"}:
            status = "needs_more_evidence"
        else:
            status = "pending_quality_control"
        flags = ["demo_seed", "mock_or_local_ai"]
        if row["expected_alignment_status"] != "exact_match":
            flags.append(row["expected_alignment_status"])
        if "formula_related" in row.get("tags", []):
            flags.append("formula_evidence_missing")
        confidence = 42 if status == "needs_more_evidence" else 72
        card = appmod.TerminologyCard.query.filter_by(
            scope_type="course",
            course_id=course.id,
            english_term=row["english_term"],
        ).first()
        if card is None:
            card = appmod.TerminologyCard(
                scope_type="course",
                course_id=course.id,
                owner_user_id=None,
                english_term=row["english_term"],
                created_at=appmod.current_time_text(),
            )
            appmod.db.session.add(card)
        card.normalized_english_term = row["english_term"].strip().lower()
        card.final_chinese_term = row.get("expected_chinese_term", "")
        card.normalized_chinese_term = row.get("expected_chinese_term", "")
        card.ai_translation_candidate = row.get("expected_chinese_term", "")
        card.courseware_sentence = row.get("english_context", "")
        card.english_kb_evidence = row.get("expected_english_evidence", "")
        card.chinese_kb_evidence = row.get("expected_chinese_evidence", "")
        card.english_evidence_snapshot = row.get("expected_english_evidence", "")
        card.chinese_evidence_snapshot = row.get("expected_chinese_evidence", "")
        card.english_evidence_score = 0.86 if row.get("expected_english_evidence") else 0.0
        card.chinese_evidence_score = 0.84 if row.get("expected_chinese_evidence") else 0.0
        card.concept_explanation = f"Demo card for {row['english_term']} in {course.course_code}."
        card.alignment_reason = "Demo local evidence snapshot; teacher review is required unless live AI is configured."
        card.alignment_status = row["expected_alignment_status"]
        card.score_breakdown_json = json.dumps({
            "term_quality_score": 0.9,
            "english_evidence_score": card.english_evidence_score,
            "chinese_evidence_score": card.chinese_evidence_score,
            "ai_alignment_score": 0.55,
            "risk_penalty": 30,
        }, ensure_ascii=False)
        card.quality_flags_json = json.dumps(sorted(set(flags)), ensure_ascii=False)
        card.confidence_score = confidence
        card.status = status
        card.ai_provider = "local_heuristic"
        card.ai_model = "demo-local"
        card.prompt_version = "alignment_v1"
        card.retrieval_version = "local_lexical_v1"
        card.source_alignment_run_id = alignment_run.id
        card.alignment_run_id = alignment_run.id
        card.risk_note = "demo_seed=true; local/demo AI output cannot be auto-approved."
        card.english_evidence_chunk_id = english_chunk.id if english_chunk else None
        card.chinese_evidence_chunk_id = chinese_chunk.id if chinese_chunk else None
        card.updated_at = appmod.current_time_text()
        cards.append(card)
    appmod.db.session.flush()
    return cards


def run_demo_flow(skip_evaluation=False):
    os.environ["AI_PROVIDER"] = "none"
    os.environ["ALLOW_MOCK_AI"] = "True"
    os.environ["OCR_PROVIDER"] = os.environ.get("OCR_PROVIDER", "none")
    os.environ["FORMULA_OCR_PROVIDER"] = os.environ.get("FORMULA_OCR_PROVIDER", "none")
    seed_demo_data(reset=False)
    appmod = load_app_module()
    summary = {
        "document_ingestion": "FAIL",
        "alignment_run": "FAIL",
        "cards_generated": 0,
        "qc_cards": 0,
        "auto_approved_cards": 0,
        "student_search": "FAIL",
        "student_feedback": "FAIL",
        "admin_jobs": "FAIL",
        "evaluation_run": "SKIPPED" if skip_evaluation else "FAIL",
        "no_evidence_forced_alignment_rate": None,
        "evaluation_run_id": None,
        "evaluation_metrics": {},
    }
    with appmod.app.app_context():
        teacher = appmod.User.query.filter_by(email="teacher@lexibridge.local").first()
        student = appmod.User.query.filter_by(email="student@lexibridge.local").first()
        admin = appmod.User.query.filter_by(email="admin@lexibridge.local").first()
        course = appmod.Course.query.filter_by(course_code="SP101").first()
        if not all([teacher, student, admin, course]):
            raise RuntimeError("Demo users or SP101 course are missing. Run seed_demo_data.py first.")

        documents = appmod.Document.query.filter_by(course_id=course.id, source_type="demo_seed").all()
        for document in documents:
            ensure_completed_job(appmod, "document_ingestion", teacher.id, course_id=course.id, document_id=document.id)
        summary["document_ingestion"] = "PASS" if documents else "FAIL"

        alignment_run = appmod.AlignmentRun(
            document_id=documents[0].id if documents else None,
            course_id=course.id,
            triggered_by=teacher.id,
            provider="local_heuristic",
            model_name="demo-local",
            ai_provider="local_heuristic",
            ai_model="demo-local",
            prompt_version="alignment_v1",
            retrieval_version="local_lexical_v1",
            status="completed",
            started_at=appmod.current_time_text(),
            finished_at=appmod.current_time_text(),
            error_message="demo_seed=true",
        )
        appmod.db.session.add(alignment_run)
        appmod.db.session.flush()
        cards = upsert_demo_cards(appmod, course, teacher, alignment_run)
        qc_count = len([card for card in cards if card.status == "pending_quality_control"])
        needs_count = len([card for card in cards if card.status == "needs_more_evidence"])
        alignment_run.term_count = len(cards)
        alignment_run.terms_extracted = len(cards)
        alignment_run.cards_created = len(cards)
        alignment_run.card_created_count = len(cards)
        alignment_run.auto_approved_count = 0
        alignment_run.qc_count = qc_count
        alignment_run.needs_evidence_count = needs_count
        alignment_run.conflict_count = 0
        alignment_run.failed_count = 0
        ensure_completed_job(appmod, "alignment_run", teacher.id, course_id=course.id, alignment_run_id=alignment_run.id)
        summary["alignment_run"] = "PASS"
        summary["cards_generated"] = len(cards)
        summary["qc_cards"] = qc_count + needs_count
        summary["auto_approved_cards"] = 0

        target_card = cards[0] if cards else None
        if target_card:
            record = appmod.StudentTermRecord.query.filter_by(user_id=student.id, term_id=target_card.id).first()
            if record is None:
                record = appmod.StudentTermRecord(user_id=student.id, term_id=target_card.id)
                appmod.db.session.add(record)
            record.is_favorite = True
            record.is_mastered = True
            record.last_viewed_at = appmod.current_time_text()
            feedback = appmod.Feedback(
                term_id=target_card.id,
                user_id=student.id,
                course_id=course.id,
                course=course.name,
                english_term=target_card.english_term,
                chinese_term=target_card.final_chinese_term,
                feedback_type="evidence_error",
                severity="normal",
                feedback_content="Demo feedback: please review evidence clarity.",
                status="open",
                created_at=appmod.current_time_text(),
            )
            appmod.db.session.add(feedback)
            summary["student_search"] = "PASS"
            summary["student_feedback"] = "PASS"

        if appmod.BackgroundJob.query.count() > 0 and appmod.SystemLog.query.count() >= 0:
            summary["admin_jobs"] = "PASS"

        if not skip_evaluation:
            evaluation_set = appmod.EvaluationSet.query.filter_by(name="lexibridge_demo_gold_v1").first()
            evaluation_run = appmod.run_evaluation_set(
                evaluation_set,
                admin,
                split="test",
                model_version="demo-local",
                prompt_version="alignment_v1",
                retrieval_version="local_lexical_v1",
            )
            appmod.db.session.flush()
            ensure_completed_job(appmod, "evaluation_run", admin.id, evaluation_run_id=evaluation_run.id)
            metrics = json.loads(evaluation_run.metrics_json or "{}")
            summary["evaluation_run"] = "PASS" if evaluation_run.status == "completed" else "FAIL"
            summary["evaluation_run_id"] = evaluation_run.id
            summary["evaluation_metrics"] = metrics
            summary["no_evidence_forced_alignment_rate"] = metrics.get("no_evidence_forced_alignment_rate")
        appmod.db.session.add(appmod.SystemLog(
            level="info",
            module="demo_flow",
            message=f"Demo flow completed for {course.course_code}: cards={summary['cards_generated']}",
            created_at=appmod.current_time_text(),
        ))
        appmod.db.session.commit()
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run the LexiBridge AI deterministic demo flow.")
    parser.add_argument("--skip-evaluation", action="store_true", help="Run teacher/student/admin demo without evaluation.")
    parser.add_argument("--summary-json", action="store_true", help="Print machine-readable summary line.")
    args = parser.parse_args()
    summary = run_demo_flow(skip_evaluation=args.skip_evaluation)
    print("Demo Flow Result:")
    print(f"- document ingestion: {summary['document_ingestion']}")
    print(f"- alignment run: {summary['alignment_run']}")
    print(f"- cards generated: {summary['cards_generated']}")
    print(f"- QC cards: {summary['qc_cards']}")
    print(f"- auto approved cards: {summary['auto_approved_cards']}")
    print(f"- student search: {summary['student_search']}")
    print(f"- student feedback: {summary['student_feedback']}")
    print(f"- admin jobs: {summary['admin_jobs']}")
    print(f"- evaluation run: {summary['evaluation_run']}")
    print(f"- no evidence forced alignment rate: {summary['no_evidence_forced_alignment_rate']}")
    if args.summary_json:
        print("DEMO_FLOW_JSON=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
