from pathlib import Path

from services.storage import compute_sha256


def test_storage_integrity_detects_missing_and_hash_mismatch(app_module, tmp_path):
    with app_module.app.app_context():
        service = app_module.storage_service()
        source = tmp_path / "artifact.txt"
        source.write_text("artifact", encoding="utf-8")
        meta = service.save_file(str(source), "uploaded_document", owner_user_id=1, original_filename="artifact.txt")
        obj = app_module.StorageObject(
            storage_backend=meta["storage_backend"],
            bucket=meta["bucket"],
            storage_key=meta["storage_key"],
            original_filename="artifact.txt",
            content_type=meta["content_type"],
            size_bytes=meta["size_bytes"],
            sha256=meta["sha256"],
            owner_user_id=1,
            visibility="private",
            purpose="uploaded_document",
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(obj)
        app_module.db.session.commit()
        assert service.exists(obj.storage_key)
        path = service.absolute_path(obj.storage_key)
        assert compute_sha256(path) == obj.sha256
        Path(path).write_text("changed", encoding="utf-8")
        assert compute_sha256(path) != obj.sha256
        Path(path).unlink()
        assert not service.exists(obj.storage_key)
