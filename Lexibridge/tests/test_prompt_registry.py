import json
import os
import subprocess
import sys
from pathlib import Path

from services.prompt_registry import ALIGNMENT_STATUS_ENUM, validate_ai_json, validate_prompt_schema


ROOT = Path(__file__).resolve().parents[1]


def test_register_default_prompts_script_and_no_duplicates(app_module):
    env = dict(os.environ)
    env["DATABASE_URL"] = app_module.app.config["SQLALCHEMY_DATABASE_URI"]
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/register_default_prompts.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with app_module.app.app_context():
        prompts = app_module.PromptTemplate.query.filter_by(prompt_key="term_alignment", prompt_version="v1").all()
        assert len(prompts) == 1
        prompt = prompts[0]
        assert prompt.is_active
        assert validate_prompt_schema(prompt.json_schema)
        assert "alignment_status" in json.loads(prompt.json_schema)["properties"]


def test_inactive_prompt_not_default_and_status_enum_validated(app_module):
    with app_module.app.app_context():
        prompt = app_module.PromptTemplate(
            prompt_key="term_alignment",
            prompt_version="inactive",
            task_type="term_alignment",
            is_active=False,
            is_default=True,
            json_schema="{}",
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(prompt)
        app_module.db.session.commit()
        selected = app_module.get_prompt_template("term_alignment", task_type="term_alignment")
        assert selected.prompt_version != "inactive"

    ok, reason = validate_ai_json("term_alignment", {
        "alignment_status": "made_up_status",
        "candidate_chinese_term": "x",
        "concept_explanation": "",
        "alignment_reason": "",
        "risk_flags": [],
        "requires_human_review": True,
    })
    assert ok is False
    assert "Unsupported" in reason
    assert "exact_match" in ALIGNMENT_STATUS_ENUM
