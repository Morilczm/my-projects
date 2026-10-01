import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_dev_check():
    spec = importlib.util.spec_from_file_location("dev_check", ROOT / "scripts" / "dev_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dev_check_steps_cover_required_gate_commands():
    dev_check = load_dev_check()
    steps = dev_check.build_steps("python")

    assert [step.name for step in steps] == [
        "release safety check",
        "pytest",
        "database initialization",
        "backend import/API smoke",
    ]
    assert steps[0].command == ["python", "scripts/check_release_safety.py"]
    assert steps[1].command == ["python", "-m", "pytest"]
    assert steps[2].command == ["python", "scripts/migrate_db.py", "--apply"]
    assert steps[3].command == ["python", "scripts/dev_check.py", "--backend-smoke-child"]


def test_dev_check_env_uses_temporary_runtime_paths(tmp_path):
    dev_check = load_dev_check()
    env = dev_check.build_check_env(tmp_path)

    assert env["DATABASE_URL"].startswith("sqlite:///")
    assert str(tmp_path) in env["DATABASE_URL"]
    assert env["UPLOAD_FOLDER"] == str(tmp_path / "uploads")
    assert env["LOCAL_STORAGE_ROOT"] == str(tmp_path / "uploads")
    assert env["PYTHONPYCACHEPREFIX"] == str(tmp_path / "pycache")
    assert env["AI_PROVIDER"] == "none"
    assert env["AI_PROVIDER_MODE"] == "none"
    assert env["DEEPSEEK_API_KEY"] == ""
    assert env["OPENAI_API_KEY"] == ""
    assert env["OCR_PROVIDER"] == "none"
    assert env["FORMULA_OCR_PROVIDER"] == "none"
