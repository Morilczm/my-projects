from pathlib import Path
from scripts.evaluations import cross_corpus_v2_benchmark as v2
def test_gold_is_scorer_only():
    x=v2.integrity(); assert x["gold_isolation_passed"]
    assert not x["corpus_builder_imports_gold"] and not x["production_reads_gold"]
    text=Path(v2.__file__).read_text()
    assert "required_semantic_propositions" not in text
def test_opaque_ids_absent_from_sources():
    corpus="\n".join(x["text"] for lang in ("en","zh") for x in v2.sources(lang))
    assert all(x["concept_id"] not in corpus for x in v2.load_gold())
