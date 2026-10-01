import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def load_app_module():
    spec = importlib.util.spec_from_file_location("lexibridge_app", BACKEND / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description="Run LexiBridge AI local evaluation harness.")
    parser.add_argument("--set", dest="set_path", default="docs/evaluation_sample.jsonl")
    parser.add_argument("--split", default="test")
    parser.add_argument("--name", default="lexibridge_smoke_v1")
    parser.add_argument("--discipline", default="mixed")
    args = parser.parse_args()

    app_module = load_app_module()
    with app_module.app.app_context():
        app_module.db.create_all()
        app_module.ensure_schema_columns()
        user = app_module.User.query.filter_by(email="admin@lexibridge.local").first()
        if user is None:
            user = app_module.User(
                username="admin",
                email="admin@lexibridge.local",
                password_hash=app_module.generate_password_hash("Admin1234", method="pbkdf2:sha256"),
                role="admin",
                is_verified=True,
                created_at=app_module.current_time_text(),
            )
            app_module.db.session.add(user)
            app_module.db.session.commit()

        evaluation_set = app_module.EvaluationSet(
            name=args.name,
            discipline=args.discipline,
            description="CLI imported smoke evaluation set.",
            split=args.split,
            created_by=user.id,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        app_module.db.session.add(evaluation_set)
        app_module.db.session.flush()
        import_result = app_module.import_evaluation_items(args.set_path, evaluation_set.id, user)
        run = app_module.run_evaluation_set(evaluation_set, user, split=args.split)
        app_module.db.session.commit()

        metrics = app_module.safe_json_loads(run.metrics_json, {})
        report = app_module.safe_json_loads(run.report_json, {})
        gate = (report.get("release_gate") or {})
        print(f"Imported: {import_result['imported_count']} skipped: {import_result['skipped_count']}")
        print(f"EvaluationRun ID: {run.id}")
        for key in [
            "extraction_precision",
            "extraction_recall",
            "evidence_accuracy",
            "alignment_accuracy",
            "false_positive_rate",
            "auto_approval_error_rate",
            "no_evidence_forced_alignment_rate",
        ]:
            print(f"{key}: {metrics.get(key)}")
        print(f"release_gate: {'PASS' if gate.get('passed') else 'FAIL'}")


if __name__ == "__main__":
    main()
