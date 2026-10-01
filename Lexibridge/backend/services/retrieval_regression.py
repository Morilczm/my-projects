"""Retrieval regression metrics for KB publishing gates."""

from __future__ import annotations


def evaluate_retrieval_cases(cases, retrieve_func) -> dict:
    results = []
    passed = 0
    negative_errors = 0
    forced_no_evidence = 0
    for case in cases:
        query = case.get("query") or case.get("english_term") or ""
        items = retrieve_func(case, query)
        top_text = "\n".join(str(item.get("content") or item.get("content_excerpt") or "") for item in items[:5])
        expected = str(case.get("expected_positive_chunk_text") or case.get("expected_chinese_evidence") or case.get("expected_english_evidence") or "")
        negative = str(case.get("negative_chunk_text") or case.get("negative_chinese_evidence") or case.get("negative_english_evidence") or "")
        no_evidence = bool(case.get("expect_no_evidence"))
        ok = True
        reason = ""
        if no_evidence:
            ok = not items
            if not ok:
                forced_no_evidence += 1
                reason = "expected no evidence but got results"
        elif expected:
            ok = expected[:40] in top_text or any(token and token in top_text for token in expected.split()[:3])
            if not ok:
                reason = "expected evidence not found"
        if negative and negative[:40] in top_text:
            ok = False
            negative_errors += 1
            reason = "negative evidence matched"
        if ok:
            passed += 1
        results.append({"query": query, "passed": ok, "failure_reason": reason, "result_count": len(items)})
    return {
        "status": "completed",
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "negative_match_errors": negative_errors,
        "no_evidence_forced_match": forced_no_evidence,
        "results": results,
    }
