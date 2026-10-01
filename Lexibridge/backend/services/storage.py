import hashlib
import mimetypes
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


STORAGE_BACKENDS = {"local", "s3"}
STORAGE_PURPOSES = {
    "uploaded_document",
    "derived_page_image",
    "derived_formula_image",
    "export_pdf",
    "backup_artifact",
    "demo_asset",
}


def safe_filename(name: str) -> str:
    base = os.path.basename(str(name or "file"))
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return base or "file"


def compute_sha256(local_path: str) -> str:
    digest = hashlib.sha256()
    with open(local_path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def content_type_for(path: str, fallback: str = "application/octet-stream") -> str:
    return mimetypes.guess_type(path)[0] or fallback


@dataclass
class StorageSaveResult:
    storage_backend: str
    bucket: str
    storage_key: str
    absolute_path: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    purpose: str

    def as_dict(self) -> dict:
        return {
            "storage_backend": self.storage_backend,
            "bucket": self.bucket,
            "storage_key": self.storage_key,
            "absolute_path": self.absolute_path,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "purpose": self.purpose,
        }


class LocalStorageBackend:
    def __init__(self, root: str, bucket: str = "local"):
        self.root = Path(root).expanduser().resolve()
        self.bucket = bucket
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if candidate != self.root and not str(candidate).startswith(str(self.root) + os.sep):
            raise ValueError("storage_key escapes storage root")
        return candidate

    def save_file(self, local_path: str, purpose: str, original_filename: str = "") -> StorageSaveResult:
        if purpose not in STORAGE_PURPOSES:
            raise ValueError(f"Unsupported storage purpose: {purpose}")
        source = Path(local_path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Source file not found: {local_path}")
        safe_name = safe_filename(original_filename or source.name)
        now = datetime.utcnow()
        storage_key = f"storage/{purpose}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}_{safe_name}"
        destination = self._resolve_key(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return StorageSaveResult(
            storage_backend="local",
            bucket=self.bucket,
            storage_key=storage_key,
            absolute_path=str(destination),
            original_filename=safe_name,
            content_type=content_type_for(safe_name),
            size_bytes=destination.stat().st_size,
            sha256=compute_sha256(str(destination)),
            purpose=purpose,
        )

    def open_file(self, storage_key: str, mode: str = "rb"):
        return open(self._resolve_key(storage_key), mode)

    def exists(self, storage_key: str) -> bool:
        try:
            return self._resolve_key(storage_key).exists()
        except ValueError:
            return False

    def absolute_path(self, storage_key: str) -> str:
        path = self._resolve_key(storage_key)
        if not path.exists():
            raise FileNotFoundError(storage_key)
        return str(path)

    def get_signed_url(self, storage_key: str, expires_in: int = 3600) -> str:
        # Local MVP returns a controlled pseudo URL instead of exposing a server path.
        self._resolve_key(storage_key)
        return f"/local-storage/{storage_key}?expires_in={int(expires_in)}"

    def delete(self, storage_key: str) -> bool:
        path = self._resolve_key(storage_key)
        if path.exists():
            path.unlink()
            return True
        return False


class S3CompatibleStorageBackend:
    def __init__(self, **config):
        self.config = config

    def _not_configured(self):
        raise NotImplementedError("S3-compatible storage is a configuration boundary in this Local MVP.")

    save_file = open_file = exists = absolute_path = get_signed_url = delete = _not_configured


class StorageService:
    def __init__(self, backend=None):
        self.backend = backend or build_storage_backend_from_env()

    def save_file(self, local_path: str, purpose: str, owner_user_id=None, course_id=None, document_id=None, original_filename: str = "") -> dict:
        result = self.backend.save_file(local_path, purpose, original_filename=original_filename)
        data = result.as_dict()
        data.update({
            "owner_user_id": owner_user_id,
            "course_id": course_id,
            "document_id": document_id,
        })
        return data

    def open_file(self, storage_key: str, mode: str = "rb"):
        return self.backend.open_file(storage_key, mode)

    def exists(self, storage_key: str) -> bool:
        return self.backend.exists(storage_key)

    def absolute_path(self, storage_key: str) -> str:
        return self.backend.absolute_path(storage_key)

    def get_signed_url(self, storage_key: str, expires_in: int = 3600) -> str:
        return self.backend.get_signed_url(storage_key, expires_in=expires_in)

    def delete(self, storage_key: str) -> bool:
        return self.backend.delete(storage_key)

    def compute_sha256(self, local_path: str) -> str:
        return compute_sha256(local_path)


def build_storage_backend_from_env(env=None):
    env = env or os.environ
    backend = str(env.get("STORAGE_BACKEND", "local")).strip().lower() or "local"
    if backend == "local":
        root = env.get("LOCAL_STORAGE_ROOT") or env.get("UPLOAD_FOLDER") or env.get("UPLOAD_DIR") or "uploads"
        return LocalStorageBackend(root)
    if backend == "s3":
        return S3CompatibleStorageBackend(
            endpoint_url=env.get("S3_ENDPOINT_URL", ""),
            bucket=env.get("S3_BUCKET", ""),
            access_key_id=env.get("S3_ACCESS_KEY_ID", ""),
            secret_access_key=env.get("S3_SECRET_ACCESS_KEY", ""),
            region=env.get("S3_REGION", ""),
            public_base_url=env.get("S3_PUBLIC_BASE_URL", ""),
        )
    raise ValueError(f"Unsupported STORAGE_BACKEND: {backend}")


def validate_storage_config(env=None, app_env: str = "development") -> tuple[list[str], list[str]]:
    env = env or os.environ
    app_env = str(app_env or env.get("APP_ENV", "development")).lower()
    backend = str(env.get("STORAGE_BACKEND", "local")).strip().lower() or "local"
    errors = []
    warnings = []
    placeholders = {"", "your-access-key", "your-secret-key", "placeholder", "sk-xxx", "change-me"}
    if backend not in STORAGE_BACKENDS:
        errors.append(f"Unsupported STORAGE_BACKEND: {backend}")
        return errors, warnings
    if backend == "local":
        root = Path(env.get("LOCAL_STORAGE_ROOT") or env.get("UPLOAD_FOLDER") or env.get("UPLOAD_DIR") or "uploads").expanduser()
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / ".storage-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except Exception as exc:
            errors.append(f"LOCAL_STORAGE_ROOT is not writable: {root} ({exc})")
        if app_env == "production":
            errors.append("Local storage is not acceptable as the only production storage backend.")
    if backend == "s3":
        required = ["S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]
        for key in required:
            value = str(env.get(key, "")).strip()
            if value.lower() in placeholders or "your-" in value.lower():
                errors.append(f"{key} is required for STORAGE_BACKEND=s3 and must not be a placeholder.")
        if not (env.get("S3_REGION") or env.get("S3_ENDPOINT_URL")):
            errors.append("S3_REGION or S3_ENDPOINT_URL is required for STORAGE_BACKEND=s3.")
    if str(env.get("LOG_REDACT_SECRETS", "true")).lower() == "false":
        errors.append("LOG_REDACT_SECRETS must remain true when storage credentials are configured.")
    return errors, warnings
