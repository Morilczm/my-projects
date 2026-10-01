from pathlib import Path

import pytest

from services.storage import LocalStorageBackend, StorageService, compute_sha256, safe_filename


def test_local_storage_save_open_exists_delete_and_safe_url(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Fourier Transform", encoding="utf-8")
    service = StorageService(LocalStorageBackend(str(tmp_path / "storage-root")))

    meta = service.save_file(str(source), "uploaded_document", owner_user_id=1, course_id=2, original_filename="../../notes.txt")

    assert meta["storage_key"].startswith("storage/uploaded_document/")
    assert ".." not in meta["storage_key"]
    assert meta["sha256"] == compute_sha256(meta["absolute_path"])
    assert service.exists(meta["storage_key"])
    with service.open_file(meta["storage_key"], "rb") as handle:
        assert handle.read() == b"Fourier Transform"
    signed = service.get_signed_url(meta["storage_key"])
    assert signed.startswith("/local-storage/")
    assert not signed.startswith(str(tmp_path))
    assert service.delete(meta["storage_key"]) is True
    assert service.exists(meta["storage_key"]) is False


def test_local_storage_rejects_path_escape(tmp_path):
    backend = LocalStorageBackend(str(tmp_path / "root"))
    with pytest.raises(ValueError):
        backend.absolute_path("../escape.txt")


def test_safe_filename_removes_path_and_unsafe_chars():
    assert safe_filename("../../a b中文.pdf").endswith(".pdf")
    assert "/" not in safe_filename("../../a b中文.pdf")
