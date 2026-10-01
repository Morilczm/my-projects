#!/usr/bin/env python3
"""Seed deterministic LexiBridge AI demo data for course demos and pilot trials."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo_data"
APP_PATH = ROOT / "backend" / "app.py"
DEMO_EVALUATION_SET_NAME = "lexibridge_demo_gold_v1"


def load_app_module():
    sys.path.insert(0, str(ROOT / "backend"))
    spec = importlib.util.spec_from_file_location("lexibridge_demo_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    rows = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no} invalid JSONL: {exc}") from exc
    return rows


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    return "_".join(part for part in cleaned.split("_") if part)


def chunk_markdown(text: str):
    blocks = []
    current = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        if stripped.startswith("#"):
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        if stripped.startswith("- "):
            if current:
                blocks.append(" ".join(current))
                current = []
            blocks.append(stripped[2:].strip())
        else:
            current.append(stripped)
    if current:
        blocks.append(" ".join(current))
    return [block for block in blocks if len(block) >= 20]


def reset_demo_data(appmod):
    db = appmod.db
    demo_codes = {"DS101", "SP101", "MATH101"}
    courses = appmod.Course.query.filter(appmod.Course.course_code.in_(demo_codes)).all()
    course_ids = [course.id for course in courses]
    demo_users = [
        "admin@lexibridge.local",
        "teacher@lexibridge.local",
        "student@lexibridge.local",
        "student2@lexibridge.local",
    ]
    demo_user_rows = appmod.User.query.filter(appmod.User.email.in_(demo_users)).all()
    user_ids = [user.id for user in demo_user_rows]

    if course_ids:
        for model in [
            appmod.StudentTermRecord,
            appmod.Feedback,
            appmod.TerminologyCard,
            appmod.AlignmentRun,
            appmod.BackgroundJob,
            appmod.BackgroundJobEvent,
            appmod.FormulaBlock,
            appmod.DocumentChunk,
            appmod.KnowledgeChunk,
            appmod.KnowledgeBaseVersion,
            appmod.CourseMember,
        ]:
            if hasattr(model, "course_id"):
                model.query.filter(model.course_id.in_(course_ids)).delete(synchronize_session=False)
    for doc in appmod.Document.query.filter_by(source_type="demo_seed").all():
        appmod.DocumentChunk.query.filter_by(document_id=doc.id).delete(synchronize_session=False)
        appmod.KnowledgeChunk.query.filter_by(document_id=doc.id).delete(synchronize_session=False)
        appmod.FormulaBlock.query.filter_by(document_id=doc.id).delete(synchronize_session=False)
        db.session.delete(doc)
    for source in appmod.KnowledgeSource.query.filter_by(access_method="demo_seed").all():
        appmod.KnowledgeChunk.query.filter_by(source_id=source.id).delete(synchronize_session=False)
        db.session.delete(source)
    for evaluation_set in appmod.EvaluationSet.query.filter_by(name=DEMO_EVALUATION_SET_NAME).all():
        appmod.EvaluationItem.query.filter_by(set_id=evaluation_set.id).delete(synchronize_session=False)
        appmod.EvaluationRun.query.filter_by(evaluation_set_id=evaluation_set.id).delete(synchronize_session=False)
        db.session.delete(evaluation_set)
    if course_ids:
        appmod.Course.query.filter(appmod.Course.id.in_(course_ids)).delete(synchronize_session=False)
    if user_ids:
        for email in ["student2@lexibridge.local"]:
            user = appmod.User.query.filter_by(email=email).first()
            if user:
                db.session.delete(user)
    db.session.commit()


def upsert_user(appmod, spec, stats):
    user = appmod.User.query.filter_by(email=spec["email"]).first()
    created = False
    if user is None:
        user = appmod.User(
            username=spec["username"],
            email=spec["email"],
            created_at=appmod.current_time_text(),
        )
        appmod.db.session.add(user)
        created = True
        stats["users_created"] += 1
    user.username = spec["username"]
    user.role = spec["role"]
    user.display_name = spec.get("display_name", spec["username"])
    user.password_hash = appmod.generate_password_hash(spec["password"], method="pbkdf2:sha256")
    user.is_verified = True
    user.verification_token = ""
    user.reset_token = ""
    if not created:
        stats["users_updated"] += 1
    return user


def ensure_plan_subscription(appmod, student_user, stats):
    plan = appmod.SubscriptionPlan.query.filter_by(name="Basic").first()
    if plan is None:
        plan = appmod.SubscriptionPlan(
            name="Basic",
            price_monthly=10,
            monthly_pages=100,
            monthly_ai_calls=300,
            export_enabled=True,
            description="Demo Basic plan",
            is_active=True,
        )
        appmod.db.session.add(plan)
        appmod.db.session.flush()
    existing = appmod.UserSubscription.query.filter_by(user_id=student_user.id, status="active").first()
    if existing is None:
        appmod.db.session.add(appmod.UserSubscription(
            user_id=student_user.id,
            plan_id=plan.id,
            start_date=appmod.current_time_text(),
            end_date="",
            status="active",
            auto_renew=False,
        ))
        appmod.db.session.add(appmod.BillingRecord(
            user_id=student_user.id,
            plan_id=plan.id,
            amount=plan.price_monthly,
            payment_method="mock_payment",
            payment_status="paid",
            created_at=appmod.current_time_text(),
        ))
        stats["subscriptions_created"] += 1


def upsert_course(appmod, course_spec, teacher, stats):
    course = appmod.Course.query.filter_by(course_code=course_spec["course_code"]).first()
    if course is None:
        course = appmod.Course.query.filter_by(name=course_spec["course_name"]).first()
    if course is None:
        course = appmod.Course(
            name=course_spec["course_name"],
            course_code=course_spec["course_code"],
            created_at=appmod.current_time_text(),
        )
        appmod.db.session.add(course)
        stats["courses_created"] += 1
    else:
        stats["courses_updated"] += 1
    course.name = course_spec["course_name"]
    course.course_code = course_spec["course_code"]
    course.semester = course_spec.get("semester", "Demo 2026")
    course.description = f"{course_spec.get('description', '')} demo_seed=true"
    course.language_mode = course_spec.get("language_mode", "bilingual")
    course.teacher_id = teacher.id
    course.status = "active"
    return course


def upsert_member(appmod, course, user, role, stats):
    member = appmod.CourseMember.query.filter_by(course_id=course.id, user_id=user.id).first()
    if member is None:
        member = appmod.CourseMember(
            course_id=course.id,
            user_id=user.id,
            created_at=appmod.current_time_text(),
        )
        appmod.db.session.add(member)
        stats["members_created"] += 1
    member.role = role
    member.role_in_course = role
    member.status = "active"
    member.joined_at = member.joined_at or appmod.current_time_text()


def upsert_knowledge_source(appmod, name, language, discipline, created_by):
    source = appmod.KnowledgeSource.query.filter_by(name=name, access_method="demo_seed").first()
    if source is None:
        source = appmod.KnowledgeSource(name=name, access_method="demo_seed", created_at=appmod.current_time_text())
        appmod.db.session.add(source)
        appmod.db.session.flush()
    source.language = language
    source.discipline = discipline
    source.source_type = "platform_seed"
    source.license_status = "open_licensed"
    source.update_frequency = "manual"
    source.allow_full_text_indexing = True
    source.allow_student_search = True
    source.allow_derivative_cards = True
    source.created_by = created_by
    source.updated_at = appmod.current_time_text()
    return source


def upsert_document_with_chunks(appmod, course, user, source, rel_path, language, kb_type, discipline, stats):
    path = DEMO_DIR / rel_path
    text = path.read_text(encoding="utf-8")
    filename = path.name
    document = appmod.Document.query.filter_by(
        course_id=course.id,
        filename=filename,
        source_type="demo_seed",
    ).first()
    if document is None:
        document = appmod.Document(
            owner_user_id=user.id,
            course_id=course.id,
            filename=filename,
            source_type="demo_seed",
            upload_time=appmod.current_time_text(),
        )
        appmod.db.session.add(document)
        appmod.db.session.flush()
        stats["documents_created"] += 1
    else:
        appmod.DocumentChunk.query.filter_by(document_id=document.id).delete(synchronize_session=False)
        appmod.KnowledgeChunk.query.filter_by(document_id=document.id).delete(synchronize_session=False)
        stats["documents_updated"] += 1
    document.scope_type = "course"
    document.saved_filename = f"demo_seed/{rel_path}"
    document.file_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    document.file_type = path.suffix.lstrip(".")
    document.language = language
    document.parsing_status = "parsed"
    document.ocr_required = False
    document.ocr_status = "not_required"
    document.ocr_provider = "none"
    document.quality_flags_json = json.dumps(["demo_seed"], ensure_ascii=False)
    document.parsed_text = text
    document.error_message = ""

    chunks = chunk_markdown(text)
    for index, content in enumerate(chunks, 1):
        citation = f"demo_seed=true; {course.course_code}; {filename}; chunk {index}"
        appmod.db.session.add(appmod.DocumentChunk(
            document_id=document.id,
            course_id=course.id,
            user_id=user.id,
            owner_user_id=user.id,
            chunk_index=index,
            language=language,
            section_title=filename,
            content=content,
            source_type="demo_seed",
            source_location=citation,
            ocr_confidence=100,
            ocr_provider="none",
            ocr_status="not_required",
            quality_flags_json=json.dumps(["demo_seed"], ensure_ascii=False),
            created_at=appmod.current_time_text(),
        ))
        appmod.db.session.add(appmod.KnowledgeChunk(
            document_id=document.id,
            source_id=source.id,
            course_id=course.id,
            course=course.name,
            title=filename,
            discipline=discipline,
            chapter="demo",
            chunk_index=index,
            content=content,
            source_page=f"chunk {index}",
            page_number=index,
            keywords="",
            source_citation=citation,
            language=language,
            knowledge_base_type=kb_type,
            owner_user_id=str(user.id),
            visibility="course",
            created_at=appmod.current_time_text(),
        ))
        stats["knowledge_chunks_created"] += 1
    stats["document_chunks_created"] += len(chunks)
    return document, len(chunks)


def upsert_media_document(appmod, course, user, rel_path, language, parsing_status, formula=False, stats=None):
    path = DEMO_DIR / rel_path
    document = appmod.Document.query.filter_by(course_id=course.id, filename=path.name, source_type="demo_seed").first()
    if document is None:
        document = appmod.Document(
            owner_user_id=user.id,
            course_id=course.id,
            filename=path.name,
            source_type="demo_seed",
            upload_time=appmod.current_time_text(),
        )
        appmod.db.session.add(document)
        appmod.db.session.flush()
        if stats is not None:
            stats["documents_created"] += 1
    else:
        appmod.FormulaBlock.query.filter_by(document_id=document.id).delete(synchronize_session=False)
        if stats is not None:
            stats["documents_updated"] += 1
    document.scope_type = "course"
    document.saved_filename = f"demo_seed/{rel_path}"
    document.file_type = path.suffix.lstrip(".")
    document.language = language
    document.parsing_status = parsing_status
    document.ocr_required = True
    document.ocr_status = "ocr_unavailable"
    document.ocr_provider = "none"
    document.ocr_error = "Demo asset requires a configured OCR engine for live recognition."
    flags = ["demo_seed", "ocr_sensitive"]
    if formula:
        flags.append("formula_related")
    document.quality_flags_json = json.dumps(flags, ensure_ascii=False)
    document.parsed_text = ""
    document.error_message = document.ocr_error
    if formula:
        appmod.db.session.add(appmod.FormulaBlock(
            document_id=document.id,
            course_id=course.id,
            owner_user_id=user.id,
            scope_type="course",
            page_number=1,
            bbox_json=json.dumps({"x": 0, "y": 0, "width": 1, "height": 1}, ensure_ascii=False),
            image_path=f"demo_seed/{rel_path}",
            latex="",
            plain_text="",
            provider="none",
            confidence=0,
            status="needs_formula_ocr_engine",
            error="Demo formula region detected; configure FORMULA_OCR_PROVIDER to recognize LaTeX.",
            quality_flags_json=json.dumps(["demo_seed", "formula_related"], ensure_ascii=False),
            created_at=appmod.current_time_text(),
        ))
        if stats is not None:
            stats["formula_blocks_created"] += 1
    return document


def upsert_kb_version(appmod, course, user, source_count, chunk_count):
    version_name = f"demo-{course.course_code.lower()}-v1"
    version = appmod.KnowledgeBaseVersion.query.filter_by(course_id=course.id, version_name=version_name).first()
    if version is None:
        version = appmod.KnowledgeBaseVersion(
            course_id=course.id,
            version_name=version_name,
            created_at=appmod.current_time_text(),
        )
        appmod.db.session.add(version)
    version.kb_scope = "course"
    version.owner_user_id = user.id
    version.description = f"Self-authored demo KB version for {course.course_code}; demo_seed=true"
    version.source_count = source_count
    version.chunk_count = chunk_count
    version.created_by = user.id
    version.is_active = True


def upsert_evaluation_items(appmod, courses_by_code, admin, stats):
    evaluation_set = appmod.EvaluationSet.query.filter_by(name=DEMO_EVALUATION_SET_NAME).first()
    if evaluation_set is None:
        evaluation_set = appmod.EvaluationSet(
            name=DEMO_EVALUATION_SET_NAME,
            created_by=admin.id,
            created_at=appmod.current_time_text(),
        )
        appmod.db.session.add(evaluation_set)
        appmod.db.session.flush()
        stats["evaluation_sets_created"] += 1
    else:
        appmod.EvaluationItem.query.filter_by(set_id=evaluation_set.id).delete(synchronize_session=False)
        stats["evaluation_sets_updated"] += 1
    evaluation_set.course_id = None
    evaluation_set.discipline = "multi_course_demo"
    evaluation_set.description = "Self-authored 60+ item demo gold set for LexiBridge AI pilot trials. demo_seed=true"
    evaluation_set.split = "test"
    evaluation_set.locked = True
    evaluation_set.is_locked = True
    evaluation_set.updated_at = appmod.current_time_text()

    items = []
    for file_path in sorted(DEMO_DIR.glob("*/gold_terms.jsonl")):
        items.extend(read_jsonl(file_path))
    for row in items:
        course = courses_by_code.get(row["course_code"])
        appmod.db.session.add(appmod.EvaluationItem(
            set_id=evaluation_set.id,
            evaluation_set_id=evaluation_set.id,
            item_id=row["item_id"],
            split=row.get("split", "test"),
            discipline=row.get("discipline", ""),
            course_id=course.id if course else None,
            english_term=row["english_term"],
            expected_chinese_term=row.get("expected_chinese_term", ""),
            expected_alignment_status=row.get("expected_alignment_status", ""),
            english_context=row.get("english_context", ""),
            english_evidence=row.get("expected_english_evidence", ""),
            chinese_evidence=row.get("expected_chinese_evidence", ""),
            expected_english_evidence=row.get("expected_english_evidence", ""),
            expected_chinese_evidence=row.get("expected_chinese_evidence", ""),
            negative_english_evidence=row.get("negative_english_evidence", ""),
            negative_chinese_evidence=row.get("negative_chinese_evidence", ""),
            difficulty=row.get("difficulty", "medium"),
            tags_json=json.dumps(row.get("tags", []), ensure_ascii=False),
            annotator="demo_seed",
            reviewed_by="demo_seed",
            version=row.get("version", "demo_v1"),
            created_at=appmod.current_time_text(),
        ))
    stats["evaluation_items_imported"] = len(items)
    return evaluation_set


def seed_demo_data(reset=False):
    appmod = load_app_module()
    stats = {
        "users_created": 0,
        "users_updated": 0,
        "subscriptions_created": 0,
        "courses_created": 0,
        "courses_updated": 0,
        "members_created": 0,
        "documents_created": 0,
        "documents_updated": 0,
        "document_chunks_created": 0,
        "knowledge_chunks_created": 0,
        "formula_blocks_created": 0,
        "evaluation_sets_created": 0,
        "evaluation_sets_updated": 0,
        "evaluation_items_imported": 0,
    }
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        if reset:
            reset_demo_data(appmod)

        users_by_email = {}
        for user_spec in read_json(DEMO_DIR / "users.json"):
            user = upsert_user(appmod, user_spec, stats)
            users_by_email[user.email] = user
        appmod.db.session.flush()
        teacher = users_by_email["teacher@lexibridge.local"]
        student = users_by_email["student@lexibridge.local"]
        student2 = users_by_email["student2@lexibridge.local"]
        admin = users_by_email["admin@lexibridge.local"]
        ensure_plan_subscription(appmod, student, stats)

        courses_by_code = {}
        for course_spec in read_json(DEMO_DIR / "courses.json"):
            course = upsert_course(appmod, course_spec, teacher, stats)
            courses_by_code[course.course_code] = course
        appmod.db.session.flush()

        for course in courses_by_code.values():
            upsert_member(appmod, course, teacher, "teacher", stats)
            upsert_member(appmod, course, student, "student", stats)
        upsert_member(appmod, courses_by_code["DS101"], student2, "student", stats)

        course_specs = {row["course_code"]: row for row in read_json(DEMO_DIR / "courses.json")}
        sources_by_course = {}
        for code, course in courses_by_code.items():
            spec = course_specs[code]
            discipline = spec["discipline"]
            source_en = upsert_knowledge_source(appmod, f"Demo {code} English Course Notes", "en", discipline, teacher.id)
            source_zh = upsert_knowledge_source(appmod, f"Demo {code} Chinese Reference", "zh", discipline, teacher.id)
            sources_by_course[code] = (source_en, source_zh)

        chunk_counts = {code: 0 for code in courses_by_code}
        doc_map = {
            "DS101": ("data_structures/english_course_notes.md", "data_structures/chinese_reference.md"),
            "SP101": ("signal_processing/english_course_notes.md", "signal_processing/chinese_reference.md"),
            "MATH101": ("engineering_math/english_course_notes.md", "engineering_math/chinese_reference.md"),
        }
        media_map = {
            "DS101": [
                ("data_structures/image_text_sample.png", "bilingual", "needs_ocr_engine", False),
                ("data_structures/formula_sample.png", "en", "needs_formula_ocr_engine", True),
            ],
            "SP101": [
                ("signal_processing/mixed_pdf_sample.pdf", "bilingual", "needs_formula_ocr_engine", True),
                ("signal_processing/formula_sample.png", "en", "needs_formula_ocr_engine", True),
            ],
            "MATH101": [
                ("engineering_math/formula_sample.png", "en", "needs_formula_ocr_engine", True),
            ],
        }
        for code, course in courses_by_code.items():
            spec = course_specs[code]
            source_en, source_zh = sources_by_course[code]
            _, count_en = upsert_document_with_chunks(
                appmod, course, teacher, source_en, doc_map[code][0], "en", "en_course_kb", spec["discipline"], stats
            )
            _, count_zh = upsert_document_with_chunks(
                appmod, course, teacher, source_zh, doc_map[code][1], "zh", "zh_course_kb", spec["discipline"], stats
            )
            chunk_counts[code] += count_en + count_zh
            for rel_path, language, parsing_status, formula in media_map[code]:
                upsert_media_document(appmod, course, teacher, rel_path, language, parsing_status, formula, stats)
            upsert_kb_version(appmod, course, teacher, 2, chunk_counts[code])

        evaluation_set = upsert_evaluation_items(appmod, courses_by_code, admin, stats)
        appmod.db.session.add(appmod.SystemLog(
            level="info",
            module="demo_seed",
            message=f"Demo data seeded for {len(courses_by_code)} courses and {stats['evaluation_items_imported']} evaluation items.",
            created_at=appmod.current_time_text(),
        ))
        appmod.db.session.commit()
        stats["evaluation_set_id"] = evaluation_set.id
        stats["courses_total"] = len(courses_by_code)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Seed LexiBridge AI demo data.")
    parser.add_argument("--reset-demo", action="store_true", help="Remove existing demo_seed data before seeding.")
    parser.add_argument("--summary-json", action="store_true", help="Print machine-readable summary line.")
    args = parser.parse_args()
    stats = seed_demo_data(reset=args.reset_demo)
    print("Demo Seed Result:")
    print(f"- Created users: {stats['users_created']} (updated {stats['users_updated']})")
    print(f"- Created courses: {stats['courses_created']} (updated {stats['courses_updated']})")
    print(f"- Created documents: {stats['documents_created']} (updated {stats['documents_updated']})")
    print(f"- Created document chunks: {stats['document_chunks_created']}")
    print(f"- Created knowledge chunks: {stats['knowledge_chunks_created']}")
    print(f"- Created formula blocks: {stats['formula_blocks_created']}")
    print(f"- Created evaluation items: {stats['evaluation_items_imported']}")
    print(f"- Evaluation set id: {stats['evaluation_set_id']}")
    if args.summary_json:
        print("DEMO_SEED_JSON=" + json.dumps(stats, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
