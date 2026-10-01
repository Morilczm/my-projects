from services.storage import validate_storage_config


def test_local_storage_config_passes(tmp_path):
    errors, warnings = validate_storage_config({
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_ROOT": str(tmp_path / "storage"),
        "LOG_REDACT_SECRETS": "true",
    }, app_env="development")
    assert errors == []


def test_s3_missing_config_fails():
    errors, _ = validate_storage_config({
        "STORAGE_BACKEND": "s3",
        "S3_BUCKET": "",
        "S3_ACCESS_KEY_ID": "placeholder",
        "S3_SECRET_ACCESS_KEY": "",
        "LOG_REDACT_SECRETS": "true",
    }, app_env="staging")
    assert any("S3_BUCKET" in error for error in errors)
    assert any("S3_ACCESS_KEY_ID" in error for error in errors)
    assert any("S3_SECRET_ACCESS_KEY" in error for error in errors)


def test_production_local_storage_fails(tmp_path):
    errors, _ = validate_storage_config({
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_ROOT": str(tmp_path / "storage"),
        "LOG_REDACT_SECRETS": "true",
    }, app_env="production")
    assert any("Local storage" in error for error in errors)
