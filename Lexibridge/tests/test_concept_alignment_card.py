import sqlite3

import pytest


def evidence_item(language="en", score=0.88):
    return {
        "source": "Signal Processing Notes",
        "page": 12,
        "text": "Fourier Transform converts a signal into frequency-domain representation.",
        "chunk_id": 101 if language == "en" else 202,
        "score": score,
    }


def test_create_valid_concept_alignment_card(app_module):
    with app_module.app.app_context():
        card = app_module.ConceptAlignmentCard(
            english_term="Fourier Transform",
            chinese_term="傅里叶变换",
            course="Signal Processing",
            chapter="Frequency Analysis",
            concept_scope="Signals and systems course context",
            english_explanation="A transform from time domain to frequency domain.",
            chinese_explanation="将信号从时域表示转换为频域表示。",
            alignment_reason="Both sides describe the same signal-processing concept.",
            confidence_score=0.91,
            status="needs_review",
            model_name="",
            prompt_version="alignment_v1",
            retrieval_version="local_lexical_v1",
        )
        card.set_risk_labels(["weak_chinese_evidence"])
        card.set_english_evidence([evidence_item("en")])
        card.set_chinese_evidence([evidence_item("zh", 0.83)])
        app_module.db.session.add(card)
        app_module.db.session.commit()

        saved = app_module.db.session.get(app_module.ConceptAlignmentCard, card.id)
        assert saved.card_uid
        assert saved.version == 1
        assert saved.status == "needs_review"
        assert saved.get_risk_labels() == ["weak_chinese_evidence"]
        assert saved.get_english_evidence()[0]["chunk_id"] == 101
        assert saved.get_chinese_evidence()[0]["chunk_id"] == 202


def test_concept_alignment_card_rejects_missing_required_terms(app_module):
    with app_module.app.app_context():
        with pytest.raises(ValueError, match="english_term is required"):
            app_module.ConceptAlignmentCard(english_term="", course="Signal Processing")

        with pytest.raises(ValueError, match="course is required"):
            app_module.ConceptAlignmentCard(english_term="Fourier Transform", course="")


def test_concept_alignment_card_rejects_invalid_status(app_module):
    with app_module.app.app_context():
        with pytest.raises(ValueError, match="status must be one of"):
            app_module.ConceptAlignmentCard(
                english_term="Fourier Transform",
                course="Signal Processing",
                status="auto_approved",
            )


def test_concept_alignment_card_rejects_confidence_outside_zero_to_one(app_module):
    with app_module.app.app_context():
        with pytest.raises(ValueError, match="confidence_score must be between 0 and 1"):
            app_module.ConceptAlignmentCard(
                english_term="Fourier Transform",
                course="Signal Processing",
                confidence_score=-0.1,
            )

        with pytest.raises(ValueError, match="confidence_score must be between 0 and 1"):
            app_module.ConceptAlignmentCard(
                english_term="Fourier Transform",
                course="Signal Processing",
                confidence_score=1.1,
            )


def test_approved_concept_alignment_card_requires_evidence(app_module):
    with app_module.app.app_context():
        card = app_module.ConceptAlignmentCard(
            english_term="Fourier Transform",
            chinese_term="傅里叶变换",
            course="Signal Processing",
            confidence_score=0.95,
            status="approved",
        )
        app_module.db.session.add(card)

        with pytest.raises(ValueError, match="requires English or Chinese evidence"):
            app_module.db.session.commit()
        app_module.db.session.rollback()


def test_approved_concept_alignment_card_accepts_one_side_evidence(app_module):
    with app_module.app.app_context():
        card = app_module.ConceptAlignmentCard(
            english_term="Convolution",
            chinese_term="卷积",
            course="Signal Processing",
            confidence_score=0.9,
            status="approved",
        )
        card.set_english_evidence([evidence_item("en", 0.9)])
        app_module.db.session.add(card)
        app_module.db.session.commit()

        saved = app_module.db.session.get(app_module.ConceptAlignmentCard, card.id)
        assert saved.status == "approved"
        assert saved.get_english_evidence()[0]["score"] == 0.9


def test_concept_alignment_card_table_exists_after_initialization(app_module):
    db_path = app_module.app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        columns = {row[1] for row in conn.execute("pragma table_info(concept_alignment_card)")}

    assert "concept_alignment_card" in tables
    assert {
        "card_uid",
        "english_term",
        "chinese_term",
        "course",
        "english_evidence",
        "chinese_evidence",
        "confidence_score",
        "risk_labels",
        "status",
        "version",
        "created_at",
        "updated_at",
    } <= columns
