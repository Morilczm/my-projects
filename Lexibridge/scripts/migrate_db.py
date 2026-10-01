from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


SEED_COURSES = [
    "Data Structures and Algorithms",
    "Electronic System Fundamentals",
    "Basic Physics I",
    "Advanced Mathematics",
    "Introduction to Computing",
    "Telecommunications Engineering",
    "Management",
]


SEED_USERS = [
    ("admin", "admin@lexibridge.local", "Admin1234", "admin"),
    ("teacher", "teacher@lexibridge.local", "Teacher1234", "teacher"),
    ("student", "student@lexibridge.local", "Student1234", "student"),
]


SEED_PLANS = [
    ("Free", 0, 5, 20, False, "Free Plan: 5 pages and 20 AI/search units per month."),
    ("Basic", 10, 100, 300, True, "Basic Plan: 10 yuan/month, 100 pages and 300 AI/search units."),
    ("Pro", 39, 500, 2000, True, "Pro Plan: 39 yuan/month, 500 pages and 2000 AI/search units."),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run LexiBridge database migration and local seed initialization.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Explicitly apply database migrations and seed initialization.",
    )
    return parser


def _load_app_module():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    import app as app_module  # noqa: PLC0415

    return app_module


def run_migration() -> None:
    app_module = _load_app_module()
    with app_module.app.app_context():
        app_module.db.create_all()
        app_module.ensure_schema_columns()

        created_users = 0
        for username, email, password, role in SEED_USERS:
            user = app_module.User.query.filter_by(email=email).first()
            if user is None:
                user = app_module.User(
                    username=username,
                    email=email,
                    password_hash=app_module.generate_password_hash(password, method="pbkdf2:sha256"),
                    role=role,
                    display_name=username.title(),
                    is_verified=True,
                    created_at=app_module.current_time_text()
                )
                app_module.db.session.add(user)
                created_users += 1
            else:
                user.role = role
                user.is_verified = True

        app_module.db.session.commit()

        teacher = app_module.User.query.filter_by(email="teacher@lexibridge.local").first()
        admin = app_module.User.query.filter_by(email="admin@lexibridge.local").first()

        created = 0
        for course_name in SEED_COURSES:
            course = app_module.Course.query.filter_by(name=course_name).first()
            if course is None:
                app_module.db.session.add(app_module.Course(
                    name=course_name,
                    course_code=course_name.upper().replace(" ", "-")[:30],
                    semester="2026 Spring",
                    description="Seed course workspace for LexiBridge AI bilingual course knowledge alignment.",
                    language_mode="bilingual",
                    teacher_id=teacher.id if teacher else 0,
                    created_at=app_module.current_time_text()
                ))
                created += 1

        app_module.db.session.commit()

        for course in app_module.Course.query.all():
            if teacher and app_module.CourseMember.query.filter_by(course_id=course.id, user_id=teacher.id).first() is None:
                app_module.db.session.add(app_module.CourseMember(
                    course_id=course.id,
                    user_id=teacher.id,
                    role="teacher",
                    role_in_course="teacher",
                    created_at=app_module.current_time_text(),
                    joined_at=app_module.current_time_text()
                ))
            student = app_module.User.query.filter_by(email="student@lexibridge.local").first()
            if student and app_module.CourseMember.query.filter_by(course_id=course.id, user_id=student.id).first() is None:
                app_module.db.session.add(app_module.CourseMember(
                    course_id=course.id,
                    user_id=student.id,
                    role="student",
                    role_in_course="student",
                    created_at=app_module.current_time_text(),
                    joined_at=app_module.current_time_text()
                ))

        created_plans = 0
        for name, price, pages, ai_calls, export_enabled, description in SEED_PLANS:
            plan = app_module.SubscriptionPlan.query.filter_by(name=name).first()
            if plan is None:
                app_module.db.session.add(app_module.SubscriptionPlan(
                    name=name,
                    price_monthly=price,
                    monthly_pages=pages,
                    monthly_ai_calls=ai_calls,
                    export_enabled=export_enabled,
                    description=description,
                    is_active=True
                ))
                created_plans += 1
            else:
                plan.price_monthly = price
                plan.monthly_pages = pages
                plan.monthly_ai_calls = ai_calls
                plan.export_enabled = export_enabled
                plan.description = description
                plan.is_active = True

        if app_module.KnowledgeSource.query.count() == 0:
            app_module.db.session.add(app_module.KnowledgeSource(
                name="LexiBridge Seed Bilingual Discipline KB",
                language="bilingual",
                discipline="Computer Science / Physics",
                source_type="platform_seed",
                access_method="mock_source",
                license_status="open_licensed",
                update_frequency="manual",
                allow_full_text_indexing=True,
                allow_student_search=True,
                allow_derivative_cards=True,
                created_by=admin.id if admin else 0,
                created_at=app_module.current_time_text(),
                updated_at=app_module.current_time_text()
            ))

        if app_module.KnowledgeBaseVersion.query.count() == 0:
            app_module.db.session.add(app_module.KnowledgeBaseVersion(
                kb_scope="global",
                course_id=None,
                owner_user_id=None,
                version_name="global-seed-v1",
                description="Initial local demo seed knowledge base version.",
                source_count=1,
                chunk_count=len(app_module.DEMO_KB_ENTRIES),
                created_at=app_module.current_time_text(),
                created_by=admin.id if admin else 0,
                is_active=True
            ))

        app_module.ensure_model_registry_seed(owner_user_id=admin.id if admin else 0)
        app_module.ensure_ai_registry_seed(owner_user_id=admin.id if admin else 0)

        app_module.db.session.commit()
        kb_created = app_module.seed_demo_knowledge_base()
        print(
            "database migrated; "
            f"seed_users_created={created_users}; "
            f"seed_courses_created={created}; "
            f"seed_plans_created={created_plans}; "
            f"demo_kb_created={kb_created}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("database migration requires explicit --apply")
    run_migration()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
