from services.chinese_term_candidates import (
    MAX_CANDIDATE_LIMIT,
    extract_monolingual_chinese_term_spans,
    identify_standard_chinese_terms,
)


def _evidence(text, **changes):
    item = {
        "source_uid": "zh-source-a",
        "chunk_uid": "zh-chunk-a",
        "language": "zh",
        "snippet": text,
        "rank": 1,
        "score": 0.81,
        "status": "active",
        "quality_status": "ready",
        "source_role": "chinese_reference_material",
        "block_type": "text",
        "provenance": {
            "source_uid": "zh-source-a",
            "chunk_uid": "zh-chunk-a",
            "content_hash": "content-a",
        },
    }
    item.update(changes)
    return item


def _terms(text, **changes):
    result = identify_standard_chinese_terms(
        "opaque English context",
        [_evidence(text, **changes)],
        discipline="physics",
        limit=20,
    )
    return result.candidates


def test_definition_subject_boundaries_and_scope_terms():
    candidates = _terms(
        "电场是电荷周围的一种物理场。"
        "电场强度表示单位正电荷受到的力。"
        "电势描述单位电荷的势能水平，电势能则属于特定带电体。"
        "角速度表示角位置的变化率，角加速度反映角速度变化快慢。"
        "动量等于质量与速度的乘积，角动量用于描述转动状态。"
    )
    candidates += _terms("质量是衡量惯性大小的物理量，重量是重力对物体的作用。")
    terms = {item["chinese_term"] for item in candidates}
    assert {
        "电场", "电场强度", "电势", "电势能", "角速度", "角加速度",
        "动量", "角动量", "质量", "重量",
    } <= terms
    assert not any("是电荷周围" in term or "表示单位" in term for term in terms)


def test_so_called_called_heading_and_list_patterns():
    assert extract_monolingual_chinese_term_spans("所谓惯性，是物体保持运动状态的性质。")[0]["text"] == "惯性"
    assert extract_monolingual_chinese_term_spans("将力对转动的作用称为力矩。")[0]["text"] == "力矩"
    heading = extract_monolingual_chinese_term_spans(
        "磁矩", block_type="heading", heading="磁矩"
    )
    listed = extract_monolingual_chinese_term_spans("• 比热容：单位质量升高温度所需热量。")
    assert heading[0]["text"] == "磁矩"
    assert listed[0]["text"] == "比热容"


def test_generic_units_numbers_formulas_and_definition_fragments_are_rejected():
    candidates = _terms(
        "物体是研究对象。作用表示影响。过程描述变化。"
        "kg：质量单位。42：编号。F=ma：公式。"
        "表示物体转动状态的物理量。"
    )
    assert candidates == []


def test_normalization_provenance_bounds_and_determinism():
    evidence = [
        _evidence("　角速度（ω）表示角位置变化率。", chunk_uid="b", rank=2),
        _evidence("角速度（ω）是描述转动快慢的物理量。", chunk_uid="a", rank=1),
    ]
    first = identify_standard_chinese_terms("rotation", evidence, limit=999)
    second = identify_standard_chinese_terms("rotation", list(reversed(evidence)), limit=999)
    assert len(first.candidates) <= MAX_CANDIDATE_LIMIT
    assert [x["candidate_uid"] for x in first.candidates] == [
        x["candidate_uid"] for x in second.candidates
    ]
    candidate = first.candidates[0]
    assert candidate["chinese_term"] == "角速度（ω）"
    assert candidate["normalized_text"] == "角速度(ω)"
    assert candidate["source_uid"] == "zh-source-a"
    assert candidate["chunk_uid"] == "a"
    assert candidate["original_span"]
    assert candidate["span_start"] >= 0
    assert candidate["span_end"] > candidate["span_start"]
    assert candidate["retrieval_rank"] == 1
    assert candidate["provenance"]["content_hash"] == "content-a"


def test_tie_break_is_stable_and_per_chunk_candidates_are_bounded():
    text = "；".join(f"术语甲{i}表示某种受控性质" for i in range(20))
    evidence = [
        _evidence(text, source_uid="z-source", chunk_uid="z-chunk"),
        _evidence("惯性是保持运动状态的性质", source_uid="a-source", chunk_uid="a-chunk"),
    ]
    result = identify_standard_chinese_terms("context", evidence, limit=999)
    assert len([x for x in result.candidates if x["chunk_uid"] == "z-chunk"]) <= 8
    assert len(result.candidates) <= MAX_CANDIDATE_LIMIT
    assert all(item["rank"] >= 1 for item in result.candidates)
