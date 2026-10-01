import json
from pathlib import Path


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.get_json()["token"]


def test_create_import_and_run_evaluation(app_module, client, teacher_token):
    create_response = client.post(
        "/api/evaluation/sets",
        json={
            "name": "pytest_eval_smoke",
            "discipline": "signal_processing",
            "description": "pytest smoke evaluation",
        },
        headers=auth_header(teacher_token),
    )
    assert create_response.status_code == 200
    set_id = create_response.get_json()["data"]["evaluation_set_id"]

    eval_file = Path(app_module.PROJECT_ROOT) / "tests" / "_tmp_eval_import.jsonl"
    eval_file.write_text(
        "\n".join([
            json.dumps({
                "item_id": "T-001",
                "split": "test",
                "discipline": "signal_processing",
                "english_term": "Fourier Transform",
                "expected_chinese_term": "傅里叶变换",
                "english_context": "Fourier Transform converts a time-domain signal into a frequency-domain representation.",
                "expected_english_evidence": "Fourier Transform represents a signal by frequency components.",
                "expected_chinese_evidence": "傅里叶变换用于将信号表示为频率分量。",
                "expected_alignment_status": "no_en_evidence",
                "negative_english_evidence": "A hash table maps keys to buckets.",
                "negative_chinese_evidence": "哈希表通过哈希函数映射关键字。",
                "difficulty": "easy",
                "tags": ["core_term"],
            }, ensure_ascii=False),
            "{invalid json",
            "",
        ]),
        encoding="utf-8",
    )
    try:
        import_response = client.post(
            "/api/evaluation/items/import",
            json={"evaluation_set_id": set_id, "file_path": "tests/_tmp_eval_import.jsonl"},
            headers=auth_header(teacher_token),
        )
        assert import_response.status_code == 200
        import_data = import_response.get_json()["data"]
        assert import_data["imported_count"] == 1
        assert len(import_data["errors"]) == 1

        items_response = client.get(
            f"/api/evaluation/items?evaluation_set_id={set_id}&split=test",
            headers=auth_header(teacher_token),
        )
        assert items_response.status_code == 200
        assert items_response.get_json()["items"][0]["item_id"] == "T-001"

        run_response = client.post(
            "/api/evaluation/run?sync=true",
            json={"evaluation_set_id": set_id, "split": "test"},
            headers=auth_header(teacher_token),
        )
        assert run_response.status_code == 200
        run_payload = run_response.get_json()["data"]
        assert run_payload["status"] == "completed"
        assert "no_evidence_forced_alignment_rate" in run_payload["metrics"]
        run_id = run_payload["evaluation_run_id"]

        detail_response = client.get(
            f"/api/evaluation/runs/{run_id}",
            headers=auth_header(teacher_token),
        )
        assert detail_response.status_code == 200
        detail = detail_response.get_json()["data"]
        assert detail["report_json"]
        assert "# LexiBridge AI Evaluation Report" in detail["report_markdown"]
        assert detail["input_count"] == 1
    finally:
        try:
            eval_file.unlink()
        except FileNotFoundError:
            pass


def test_evaluation_permissions(app_module, client, teacher_token):
    student_token = login(client, "student.test@lexibridge.local", "Student1234")
    student_response = client.post(
        "/api/evaluation/run?sync=true",
        json={"evaluation_set_id": 1, "split": "test"},
        headers=auth_header(student_token),
    )
    assert student_response.status_code == 403

    with app_module.app.app_context():
        admin = app_module.User(
            username="eval_admin",
            email="eval.admin@lexibridge.local",
            password_hash=app_module.generate_password_hash("Admin1234", method="pbkdf2:sha256"),
            role="admin",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(admin)
        app_module.db.session.commit()
        locked_set = app_module.EvaluationSet(
            name="admin_private_eval",
            discipline="data_structures",
            created_by=admin.id,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        app_module.db.session.add(locked_set)
        app_module.db.session.commit()
        set_id = locked_set.id

    teacher_response = client.post(
        "/api/evaluation/run?sync=true",
        json={"evaluation_set_id": set_id, "split": "test"},
        headers=auth_header(teacher_token),
    )
    assert teacher_response.status_code == 403
