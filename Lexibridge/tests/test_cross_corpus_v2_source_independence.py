from scripts.evaluations import cross_corpus_v2_benchmark as v2
def test_sources_are_independent_and_opaque():
    x=v2.integrity(); assert x["physical_sources_independent"] and x["source_orders_differ"]
    for s in v2.sources("en")+v2.sources("zh"):
        assert s["source_id"].startswith(("en-s","zh-s"))
        assert "cx-" not in s["source_id"]
def test_confusion_groups_and_static_files():
    en="\n".join(x["text"].lower() for x in v2.sources("en"))
    assert all(t in en for t in ("electric field strength","electric potential energy","angular acceleration","weight"))
