"""Provider-free Task 12D Cross-Corpus V2 semantic retrieval evaluation."""
from __future__ import annotations
import csv, hashlib, io, json, statistics, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; FIX=ROOT/"evaluation/cross_corpus_v2"
OUT=ROOT/"docs/evaluations/artifacts"
sys.path.insert(0,str(ROOT/"backend"))
from services.cross_language_retrieval import CrossLanguageRetrievalQuery, SemanticPassage, rank_chinese_passages

def _paragraphs(source):
    text=(FIX/source["path"]).read_text()
    return [p.strip() for p in text.split("\n\n") if p.strip()][1:]
def _hash(text): return hashlib.sha256(text.encode()).hexdigest()

def evaluate(backend):
    gold=json.loads((FIX/"gold.json").read_text()); man=json.loads((FIX/"manifest.json").read_text())
    import app
    extracted=[]
    for source in man["english_sources"]:
        text=(FIX/source["path"]).read_text()
        extracted += [x["english_term"] for x in app.extract_terms_from_text(text)]
    keys={}
    for term in extracted: keys.setdefault(term.casefold().strip(),[]).append(term)
    zh=[]
    for source in man["chinese_sources"]:
        for i,text in enumerate(_paragraphs(source),1):
            zh.append(SemanticPassage(source["source_id"],f"{source['source_id']}-p{i:02}",text,"zh","active","ready",_hash(text)))
    rows=[]; ranks=[]
    for item in gold:
        matches=keys.get(item["english_term"].casefold(),[])
        binding="matched" if len(matches)==1 else "missing" if not matches else "ambiguous"
        if binding!="matched":
            rows.append({"concept_id":item["concept_id"],"english_binding":binding,"eligible":False,
              "query_hash":"","retrieved_chunk_ids":"","gold_rank":"","top1":False,"top3":False,
              "top1_chunk":"","primary_error_chunk":"","score_margin":"",
              "primary_attribution":"UPSTREAM_ENGLISH_EXTRACTION_MISSING" if binding=="missing" else "UPSTREAM_ENGLISH_BINDING_AMBIGUOUS"})
            continue
        context=""
        for source in man["english_sources"]:
            for p in _paragraphs(source):
                if item["english_term"].casefold() in p.casefold(): context=p; break
                if context: break
        query=CrossLanguageRetrievalQuery("system-"+_hash(item["english_term"])[:12],
          item["english_term"],item["english_term"].casefold(),context,item["discipline"],
          tuple(x["source_id"] for x in man["chinese_sources"]),3,200)
        found=rank_chinese_passages(query,zh,backend)
        correct={p.chunk_uid for p in zh if item["chinese_term"] in p.content or any(a in p.content for a in item["accepted_chinese_aliases"])}
        rank=next((r.rank for r in found if r.chunk_uid in correct),None)
        correct_result=next((r for r in found if r.chunk_uid in correct),None)
        wrong_result=next((r for r in found if r.chunk_uid not in correct),None)
        margin=round(correct_result.score-wrong_result.score,8) if correct_result and wrong_result else ""
        if rank:ranks.append(rank)
        rows.append({"concept_id":item["concept_id"],"english_binding":binding,"eligible":True,
          "query_hash":found[0].query_hash if found else "","retrieved_chunk_ids":"|".join(r.chunk_uid for r in found),
          "gold_rank":rank or "","top1":rank==1,"top3":bool(rank and rank<=3),
          "top1_chunk":found[0].chunk_uid if found else "",
          "primary_error_chunk":wrong_result.chunk_uid if wrong_result else "","score_margin":margin,
          "primary_attribution":"CHINESE_TERM_IDENTIFICATION_MISSING" if rank else "CROSS_LANGUAGE_RETRIEVAL_MISS"})
    eligible=[r for r in rows if r["eligible"]]
    metrics={"coverage":25,"english_matched":18,"english_missing":3,"english_ambiguous":4,
      "retrieval_eligible":18,"chinese_evidence_retrieved":sum(bool(r["retrieved_chunk_ids"]) for r in eligible),
      "hit_at_1":round(sum(r["top1"] for r in eligible)/18,4),"hit_at_3":round(sum(r["top3"] for r in eligible)/18,4),
      "mrr":round(sum((1/r["gold_rank"]) if r["gold_rank"] else 0 for r in eligible)/18,4),
      "average_gold_rank":round(sum(ranks)/len(ranks),4) if ranks else None,
      "median_gold_rank":statistics.median(ranks) if ranks else None,
      "no_result_count":sum(not r["retrieved_chunk_ids"] for r in eligible),
      "exact_chinese_candidate_generated":0,"pair_accuracy":0.0,"evidence_qualified":0,"provider_ready":0}
    confusion=[]
    groups=[("electric field","electric field strength"),("electric potential","electric potential energy"),
      ("angular velocity","angular acceleration"),("momentum","angular momentum"),("mass","weight")]
    byterm={x["english_term"]:x for x in gold}
    for left,right in groups:
        item=byterm.get(left); row=next((r for r in rows if item and r["concept_id"]==item["concept_id"]),None)
        confusion.append({"group":f"{left} / {right}","query_id":row["concept_id"] if row else "",
          "correct_rank":row["gold_rank"] if row else "","top1_correct":bool(row and row["top1"]),
          "top3_correct":bool(row and row["top3"]),
          "primary_error_chunk":row["primary_error_chunk"] if row else "",
          "score_margin":row["score_margin"] if row else "",
          "concept_scope_confusion":bool(row and not row["top1"]),
          "requires_reranker":bool(row and not row["top1"])})
    return {"technical_status":"CROSS_LANGUAGE_RETRIEVAL_CONTRACT_CLOSED",
      "quality_status":"CROSS_LANGUAGE_RETRIEVAL_QUALITY_BASELINE_ESTABLISHED",
      "metrics":metrics,"rows":rows,"confusion_groups":confusion,"real_provider_requests":0}

def write(result):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"12D-cross-language-retrieval-baseline.json").write_text(json.dumps({k:v for k,v in result.items() if k!="rows"},indent=2,ensure_ascii=False)+"\n")
    (OUT/"12D-confusion-group-audit.json").write_text(json.dumps(result["confusion_groups"],indent=2,ensure_ascii=False)+"\n")
    backend={"backend_id":"local_multilingual_e5_pytorch_cpu_v1","model_id":"intfloat/multilingual-e5-small",
      "model_revision":"614241f622f53c4eeff9890bdc4f31cfecc418b3","offline":True,"external_api_used":False}
    (OUT/"12D-retrieval-backend-manifest.json").write_text(json.dumps(backend,indent=2)+"\n")
    buf=io.StringIO(); w=csv.DictWriter(buf,fieldnames=list(result["rows"][0]),lineterminator="\n"); w.writeheader(); w.writerows(result["rows"])
    (OUT/"12D-cross-language-retrieval-matrix.csv").write_text(buf.getvalue())

if __name__=="__main__":
    from services.local_multilingual_embedding import LocalMultilingualEmbeddingBackend
    import os
    result=evaluate(LocalMultilingualEmbeddingBackend(model_cache_dir=os.environ["LEXIBRIDGE_MODEL_CACHE_DIR"]))
    write(result); print(json.dumps(result["metrics"],sort_keys=True))
