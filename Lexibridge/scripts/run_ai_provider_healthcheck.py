#!/usr/bin/env python3
"""Run AI provider registry health checks without exposing secrets."""

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

from services.ai_health import healthcheck_provider  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run AI provider health checks.")
    parser.add_argument("--live-probe", action="store_true", help="Send a minimal live request for live providers.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        appmod.ensure_ai_registry_seed()
        results = []
        for config in appmod.AIProviderConfig.query.filter_by(is_enabled=True).all():
            selection = appmod.ai_selection_from_config(config=config)
            result = healthcheck_provider(selection, live_probe=args.live_probe and selection.provider_mode == "live")
            config.health_status = result.get("health_status", "unknown")
            config.last_healthcheck_at = appmod.current_time_text()
            config.updated_at = appmod.current_time_text()
            results.append(result)
        appmod.db.session.commit()
        if args.json:
            print(json.dumps({"status": "success", "items": results}, ensure_ascii=False, indent=2))
        else:
            print("AI Provider Healthcheck:")
            for item in results:
                print(f"- {item['provider_name']} ({item['provider_mode']}): {item['health_status']} - {item['message']}")


if __name__ == "__main__":
    raise SystemExit(main())
