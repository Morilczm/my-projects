from scripts.evaluations import cross_corpus_v2_benchmark as v2
def test_integrity_contract():
    x=v2.integrity()
    assert x["coverage"]==25 and x["english_source_count"]>=4 and x["chinese_source_count"]>=4
    assert not x["english_has_cjk"] and not x["english_term_leakage_in_chinese"]
    assert not x["chinese_term_leakage_in_english"] and not x["inline_bilingual_leakage"]
    assert x["english_targets_present"]==x["chinese_targets_present"]==25
    assert x["distractor_count"]>=10
def test_runner_denominator_and_provider_isolation():
    b=v2.baseline(); assert len(b["rows"])==25
    assert all(r["included_in_denominator"] for r in b["rows"])
    assert b["real_provider_requests"]==0 and b["production_files_modified"]==[]
