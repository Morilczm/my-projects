# Object Storage Design

Local uploads are suitable for development but not sufficient for production. PR-11 introduces `StorageService` and `StorageObject` so the application can move from local files to S3-compatible object storage later.

## StorageService

```python
save_file(local_path, purpose, owner_user_id=None, course_id=None, document_id=None)
open_file(storage_key)
get_signed_url(storage_key, expires_in=3600)
exists(storage_key)
delete(storage_key)
compute_sha256(local_path)
```

## LocalStorageBackend

Local files are stored under:

```text
uploads/storage/<purpose>/<yyyy>/<mm>/<uuid>_<safe_filename>
```

The API stores `storage_key`, not server absolute paths.

## S3-Compatible Backend

`S3CompatibleStorageBackend` is a configuration boundary in the Local MVP. It requires:

```text
S3_ENDPOINT_URL
S3_BUCKET
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
S3_REGION
S3_PUBLIC_BASE_URL
```

No real keys are committed. `check_storage_config.py` fails if S3 is selected with placeholder or missing values.

## StorageObject

Fields:

```text
storage_backend, bucket, storage_key, original_filename,
content_type, size_bytes, sha256, owner_user_id,
course_id, document_id, visibility, purpose, status
```

Purposes:

```text
uploaded_document
derived_page_image
derived_formula_image
export_pdf
backup_artifact
demo_asset
```

Visibility:

```text
private
course
admin
public_demo
```

Personal files must stay `private` and preserve `owner_user_id`.
