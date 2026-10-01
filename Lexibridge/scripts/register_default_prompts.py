#!/usr/bin/env python3
"""Register LexiBridge AI default prompt templates."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

spec = importlib.util.spec_from_file_location("lexibridge_app", BACKEND / "app.py")
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)

from services.prompt_registry import DEFAULT_PROMPTS  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Register default AI prompt templates.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing prompt text/schema.")
    args = parser.parse_args(argv)
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        created = 0
        updated = 0
        for item in DEFAULT_PROMPTS:
            prompt = appmod.PromptTemplate.query.filter_by(
                prompt_key=item["prompt_key"],
                prompt_version=item["prompt_version"],
            ).first()
            if prompt is None:
                prompt = appmod.PromptTemplate(
                    prompt_key=item["prompt_key"],
                    prompt_version=item["prompt_version"],
                    created_at=appmod.current_time_text(),
                )
                appmod.db.session.add(prompt)
                created += 1
            elif not args.force:
                continue
            prompt.task_type = item["task_type"]
            prompt.language = item["language"]
            prompt.template_text = item["template_text"]
            prompt.json_schema = json.dumps(item["json_schema"], ensure_ascii=False)
            prompt.is_active = True
            prompt.is_default = True
            prompt.updated_at = appmod.current_time_text()
            prompt.notes = item.get("notes", "")
            if args.force:
                updated += 1
        appmod.db.session.commit()
        prompts = appmod.PromptTemplate.query.order_by(appmod.PromptTemplate.prompt_key.asc()).all()
        print(f"Default prompts registered: created={created}; updated={updated}; total={len(prompts)}")
        for prompt in prompts:
            print(f"- {prompt.prompt_key}:{prompt.prompt_version} active={bool(prompt.is_active)} default={bool(prompt.is_default)}")


if __name__ == "__main__":
    raise SystemExit(main())
