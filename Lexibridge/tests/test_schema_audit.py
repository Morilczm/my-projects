from services.schema_audit import audit_schema


def test_schema_audit_reports_storage_and_index_warnings():
    result = audit_schema({}, {
        "document": ["id", "saved_filename", "course_id", "owner_user_id", "created_at"],
        "terminology_card": ["id", "course_id", "normalized_english_term", "final_chinese_term", "created_at"],
        "background_job": ["id", "status", "priority", "created_at"],
    })
    assert result["status"] == "WARN"
    messages = " ".join(issue["message"] for issue in result["issues"])
    assert "Legacy local path" in messages
    assert "StorageObject table is missing" in messages
