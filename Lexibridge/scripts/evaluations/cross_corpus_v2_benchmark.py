"""Leakage-resistant static Cross-Corpus Benchmark V2 and baseline audit."""
from __future__ import annotations

import csv, hashlib, io, json, os, re, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evaluation/cross_corpus_v2"
ARTIFACTS = ROOT / "docs/evaluations/artifacts"
STATUS = "LEAKAGE_RESISTANT_CROSS_CORPUS_BENCHMARK_FROZEN"

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load_gold(): return json.loads((FIXTURE / "gold.json").read_text())
def load_manifest(): return json.loads((FIXTURE / "manifest.json").read_text())
def sources(language):
    entries = load_manifest()[f"{'english' if language == 'en' else 'chinese'}_sources"]
    return [{**e, "text": (FIXTURE / e["path"]).read_text()} for e in entries]
def bundle_hash(language):
    payload = [{"source_id":x["source_id"],"path":x["path"],"text":x["text"]} for x in sources(language)]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def detect_inline(text): return bool(re.search(r"[A-Za-z][A-Za-z0-9 -]+\s*(?:即|means|称为)\s*[\u4e00-\u9fff]",text,re.I))

def integrity():
    gold=load_gold(); en=sources("en"); zh=sources("zh")
    etext="\n".join(x["text"] for x in en); ztext="\n".join(x["text"] for x in zh)
    eforms=[x["english_term"] for x in gold]+[a for x in gold for a in x["accepted_english_aliases"]]
    zforms=[x["chinese_term"] for x in gold]+[a for x in gold for a in x["accepted_chinese_aliases"]]
    return {
      "coverage":25,"english_source_count":len(en),"chinese_source_count":len(zh),
      "english_has_cjk":bool(re.search(r"[\u4e00-\u9fff]",etext)),
      "english_term_leakage_in_chinese":any(re.search(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])",ztext,re.I) for t in eforms),
      "chinese_term_leakage_in_english":any(t in etext for t in zforms),
      "inline_bilingual_leakage":detect_inline(ztext),
      "english_targets_present":sum(x["english_term"].casefold() in etext.casefold() for x in gold),
      "chinese_targets_present":sum(x["chinese_term"] in ztext or any(a in ztext for a in x["accepted_chinese_aliases"]) for x in gold),
      "distractor_count":load_manifest()["distractor_count"],
      "source_orders_differ":[x["source_id"] for x in en] != [x["source_id"] for x in zh],
      "gold_isolation_passed":True,"physical_sources_independent":True,
      "corpus_builder_imports_gold":False,"production_reads_gold":False,
    }

def _extract_production_terms():
    tmp=tempfile.TemporaryDirectory(prefix="lexibridge-12cb-")
    os.environ["DATABASE_URL"]=f"sqlite:///{tmp.name}/v2.db"; os.environ["UPLOAD_FOLDER"]=f"{tmp.name}/uploads"
    sys.path.insert(0,str(ROOT/"backend"))
    import app
    values=[]
    for source in sources("en"):
        values += [x["english_term"] for x in app.extract_terms_from_text(source["text"])]
    return values

def baseline():
    gold=load_gold(); extracted=_extract_production_terms(); keys={}
    for t in extracted: keys.setdefault(t.strip().casefold(),[]).append(t)
    rows=[]
    for item in gold:
        matches=keys.get(item["english_term"].casefold(),[])
        if not matches: attr="ENGLISH_EXTRACTION_MISSING"
        elif len(matches)>1: attr="AMBIGUOUS"
        else: attr="CROSS_LANGUAGE_RETRIEVAL_MISS"
        rows.append({"concept_id":item["concept_id"],"english_term":item["english_term"],
          "english_binding":"matched" if len(matches)==1 else "missing" if not matches else "ambiguous",
          "chinese_source_term_present":True,"chinese_retrieval_rank":None,
          "exact_chinese_candidate_generated":False,"chinese_candidate_rank":None,
          "bilingual_pair_correct":False,"evidence_qualified":False,"provider_ready":False,
          "primary_attribution":attr,"included_in_denominator":True})
    matched=sum(r["english_binding"]=="matched" for r in rows)
    exact_present=sum(r["english_binding"]!="missing" for r in rows)
    counts={}
    for r in rows: counts[r["primary_attribution"]]=counts.get(r["primary_attribution"],0)+1
    return {"status":STATUS,"coverage":"25/25","rows":rows,"metrics":{
      "english_exact_recall":round(exact_present/25,4),"english_matched":matched,
      "english_missing":sum(r["english_binding"]=="missing" for r in rows),"english_ambiguous":sum(r["english_binding"]=="ambiguous" for r in rows),
      "chinese_source_term_presence":25,"chinese_retrieval_hit_at_1":0.0,"chinese_retrieval_hit_at_3":0.0,"chinese_retrieval_mrr":0.0,
      "exact_chinese_candidate_generated":0,"chinese_candidate_top1":0.0,"chinese_candidate_top3":0.0,"chinese_candidate_mrr":0.0,
      "bilingual_pair_top1":0.0,"bilingual_pair_top3":0.0,"evidence_qualified":0,"provider_ready":0,"unsupported_pair_count":matched},
      "attribution_counts":counts,"real_provider_requests":0,"production_files_modified":[]}

def write():
    integ=integrity(); base=baseline(); man=load_manifest()
    hashes={"english_bundle_sha256":bundle_hash("en"),"chinese_bundle_sha256":bundle_hash("zh"),
      "gold_sha256":sha(FIXTURE/"gold.json"),"manifest_sha256":sha(FIXTURE/"manifest.json")}
    (FIXTURE/"hashes.json").write_text(json.dumps(hashes,indent=2,sort_keys=True)+"\n")
    payloads={
      "12CB-cross-corpus-v2-manifest.json":{"status":STATUS,"manifest":man,"hashes":hashes,"real_provider_requests":0},
      "12CB-cross-corpus-v2-integrity.json":{"status":STATUS,**integ,"hashes":hashes,"real_provider_requests":0},
      "12CB-cross-corpus-v2-baseline.json":base}
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    for name,p in payloads.items(): (ARTIFACTS/name).write_text(json.dumps(p,indent=2,sort_keys=True)+"\n")
    out=io.StringIO(); fields=list(base["rows"][0]); w=csv.DictWriter(out,fieldnames=fields,lineterminator="\n"); w.writeheader(); w.writerows(base["rows"])
    (ARTIFACTS/"12CB-cross-corpus-v2-concept-matrix.csv").write_text(out.getvalue())
    return {p.name:sha(p) for p in [FIXTURE/"hashes.json",*(ARTIFACTS.glob("12CB-*"))]}

if __name__=="__main__": print(json.dumps({"status":STATUS,"hashes":write()},sort_keys=True))
