from types import SimpleNamespace

import pytest

from services import concept_alignment_cards as concept_cards


def evidence(score=0.86):
    return [{
        "source": "Signal Processing Notes",
        "page": 7,
        "text": "Convolution combines two signals to produce a third signal.",
        "chunk_id": 17,
        "score": score,
    }]


def create_service_card(app_module, **overrides):
    data = {
        "english_term": "Convolution",
        "chinese_term": "卷积",
        "course": "Service Signal Processing",
        "chapter": "Linear Systems",
        "status": "needs_review",
        "confidence_score": 0.74,
        "risk_labels": ["weak_evidence"],
        "english_evidence": evidence(),
    }
    data.update(overrides)
    return concept_cards.create_concept_card(
        app_module.db.session,
        app_module.ConceptAlignmentCard,
        data,
        now_fn=app_module.current_time_text,
    )


def test_service_create_and_get_concept_card_by_uid(app_module):
    with app_module.app.app_context():
        card = create_service_card(app_module, english_term="Service Create Term")
        found = concept_cards.get_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            card.card_uid,
        )

        assert found.id == card.id
        assert concept_cards.serialize_concept_card(found)["risk_labels"] == ["weak_evidence"]


def test_service_create_with_partial_text_risk_forces_review_and_preserves_labels(app_module):
    with app_module.app.app_context():
        card = create_service_card(
            app_module,
            english_term="Partial Quality Service Term",
            status="draft",
            confidence_score=0.95,
            risk_labels=["weak_evidence"],
            parse_uid="parse-service-partial",
            parse_quality_status="partial_text",
            parse_quality_flags=["partial_text"],
        )
        serialized = concept_cards.serialize_concept_card(card)

        assert serialized["status"] == "draft"
        assert serialized["confidence_score"] == 0.79
        assert serialized["parse_uid"] == "parse-service-partial"
        assert serialized["parse_quality_status"] == "partial_text"
        assert serialized["risk_labels"] == ["weak_evidence", "input_partial_text"]
        assert serialized["input_risk_labels"] == ["input_partial_text"]


def test_service_rejects_approved_with_parse_quality_risk(app_module):
    with app_module.app.app_context():
        with pytest.raises(concept_cards.ConceptCardQualityGateError):
            create_service_card(
                app_module,
                english_term="Risky Approved Service Term",
                status="approved",
                parse_quality_status="mixed_quality",
                parse_quality_flags=["mixed_quality"],
            )


def test_service_list_concept_cards_filters_course_status_and_query(app_module):
    with app_module.app.app_context():
        create_service_card(app_module, english_term="Laplace Transform", course="Service Course A", status="draft")
        create_service_card(app_module, english_term="Z Transform", course="Service Course A", status="approved")
        create_service_card(app_module, english_term="Hash Table", course="Service Course B", status="draft")

        by_course = concept_cards.list_concept_cards(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            {"course": "Service Course A", "per_page": 20},
        )
        by_status = concept_cards.list_concept_cards(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            {"status": "draft", "per_page": 20},
        )
        by_query = concept_cards.list_concept_cards(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            {"q": "Laplace", "per_page": 20},
        )

        assert {card.course for card in by_course.items} == {"Service Course A"}
        assert all(card.status == "draft" for card in by_status.items)
        assert [card.english_term for card in by_query.items] == ["Laplace Transform"]


def test_service_update_allowed_fields_ignores_illegal_fields_and_increments_version(app_module):
    with app_module.app.app_context():
        card = create_service_card(app_module, english_term="Original Service Term")
        original_id = card.id
        original_uid = card.card_uid
        original_version = card.version

        updated = concept_cards.update_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            original_uid,
            {
                "id": 999999,
                "card_uid": "malicious-overwrite",
                "created_at": "not-allowed",
                "english_term": "Updated Service Term",
                "risk_labels": ["teacher_reviewed"],
            },
            now_fn=app_module.current_time_text,
        )

        assert updated.id == original_id
        assert updated.card_uid == original_uid
        assert updated.english_term == "Updated Service Term"
        assert updated.version == original_version + 1
        assert concept_cards.serialize_concept_card(updated)["risk_labels"] == ["teacher_reviewed"]


def test_service_patch_risky_card_to_approved_is_blocked(app_module):
    with app_module.app.app_context():
        card = create_service_card(
            app_module,
            english_term="Risky Patch Service Term",
            status="needs_review",
            parse_quality_status="partial_text",
            parse_quality_flags=["partial_text"],
        )

        with pytest.raises(concept_cards.ConceptCardQualityGateError):
            concept_cards.update_concept_card(
                app_module.db.session,
                app_module.ConceptAlignmentCard,
                card.card_uid,
                {"status": "approved"},
                now_fn=app_module.current_time_text,
            )


def test_service_change_status_and_reject_approved_without_evidence(app_module):
    with app_module.app.app_context():
        ready = create_service_card(app_module, english_term="Ready Service Term", status="needs_review")
        approved = concept_cards.change_concept_card_status(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            ready.card_uid,
            "approved",
            reviewer=123,
            now_fn=app_module.current_time_text,
        )
        assert approved.status == "approved"
        assert approved.reviewed_by == 123
        assert approved.reviewed_at

        no_evidence = concept_cards.create_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            {
                "english_term": "No Evidence Service Term",
                "course": "Service Signal Processing",
                "status": "draft",
            },
            now_fn=app_module.current_time_text,
        )
        with pytest.raises(concept_cards.ConceptCardError, match="requires English or Chinese evidence"):
            concept_cards.change_concept_card_status(
                app_module.db.session,
                app_module.ConceptAlignmentCard,
                no_evidence.card_uid,
                "approved",
                now_fn=app_module.current_time_text,
            )


def test_service_build_concept_card_draft_from_legacy_term_like():
    legacy = SimpleNamespace(
        english_term="Binary Search Tree",
        final_chinese_term="二叉搜索树",
        course="Data Structures",
        chapter="Trees",
        explanation="一种有序二叉树。",
        english_kb_evidence="BST evidence",
        chinese_kb_evidence="二叉搜索树证据",
        confidence=72,
        ai_model="legacy-local",
    )

    draft = concept_cards.build_concept_card_draft_from_term(legacy)

    assert draft["english_term"] == "Binary Search Tree"
    assert draft["chinese_term"] == "二叉搜索树"
    assert draft["course"] == "Data Structures"
    assert draft["chapter"] == "Trees"
    assert draft["status"] == "draft"
    assert draft["confidence_score"] == 0.72
    assert draft["english_evidence"] == "BST evidence"
    assert draft["model_name"] == "legacy-local"
