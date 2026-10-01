import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def isolated_env(tmp_path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'demo.db'}"
    env["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    env["AI_PROVIDER"] = "none"
    env["ALLOW_MOCK_AI"] = "True"
    env["OCR_PROVIDER"] = "none"
    env["FORMULA_OCR_PROVIDER"] = "none"
    return env


def parse_summary(output, prefix):
    for line in output.splitlines():
        if line.startswith(prefix):
            return json.loads(line.split("=", 1)[1])
    raise AssertionError(f"{prefix} missing from output:\n{output}")


def run_script(script, tmp_path, *args):
    result = subprocess.run(
        [sys.executable, str(ROOT / script), *args],
        cwd=ROOT,
        env=isolated_env(tmp_path),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def test_demo_data_directory_and_gold_terms():
    demo_dir = ROOT / "demo_data"
    assert demo_dir.exists()
    courses = json.loads((demo_dir / "courses.json").read_text(encoding="utf-8"))
    assert {course["course_code"] for course in courses} == {"DS101", "SP101", "MATH101"}

    total = 0
    statuses = set()
    formula_count = 0
    ocr_count = 0
    for path in demo_dir.glob("*/gold_terms.jsonl"):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(rows) >= 20
        total += len(rows)
        for row in rows:
            statuses.add(row["expected_alignment_status"])
            tags = row.get("tags", [])
            formula_count += int("formula_related" in tags)
            ocr_count += int("ocr_sensitive" in tags)
    assert total >= 60
    assert {"exact_match", "no_zh_evidence", "domain_mismatch", "formula_evidence_missing", "unverified_translation"} <= statuses
    assert formula_count >= 6
    assert ocr_count >= 6


def test_seed_demo_data_is_idempotent(tmp_path):
    run_script("scripts/migrate_db.py", tmp_path, "--apply")
    first = run_script("scripts/seed_demo_data.py", tmp_path, "--summary-json")
    second = run_script("scripts/seed_demo_data.py", tmp_path, "--summary-json")
    first_summary = parse_summary(first, "DEMO_SEED_JSON=")
    second_summary = parse_summary(second, "DEMO_SEED_JSON=")

    assert first_summary["courses_total"] == 3
    assert first_summary["evaluation_items_imported"] >= 60
    assert second_summary["users_created"] == 0
    assert second_summary["courses_created"] == 0
    assert second_summary["evaluation_items_imported"] == first_summary["evaluation_items_imported"]

    check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib.util, pathlib; "
                f"root=pathlib.Path({str(ROOT)!r}); "
                "import sys; sys.path.insert(0, str(root/'backend')); "
                "spec=importlib.util.spec_from_file_location('app', root/'backend/app.py'); "
                "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                "ctx=m.app.app_context(); ctx.push(); "
                "print(m.Course.query.filter(m.Course.course_code.in_(['DS101','SP101','MATH101'])).count(), "
                "m.EvaluationSet.query.filter_by(name='lexibridge_demo_gold_v1').count(), "
                "m.EvaluationItem.query.count()); ctx.pop()"
            ),
        ],
        cwd=ROOT,
        env=isolated_env(tmp_path),
        text=True,
        capture_output=True,
        check=True,
    )
    course_count, set_count, item_count = [int(value) for value in check.stdout.strip().split()]
    assert course_count == 3
    assert set_count == 1
    assert item_count >= 60
