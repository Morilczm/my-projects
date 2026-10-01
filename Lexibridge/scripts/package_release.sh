#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
RELEASE_VERSION="${RELEASE_VERSION:-v0.8}"
RELEASE_DATE="${RELEASE_DATE:-$(date +%Y%m%d)}"
RELEASE_NAME="LexiBridge-AI-Local-MVP-${RELEASE_VERSION}-${RELEASE_DATE}"
STAGE_DIR="$DIST_DIR/$RELEASE_NAME"
ZIP_PATH="$DIST_DIR/$RELEASE_NAME.zip"
PYTHON_BIN="$ROOT_DIR/backend/.venv-macos/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN_OVERRIDE:-python3}"
fi
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/lexibridge-pycache}"

"$PYTHON_BIN" -m py_compile "$ROOT_DIR/backend/app.py" "$ROOT_DIR/scripts/migrate_db.py"
"$PYTHON_BIN" -m py_compile "$ROOT_DIR"/backend/services/*.py

if [ "${RUN_PACKAGE_TESTS:-1}" = "1" ]; then
  "$PYTHON_BIN" -m pytest \
    "$ROOT_DIR/tests/test_api_contract.py" \
    "$ROOT_DIR/tests/test_frontend_contract.py" \
    "$ROOT_DIR/tests/test_auth.py" \
    "$ROOT_DIR/tests/test_permissions.py" \
    "$ROOT_DIR/tests/test_upload_security.py" \
    "$ROOT_DIR/tests/test_personal_privacy.py" \
    "$ROOT_DIR/tests/test_migrations.py" \
    "$ROOT_DIR/tests/test_jobs.py" \
    "$ROOT_DIR/tests/test_job_api.py" \
    "$ROOT_DIR/tests/test_worker.py" \
    "$ROOT_DIR/tests/test_demo_seed.py" \
    "$ROOT_DIR/tests/test_demo_flow.py" \
    "$ROOT_DIR/tests/test_demo_evaluation.py" \
    "$ROOT_DIR/tests/test_env_config.py" \
    "$ROOT_DIR/tests/test_logging_safety.py" \
    "$ROOT_DIR/tests/test_backup_restore.py" \
    "$ROOT_DIR/tests/test_cost_control.py" \
    "$ROOT_DIR/tests/test_production_readiness.py" \
    "$ROOT_DIR/tests/test_storage_service.py" \
    "$ROOT_DIR/tests/test_storage_config.py" \
    "$ROOT_DIR/tests/test_database_readiness.py" \
    "$ROOT_DIR/tests/test_schema_audit.py" \
    "$ROOT_DIR/tests/test_sqlite_export.py" \
    "$ROOT_DIR/tests/test_file_storage_migration.py" \
    "$ROOT_DIR/tests/test_storage_integrity.py" \
    "$ROOT_DIR/tests/test_ai_provider_registry.py" \
    "$ROOT_DIR/tests/test_prompt_registry.py" \
    "$ROOT_DIR/tests/test_ai_call_logging.py" \
    "$ROOT_DIR/tests/test_ai_provider_health.py" \
    "$ROOT_DIR/tests/test_ai_cost_control.py" \
    "$ROOT_DIR/tests/test_ai_alignment_integration.py" \
    "$ROOT_DIR/tests/test_knowledge_versioning.py" \
    "$ROOT_DIR/tests/test_knowledge_indexing.py" \
    "$ROOT_DIR/tests/test_chunk_dedup.py" \
    "$ROOT_DIR/tests/test_retrieval_regression.py" \
    "$ROOT_DIR/tests/test_knowledge_health.py" \
    "$ROOT_DIR/tests/test_source_governance.py" \
    "$ROOT_DIR/tests/test_retrieval_backend_abstraction.py" \
    "$ROOT_DIR/tests/test_embedding_provider.py" \
    "$ROOT_DIR/tests/test_vector_index.py" \
    "$ROOT_DIR/tests/test_hybrid_retrieval.py" \
    "$ROOT_DIR/tests/test_reranker.py" \
    "$ROOT_DIR/tests/test_retrieval_experiments.py" \
    "$ROOT_DIR/tests/test_retrieval_permissions_with_vector.py" \
    "$ROOT_DIR/tests/test_retrieval_score_fusion.py" \
    "$ROOT_DIR/tests/test_pilot_package.py" \
    "$ROOT_DIR/tests/test_project_materials.py" \
    "$ROOT_DIR/tests/test_final_snapshot.py" \
    "$ROOT_DIR/tests/test_final_delivery.py" \
    "$ROOT_DIR/tests/test_final_release_package.py" \
    "$ROOT_DIR/tests/test_final_materials.py"
fi

rm -rf "$STAGE_DIR" "$ZIP_PATH"
mkdir -p "$STAGE_DIR"

copy_path() {
  local src="$1"
  if [ -e "$ROOT_DIR/$src" ]; then
    mkdir -p "$STAGE_DIR/$(dirname "$src")"
    cp -R "$ROOT_DIR/$src" "$STAGE_DIR/$src"
  fi
}

copy_path "backend"
copy_path "frontend"
copy_path "scripts"
copy_path "docs"
copy_path "demo_data"
copy_path "pilot_feedback"
copy_path "pilot_package"
copy_path "final_delivery"
copy_path "README.md"
copy_path ".env.example"
copy_path ".env.development.example"
copy_path ".env.production.example"
copy_path "requirements.txt"
copy_path "LexiBridge_AI_全流程步骤书.docx"

find "$STAGE_DIR" \
  \( -name ".git" \
  -o -name ".env" \
  -o -name "__pycache__" \
  -o -name ".pytest_cache" \
  -o -name ".mypy_cache" \
  -o -name ".DS_Store" \
  -o -name "__MACOSX" \
  -o -name "*.db" \
  -o -name "*.sqlite" \
  -o -name "*.sqlite3" \
  -o -name "*.zip" \
  -o -name ".venv" \
  -o -name ".venv-macos" \
  -o -name ".venv-1" \
  -o -name "venv" \
  -o -name "uploads" \
  -o -name "derived" \
  -o -name "dist" \
  \) -prune -exec rm -rf {} +

find "$STAGE_DIR" -type f -name "*.pyc" -delete
find "$STAGE_DIR" -type f -name ".DS_Store" -delete

"$PYTHON_BIN" "$ROOT_DIR/scripts/check_release_safety.py" "$STAGE_DIR"

(
  cd "$DIST_DIR"
  zip -qr "$ZIP_PATH" "$RELEASE_NAME"
)

"$PYTHON_BIN" "$ROOT_DIR/scripts/check_release_safety.py" "$ZIP_PATH"
"$PYTHON_BIN" "$ROOT_DIR/scripts/check_release_package.py" "$ZIP_PATH"

echo "release_dir=$STAGE_DIR"
echo "release_zip=$ZIP_PATH"
