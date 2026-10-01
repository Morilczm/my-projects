import uuid


SIGNAL_EN = [
    "Fourier Transform converts a time-domain signal into a frequency-domain representation.",
    "Convolution combines two signals to produce a third signal.",
    "Angular frequency is measured in radians per second.",
    "Wavelength is the spatial period of a wave.",
]

SIGNAL_ZH = [
    "傅里叶变换用于将时域信号表示为频率分量。",
    "卷积描述两个信号经过积分叠加后形成第三个信号。",
    "角频率表示单位时间内相位变化的弧度数。",
    "波长表示波在空间中重复一次的距离。",
]

DATA_EN = [
    "A hash table maps keys to buckets using a hash function.",
    "Collision resolution handles cases where multiple keys map to the same bucket.",
    "A binary search tree stores ordered keys with left and right child nodes.",
    "A stack follows the last-in first-out principle.",
]

DATA_ZH = [
    "哈希表通过哈希函数将关键字映射到桶或存储位置。",
    "冲突解决用于处理多个关键字映射到同一位置的情况。",
    "二叉搜索树按照有序关系组织左右子节点。",
    "栈遵循后进先出的访问原则。",
]


def make_course(app_module, name, teacher_id=1):
    course = app_module.Course(
        name=name,
        course_code=name.upper()[:30],
        teacher_id=teacher_id,
        created_at=app_module.current_time_text()
    )
    app_module.db.session.add(course)
    app_module.db.session.flush()
    return course


def make_source(app_module, name, discipline):
    source = app_module.KnowledgeSource(
        name=name,
        language="bilingual",
        discipline=discipline,
        source_type="authorized_textbook",
        access_method="manual_upload",
        license_status="authorized",
        allow_full_text_indexing=True,
        allow_student_search=True,
        allow_derivative_cards=True,
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text()
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    return source


def add_chunk(app_module, course, source, content, language, kb_type, discipline, index, owner_user_id="", visibility="course"):
    chunk = app_module.KnowledgeChunk(
        document_id=0,
        source_id=source.id if source else None,
        course_id=course.id if course else None,
        course=course.name if course else "",
        title=f"{discipline} KB",
        discipline=discipline,
        chapter="Test",
        chunk_index=index,
        content=content,
        source_page=f"p.{index}",
        page_number=index,
        source_citation=f"{discipline} source p.{index}",
        language=language,
        knowledge_base_type=kb_type,
        owner_user_id=str(owner_user_id or ""),
        visibility=visibility,
        created_at=app_module.current_time_text()
    )
    app_module.db.session.add(chunk)
    return chunk


def seed_retrieval_kb(app_module):
    suffix = uuid.uuid4().hex[:8]
    teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
    signal_course = make_course(app_module, f"Signal Processing {suffix}", teacher_id=teacher.id)
    data_course = make_course(app_module, f"Data Structures {suffix}", teacher_id=teacher.id)
    signal_source = make_source(app_module, f"Signal Source {suffix}", "Signal Processing")
    data_source = make_source(app_module, f"Data Source {suffix}", "Data Structures")
    for index, text in enumerate(SIGNAL_EN, start=1):
        add_chunk(app_module, signal_course, signal_source, text, "en", "en_course_kb", "Signal Processing", index)
    for index, text in enumerate(SIGNAL_ZH, start=1):
        add_chunk(app_module, signal_course, signal_source, text, "zh", "zh_course_kb", "Signal Processing", index)
    for index, text in enumerate(DATA_EN, start=1):
        add_chunk(app_module, data_course, data_source, text, "en", "en_course_kb", "Data Structures", index)
    for index, text in enumerate(DATA_ZH, start=1):
        add_chunk(app_module, data_course, data_source, text, "zh", "zh_course_kb", "Data Structures", index)
    app_module.db.session.commit()
    return signal_course, data_course


def retrieve(app_module, query, course, language, kb_type, owner_user_id=None, scope_type="course"):
    return app_module.retrieve_evidence_results(
        query,
        course_id=course.id if course else None,
        course_name=course.name if course else "",
        language=language,
        scope_type=scope_type,
        owner_user_id=owner_user_id,
        limit=5,
        knowledge_base_type=kb_type
    )


def test_positive_retrieval_returns_matching_evidence(app_module):
    with app_module.app.app_context():
        signal_course, data_course = seed_retrieval_kb(app_module)

        assert "Fourier Transform" in retrieve(app_module, "Fourier Transform", signal_course, "en", "en_course_kb")[0]["content"]
        assert "傅里叶变换" in retrieve(app_module, "Fourier Transform", signal_course, "zh", "zh_course_kb")[0]["content"]
        assert "hash table" in retrieve(app_module, "Hash Table", data_course, "en", "en_course_kb")[0]["content"].lower()
        assert "哈希表" in retrieve(app_module, "Hash Table", data_course, "zh", "zh_course_kb")[0]["content"]
        assert "卷积" in retrieve(app_module, "Convolution", signal_course, "zh", "zh_course_kb")[0]["content"]
        assert "角频率" in retrieve(app_module, "Angular frequency", signal_course, "zh", "zh_course_kb")[0]["content"]


def test_reverse_mismatch_and_no_evidence_return_empty(app_module):
    with app_module.app.app_context():
        signal_course, data_course = seed_retrieval_kb(app_module)

        assert not retrieve(app_module, "Fourier Transform", data_course, "zh", "zh_course_kb")
        assert not retrieve(app_module, "time-domain signal", data_course, "zh", "zh_course_kb")
        assert not retrieve(app_module, "Hash Table", signal_course, "zh", "zh_course_kb")
        assert not retrieve(app_module, "Collision Resolution", signal_course, "zh", "zh_course_kb")
        assert not retrieve(app_module, "Fourier Transform", data_course, "en", "en_course_kb")
        assert not retrieve(app_module, "Nonexistent Term", signal_course, "zh", "zh_course_kb")
        assert not retrieve(app_module, "the and of", signal_course, "en", "en_course_kb")


def test_personal_private_chunks_are_owner_filtered(app_module):
    with app_module.app.app_context():
        source = make_source(app_module, f"Personal Source {uuid.uuid4().hex[:8]}", "Signal Processing")
        personal_course = make_course(app_module, f"Personal Course {uuid.uuid4().hex[:8]}")
        add_chunk(
            app_module,
            personal_course,
            source,
            "Fourier Transform personal note.",
            "en",
            "student_personal_kb",
            "Signal Processing",
            1,
            owner_user_id=101,
            visibility="private"
        )
        add_chunk(
            app_module,
            personal_course,
            source,
            "Hash Table private note.",
            "en",
            "student_personal_kb",
            "Data Structures",
            2,
            owner_user_id=202,
            visibility="private"
        )
        app_module.db.session.commit()

        own_results = retrieve(app_module, "Fourier Transform", personal_course, "en", "student_personal_kb", owner_user_id=101, scope_type="personal")
        other_results = retrieve(app_module, "Hash Table", personal_course, "en", "student_personal_kb", owner_user_id=101, scope_type="personal")

        assert len(own_results) == 1
        assert own_results[0]["owner_user_id"] == "101"
        assert other_results == []


def test_knowledge_search_api_returns_empty_instead_of_fallback(app_module, client, teacher_token):
    with app_module.app.app_context():
        signal_course, data_course = seed_retrieval_kb(app_module)
        signal_course_id = signal_course.id
        data_course_id = data_course.id

    ok_response = client.get(
        f"/api/knowledge/search?q=Fourier%20Transform&course_id={signal_course_id}&language=zh&knowledge_base_type=zh_course_kb&scope_type=course",
        headers={"Authorization": f"Bearer {teacher_token}"}
    )
    assert ok_response.status_code == 200
    ok_payload = ok_response.get_json()
    assert ok_payload["data"]["items"]
    assert "傅里叶变换" in ok_payload["data"]["items"][0]["content"]
    assert ok_payload["data"]["items"][0]["score_breakdown"]["semantic_similarity_score"] == 0.0

    empty_response = client.get(
        f"/api/knowledge/search?q=Fourier%20Transform&course_id={data_course_id}&language=zh&knowledge_base_type=zh_course_kb&scope_type=course",
        headers={"Authorization": f"Bearer {teacher_token}"}
    )
    assert empty_response.status_code == 200
    empty_payload = empty_response.get_json()
    assert empty_payload["data"]["items"] == []
    assert empty_payload["data"]["message"] == "No evidence passed the relevance threshold."


def test_card_generation_status_rules(app_module):
    strong_item = {
        "content": "Fourier Transform converts a time-domain signal.",
        "evidence_score": 0.80,
        "evidence_strength": "strong",
        "risk_flags": []
    }
    weak_item = {
        "content": "Fourier related weak note.",
        "evidence_score": 0.66,
        "evidence_strength": "weak",
        "risk_flags": []
    }

    missing_english = app_module.finalize_alignment_result({
        "english_term": "Fourier Transform",
        "course": "Signal Processing",
        "english_kb_evidence": "",
        "chinese_kb_evidence": "傅里叶变换用于将时域信号表示为频率分量。",
        "english_evidence_items": [],
        "chinese_evidence_items": [strong_item],
        "confidence_score": 95,
        "ai_model": "deepseek",
        "provider_status": "real_provider",
        "term_quality_score": 1.0,
    })
    assert missing_english["alignment_status"] == "no_en_evidence"
    assert missing_english["review_status"] == "needs_more_evidence"
    assert missing_english["confidence_score"] <= 45

    weak = app_module.finalize_alignment_result({
        "english_term": "Fourier Transform",
        "course": "Signal Processing",
        "english_kb_evidence": "Fourier Transform converts a time-domain signal.",
        "chinese_kb_evidence": "傅里叶变换用于将时域信号表示为频率分量。",
        "english_evidence_items": [weak_item],
        "chinese_evidence_items": [strong_item],
        "confidence_score": 95,
        "ai_model": "deepseek",
        "provider_status": "real_provider",
        "term_quality_score": 1.0,
    })
    assert "weak_evidence" in weak["quality_flags"]
    assert weak["review_status"] == "pending_quality_control"

    strong_live = app_module.finalize_alignment_result({
        "english_term": "Fourier Transform",
        "course": "Signal Processing",
        "english_kb_evidence": "Fourier Transform converts a time-domain signal.",
        "chinese_kb_evidence": "傅里叶变换用于将时域信号表示为频率分量。",
        "english_evidence_items": [strong_item],
        "chinese_evidence_items": [strong_item],
        "confidence_score": 100,
        "ai_model": "deepseek",
        "provider_status": "real_provider",
        "term_quality_score": 1.0,
    })
    assert strong_live["review_status"] == "auto_approved"

    strong_mock = app_module.finalize_alignment_result({
        "english_term": "Fourier Transform",
        "course": "Signal Processing",
        "english_kb_evidence": "Fourier Transform converts a time-domain signal.",
        "chinese_kb_evidence": "傅里叶变换用于将时域信号表示为频率分量。",
        "english_evidence_items": [strong_item],
        "chinese_evidence_items": [strong_item],
        "confidence_score": 100,
        "ai_model": "local_heuristic",
        "provider_status": "local_heuristic",
        "term_quality_score": 1.0,
    })
    assert strong_mock["review_status"] == "pending_quality_control"
