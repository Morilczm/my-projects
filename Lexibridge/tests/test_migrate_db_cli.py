import os
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_import_sentinel(tmp_path: Path) -> tuple[Path, Path]:
    sentinel_dir = tmp_path / "sentinel"
    sentinel_dir.mkdir(exist_ok=True)
    sentinel_file = sentinel_dir / "backend_app_imported"
    (sentinel_dir / "sitecustomize.py").write_text(
        """
import importlib.util
import builtins
from pathlib import Path

_sentinel = Path(__file__).with_name("backend_app_imported")
_original = importlib.util.spec_from_file_location
_original_import = builtins.__import__

def spec_from_file_location(name, location, *args, **kwargs):
    try:
        path = Path(location)
        if path.name == "app.py" and path.parent.name == "backend":
            _sentinel.write_text(f"{name}\\n", encoding="utf-8")
    except Exception:
        pass
    return _original(name, location, *args, **kwargs)

importlib.util.spec_from_file_location = spec_from_file_location

def tracked_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "app":
        _sentinel.write_text(f"{name}\\n", encoding="utf-8")
    return _original_import(name, globals, locals, fromlist, level)

builtins.__import__ = tracked_import
""".strip(),
        encoding="utf-8",
    )
    return sentinel_dir, sentinel_file


def _cli_env(tmp_path: Path, db_path: Path) -> tuple[dict[str, str], Path]:
    sentinel_dir, sentinel_file = _write_import_sentinel(tmp_path)
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env.update({
        "DATABASE_URL": f"sqlite:///{db_path}",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "AUTH_REQUIRED": "True",
        "AI_PROVIDER": "none",
        "ALLOW_MOCK_AI": "True",
        "OCR_PROVIDER": "none",
        "FORMULA_OCR_PROVIDER": "none",
        "PYTHONPATH": str(sentinel_dir) + (os.pathsep + existing_pythonpath if existing_pythonpath else ""),
    })
    for key in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        env.pop(key, None)
    return env, sentinel_file


def _run_cli(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    db_path = tmp_path / "migration-cli.db"
    env, sentinel_file = _cli_env(tmp_path, db_path)
    result = subprocess.run(
        [sys.executable, "scripts/migrate_db.py", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, db_path, sentinel_file


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}


def test_migrate_db_help_has_no_app_import_or_database_side_effect(tmp_path):
    result, db_path, sentinel = _run_cli(tmp_path, "--help")

    assert result.returncode == 0
    assert "usage:" in result.stdout
    assert "--apply" in result.stdout
    assert "Traceback" not in result.stderr
    assert not db_path.exists()
    assert not sentinel.exists()


def test_migrate_db_no_args_refuses_without_side_effects(tmp_path):
    result, db_path, sentinel = _run_cli(tmp_path)

    assert result.returncode == 2
    assert "--apply" in result.stderr
    assert not db_path.exists()
    assert not sentinel.exists()


def test_migrate_db_unknown_args_refuse_without_side_effects(tmp_path):
    result, db_path, sentinel = _run_cli(tmp_path, "--unknown")

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert not db_path.exists()
    assert not sentinel.exists()


def test_migrate_db_apply_with_unknown_arg_refuses_before_app_import(tmp_path):
    result, db_path, sentinel = _run_cli(tmp_path, "--apply", "--unknown")

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert not db_path.exists()
    assert not sentinel.exists()


def test_migrate_db_apply_runs_existing_migration_and_is_repeatable(tmp_path):
    first, db_path, sentinel = _run_cli(tmp_path, "--apply")
    assert first.returncode == 0, first.stderr
    assert "database migrated;" in first.stdout
    assert db_path.exists()
    assert sentinel.exists()
    first_tables = _tables(db_path)
    assert {"user", "course", "knowledge_source", "knowledge_chunk", "ai_provider_config"} <= first_tables

    sentinel.unlink()
    second, _second_db_path, second_sentinel = _run_cli(tmp_path, "--apply")
    assert second.returncode == 0, second.stderr
    assert "database migrated;" in second.stdout
    assert second_sentinel.exists()
    assert _tables(db_path) == first_tables
