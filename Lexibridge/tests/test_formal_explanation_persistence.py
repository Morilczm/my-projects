import json

from services import alignment_output_parser
from services import alignment_providers
from services import alignment_verification


def _verification_input():
    return {
        "card_uid": "card-explanation-contract",
        "english_term": "electric charge",
        "chinese_term": "电荷",
        "course": "Synthetic Physics",
        "chapter": "Electromagnetism",
        "english_evidence": [{
            "chunk_uid": "chunk-en-charge",
            "source_uid": "source-en",
            "language": "en",
            "snippet": "Bounded synthetic English evidence.",
        }],
        "chinese_evidence": [{
            "chunk_uid": "chunk-zh-charge",
            "source_uid": "source-zh",
            "language": "zh",
            "snippet": "有界合成中文证据。",
        }],
        "candidate_info": {
            "candidate_uid": "candidate-charge",
            "source_uid": "source-zh",
            "chunk_uid": "chunk-zh-charge",
        },
        "retrieval_version": "lexical-v1",
        "risk_labels": ["bilingual_alignment_not_verified"],
    }


def test_formal_explanation_survives_safe_persistence_reload_and_serialization(app_module):
    normalized_input = alignment_verification.validate_alignment_verification_input(
        _verification_input()
    )
    provider_output = alignment_providers.FakeLLMAlignmentProvider().verify_alignment(
        normalized_input
    )
    normalized_output = alignment_output_parser.normalize_alignment_output(provider_output)
    expected = normalized_output["explanation"]

    assert expected
    assert provider_output["explanation"] == expected

    with app_module.app.app_context():
        run = alignment_verification.create_safe_alignment_verification_run(
            app_module.db.session,
            app_module.AlignmentVerificationRun,
            normalized_input,
            provider_output,
            execution_key="formal-explanation-contract",
            card_uid="card-explanation-contract",
            now_fn=app_module.current_time_text,
        )
        run_uid = run.run_uid
        app_module.db.session.commit()
        app_module.db.session.remove()

        reloaded = app_module.AlignmentVerificationRun.query.filter_by(
            run_uid=run_uid
        ).one()
        persisted_output = json.loads(reloaded.output_payload)
        serialized = alignment_verification.serialize_alignment_verification_run(
            reloaded
        )

        assert persisted_output["explanation"] == expected
        assert serialized["explanation"] == expected
        assert serialized["output_payload"]["explanation"] == expected
        assert "raw_response" not in serialized
        assert "raw_response" not in serialized["output_payload"]


def test_empty_explanation_fails_the_persistence_contract(app_module):
    normalized_input = alignment_verification.validate_alignment_verification_input(
        _verification_input()
    )
    provider_output = alignment_providers.FakeLLMAlignmentProvider().verify_alignment(
        normalized_input
    )
    provider_output["explanation"] = ""

    with app_module.app.app_context():
        try:
            alignment_verification.create_safe_alignment_verification_run(
                app_module.db.session,
                app_module.AlignmentVerificationRun,
                normalized_input,
                provider_output,
                execution_key="formal-empty-explanation-contract",
                card_uid="card-explanation-contract",
                now_fn=app_module.current_time_text,
            )
        except alignment_verification.AlignmentVerificationError as exc:
            assert "explanation" in str(exc)
        else:
            raise AssertionError("empty explanation must fail before persistence")
