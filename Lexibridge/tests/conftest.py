import importlib.util
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


@pytest.fixture(scope="session")
def app_module(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("lexibridge-data")
    upload_dir = tmp_path_factory.mktemp("lexibridge-uploads")
    os.environ["DATABASE_URL"] = f"sqlite:///{data_dir / 'test.db'}"
    os.environ["UPLOAD_FOLDER"] = str(upload_dir)
    os.environ["AUTH_REQUIRED"] = "True"
    os.environ["AI_PROVIDER"] = "none"
    os.environ["ALLOW_MOCK_AI"] = "True"
    os.environ["OCR_PROVIDER"] = "none"
    os.environ["FORMULA_OCR_PROVIDER"] = "none"
    os.environ["LEXIBRIDGE_SKIP_ENV_FILE"] = "true"
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["ANTHROPIC_API_KEY"] = ""

    spec = importlib.util.spec_from_file_location("lexibridge_test_app", BACKEND / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with module.app.app_context():
        module.db.create_all()
        module.ensure_schema_columns()
        teacher = module.User(
            username="test_teacher",
            email="teacher.test@lexibridge.local",
            password_hash=module.generate_password_hash("Teacher1234", method="pbkdf2:sha256"),
            role="teacher",
            is_verified=True,
            created_at=module.current_time_text()
        )
        student = module.User(
            username="test_student",
            email="student.test@lexibridge.local",
            password_hash=module.generate_password_hash("Student1234", method="pbkdf2:sha256"),
            role="student",
            is_verified=True,
            created_at=module.current_time_text()
        )
        admin = module.User(
            username="test_admin",
            email="admin.test@lexibridge.local",
            password_hash=module.generate_password_hash("Admin1234", method="pbkdf2:sha256"),
            role="admin",
            is_verified=True,
            created_at=module.current_time_text()
        )
        module.db.session.add_all([teacher, student, admin])
        module.db.session.commit()
        course = module.Course(
            name="OCR Test Course",
            course_code="OCR-101",
            teacher_id=teacher.id,
            created_at=module.current_time_text()
        )
        module.db.session.add(course)
        module.db.session.commit()
        module.db.session.add(module.CourseMember(
            course_id=course.id,
            user_id=teacher.id,
            role="teacher",
            role_in_course="teacher",
            created_at=module.current_time_text(),
            joined_at=module.current_time_text()
        ))
        module.db.session.add(module.SubscriptionPlan(
            name="Free",
            price_monthly=0,
            monthly_pages=5,
            monthly_ai_calls=20,
            export_enabled=False,
            description="Test free plan",
            is_active=True
        ))
        module.db.session.commit()

    module.app.config["TESTING"] = True
    return module


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture()
def teacher_token(client):
    response = client.post("/api/auth/login", json={
        "email": "teacher.test@lexibridge.local",
        "password": "Teacher1234"
    })
    assert response.status_code == 200
    return response.get_json()["token"]


@pytest.fixture()
def student_token(client):
    response = client.post("/api/auth/login", json={
        "email": "student.test@lexibridge.local",
        "password": "Student1234"
    })
    assert response.status_code == 200
    return response.get_json()["token"]


@pytest.fixture()
def admin_token(client):
    response = client.post("/api/auth/login", json={
        "email": "admin.test@lexibridge.local",
        "password": "Admin1234"
    })
    assert response.status_code == 200
    return response.get_json()["token"]


@pytest.fixture()
def test_course(app_module):
    with app_module.app.app_context():
        return app_module.Course.query.filter_by(name="OCR Test Course").first()


@pytest.fixture()
def tiny_png_bytes():
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA"
        b"\xe2!\xbc\x00\x00\x00\x00IEND\xaeB`\x82"
    )
