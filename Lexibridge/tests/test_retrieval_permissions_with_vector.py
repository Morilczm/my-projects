def test_student_cannot_request_retrieval_debug(client, student_token, test_course):
    response = client.get(
        f"/api/knowledge/search?q=Fourier&course_id={test_course.id}&language=zh&knowledge_base_type=zh_course_kb&include_debug=true",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert response.status_code == 403


def test_student_cannot_run_retrieval_experiment(client, student_token, test_course):
    response = client.post(
        "/api/admin/retrieval/experiments/run",
        json={"course_id": test_course.id},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert response.status_code in {401, 403}


def test_teacher_can_run_own_course_retrieval_health(client, teacher_token):
    response = client.get(
        "/api/admin/retrieval/health",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert response.status_code == 200
    assert "vector_index_health" in response.get_json()["data"]
