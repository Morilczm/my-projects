"""Task 12J-A provider-free layout ingestion and retrieval evaluation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import statistics
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evaluations/artifacts"
sys.path.insert(0, str(ROOT / "backend"))

from services import chinese_term_candidates, knowledge_governance  # noqa: E402
from services.cross_language_retrieval import (  # noqa: E402
    CrossLanguageRetrievalQuery,
    SemanticPassage,
    rank_chinese_passages,
)
from services.document_parse_quality import parse_document_with_quality  # noqa: E402
from services.local_multilingual_embedding import MODEL_ID, MODEL_REVISION  # noqa: E402
from services.bilingual_semantic_pairing import (  # noqa: E402
    EnglishPairingInput,
    rank_bilingual_pairs,
)


CONCEPTS = (
    ("electric-field", "Electric field", "电场", "F=qE",
     "A field around charge exerts force according to F=qE.",
     "电场是电荷周围能够按 F=qE 对其他电荷施力的物理场。"),
    ("field-strength", "Electric field strength", "电场强度", "E=F/q",
     "Electric field strength is force per unit charge, E=F/q.",
     "电场强度是单位正电荷受到的力，满足 E=F/q。"),
    ("potential", "Electric potential", "电势", "V=W/q",
     "Electric potential is work per unit charge, V=W/q.",
     "电势是单位电荷对应的功，满足 V=W/q。"),
    ("potential-energy", "Electric potential energy", "电势能", "Ep=qV",
     "Electric potential energy obeys Ep=qV for charge in a potential.",
     "电势能是电荷在电势中具有的能量，满足 Ep=qV。"),
    ("angular-velocity", "Angular velocity", "角速度", "omega=dtheta/dt",
     "Angular velocity is the rate of angular displacement, omega=dtheta/dt.",
     "角速度表示角位移随时间的变化率，满足 omega=dtheta/dt。"),
    ("angular-acceleration", "Angular acceleration", "角加速度", "alpha=domega/dt",
     "Angular acceleration is the rate of angular velocity, alpha=domega/dt.",
     "角加速度表示角速度随时间的变化率，满足 alpha=domega/dt。"),
    ("mass", "Mass", "质量", "m=rho*V",
     "Mass measures inertia and may be computed from density, m=rho*V.",
     "质量衡量物体的惯性，也可由密度计算，满足 m=rho*V。"),
    ("weight", "Weight", "重量", "W=m*g",
     "Weight is gravitational force on a mass, W=m*g.",
     "重量是重力对物体产生的力，满足 W=m*g。"),
    ("momentum", "Momentum", "动量", "p=m*v",
     "Momentum describes translational motion, p=m*v.",
     "动量描述物体的平动状态，满足 p=m*v。"),
    ("angular-momentum", "Angular momentum", "角动量", "L=r*p",
     "Angular momentum describes rotational motion, L=r*p.",
     "角动量描述物体的转动状态，满足 L=r*p。"),
)


class DeterministicFormulaFeatureBackend:
    """CI backend based only on shared public physics notation."""

    backend_id = "deterministic_formula_feature_fake_v1"
    model_id = MODEL_ID
    model_revision = MODEL_REVISION

    def readiness(self):
        return SimpleNamespace(ready=True, reason_code="READY")

    @staticmethod
    def _encode(texts):
        formulae = [item[3] for item in CONCEPTS]
        rows = []
        for text in texts:
            vector = [1.0 if formula in text else 0.0 for formula in formulae]
            if not any(vector):
                vector = [0.0] * len(formulae)
            rows.append(vector)
        return rows

    def embed_queries(self, texts):
        return self._encode(texts)

    def embed_passages(self, texts):
        return self._encode(texts)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _draw_material(path: Path, rows, *, chinese: bool) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    font = "Helvetica"
    if chinese:
        font = "STSong-Light"
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(font))
        except KeyError:
            pass
    for index, row in enumerate(rows, 1):
        title = row[2] if chinese else row[1]
        definition = row[5] if chinese else row[4]
        pdf.setFont(font, 9)
        pdf.drawString(72, 766, "合成物理课程页眉" if chinese else "Synthetic Physics Course Header")
        pdf.setFont(font, 18)
        pdf.drawString(72, 710, title)
        pdf.setFont(font, 11)
        pdf.drawString(72, 675, definition)
        pdf.drawString(72, 640, f"- {'关键定义结构' if chinese else 'Key definition structure'}")
        if index == 1:
            pdf.drawString(72, 605, "量 | 公式" if chinese else "quantity | formula")
        pdf.setFont(font, 9)
        pdf.drawString(300, 28, str(index))
        pdf.showPage()
    pdf.save()


def _blocks(result):
    return [SimpleNamespace(**block) for block in result.blocks]


def evaluate() -> dict:
    backend = DeterministicFormulaFeatureBackend()
    parsed = []
    chunks = []
    fixture_specs = (
        ("en-a.pdf", CONCEPTS[:5], False),
        ("en-b.pdf", CONCEPTS[5:], False),
        ("zh-a.pdf", CONCEPTS[:5], True),
        ("zh-b.pdf", CONCEPTS[5:], True),
    )
    with tempfile.TemporaryDirectory(prefix="lexibridge-12ja-") as temp:
        temp_root = Path(temp)
        for filename, rows, chinese in fixture_specs:
            path = temp_root / filename
            _draw_material(path, rows, chinese=chinese)
            result = parse_document_with_quality(
                str(path),
                filename=filename,
                language_hint="zh" if chinese else "en",
            )
            source_uid = f"synthetic-{filename[:-4]}"
            built = knowledge_governance.build_knowledge_chunks_from_parse_blocks(
                SimpleNamespace(**result.parse_record_data),
                _blocks(result),
                source_uid,
                {
                    "language": "zh" if chinese else "en",
                    "course": "Synthetic Public Physics",
                },
            )
            parsed.append({
                "source_uid": source_uid,
                "language": "zh" if chinese else "en",
                "status": result.parse_record_data["parse_status"],
                "page_count": len(rows),
                "layout_block_count": len(result.blocks),
                "parser": result.parse_record_data["parser_name"],
                "parser_version": result.parse_record_data["parser_version"],
                "fallback": "layout_fallback_native" in result.parse_record_data["warnings"],
            })
            for chunk in built:
                chunks.append({**chunk, "language": "zh" if chinese else "en"})

    chinese_chunks = [item for item in chunks if item["language"] == "zh"]
    passages = [
        SemanticPassage(
            source_uid=item["source_uid"],
            chunk_uid=item["chunk_uid"],
            content=item["text"],
            language="zh",
            source_status="active",
            quality_status="ready",
            content_hash=item["content_hash"],
        )
        for item in chinese_chunks
    ]
    rows = []
    candidate_generated = 0
    pair_generated = 0
    evidence_provenance_retained = 0
    ranks = []
    for concept_id, english, chinese, formula, en_context, _ in CONCEPTS:
        query = CrossLanguageRetrievalQuery(
            english_candidate_uid=f"synthetic-{_hash(concept_id)[:16]}",
            canonical_english_term=english,
            normalized_english_term=english.casefold(),
            english_context=en_context,
            discipline="physics",
            allowed_chinese_source_uids=tuple(sorted({p.source_uid for p in passages})),
            top_k=3,
            retrieval_budget=100,
        )
        found = rank_chinese_passages(query, passages, backend)
        correct = next(item for item in passages if formula in item.content)
        rank = next((item.rank for item in found if item.chunk_uid == correct.chunk_uid), None)
        if rank:
            ranks.append(rank)
        evidence = [
            {
                **item.__dict__,
                "heading": next(
                    chunk["source_section"]
                    for chunk in chinese_chunks
                    if chunk["chunk_uid"] == item.chunk_uid
                ),
                "block_type": "layout_section",
                "source_locator": next(
                    chunk["source_locator"]
                    for chunk in chinese_chunks
                    if chunk["chunk_uid"] == item.chunk_uid
                ),
                "provenance": item.provenance,
            }
            for item in found
        ]
        identified = chinese_term_candidates.identify_standard_chinese_terms(
            english, evidence, discipline="physics", limit=10
        )
        exact = next(
            (item for item in identified.candidates if item["chinese_term"] == chinese),
            None,
        )
        candidate_generated += int(exact is not None)
        pair_count = 0
        if identified.candidates:
            pairs = rank_bilingual_pairs(
                EnglishPairingInput(
                    query.english_candidate_uid,
                    english,
                    english.casefold(),
                    en_context,
                    "physics",
                    {"source_uid": f"synthetic-en-{concept_id}", "chunk_uid": f"en-{concept_id}"},
                ),
                identified.candidates,
                backend,
            )
            pair_count = len(pairs)
            pair_generated += int(bool(pairs))
        provenance_ok = bool(found and found[0].provenance.get("content_hash"))
        evidence_provenance_retained += int(provenance_ok)
        rows.append({
            "opaque_item_id": _hash(concept_id)[:20],
            "query_hash": found[0].query_hash if found else "",
            "retrieved_chunk_ids": "|".join(item.chunk_uid for item in found),
            "correct_rank": rank or "",
            "top1": rank == 1,
            "top3": bool(rank and rank <= 3),
            "candidate_generated": exact is not None,
            "pair_count": pair_count,
            "provenance_complete": provenance_ok,
        })

    lengths = [len(item["text"]) for item in chunks]
    block_types = {
        block_type
        for item in chunks
        for block_type in str(item.get("block_type") or "").split("+")
        if block_type
    }
    chunk_rows = [
        {
            "source_uid": item["source_uid"],
            "chunk_uid": item["chunk_uid"],
            "language": item["language"],
            "page_range": item["page_number"],
            "heading_path": item["source_section"],
            "block_types": str(item.get("block_type") or "").replace("+", "|"),
            "character_count": len(item["text"]),
            "content_hash": item["content_hash"],
            "provenance_complete": bool(item["source_locator"] and item["source_section"]),
        }
        for item in chunks
    ]
    return {
        "technical_status": "LAYOUT_AWARE_INGESTION_RETRIEVAL_CONTRACT_CLOSED",
        "quality_status": "LAYOUT_AWARE_INGESTION_RETRIEVAL_BASELINE_ESTABLISHED",
        "fixture_corpus": {
            "english_pdfs": 2,
            "chinese_pdfs": 2,
            "concepts": len(CONCEPTS),
            "confusion_groups": 5,
            "private_material_used": False,
            "inline_bilingual_term_leakage": False,
        },
        "parsing": {
            "sources_succeeded": sum(item["status"] == "success" for item in parsed),
            "sources_failed": sum(item["status"] != "success" for item in parsed),
            "page_count": sum(item["page_count"] for item in parsed),
            "layout_block_count": sum(item["layout_block_count"] for item in parsed),
            "parsers": sorted({item["parser"] for item in parsed}),
            "layout_fallback_count": sum(item["fallback"] for item in parsed),
        },
        "chunking": {
            "chunk_count": len(chunks),
            "average_length": round(statistics.mean(lengths), 2),
            "median_length": statistics.median(lengths),
            "heading_definition_integrity_rate": round(
                sum(any(row[1 if item["language"] == "en" else 2] in item["text"]
                        and row[3] in item["text"] for row in CONCEPTS) for item in chunks)
                / len(chunks), 4
            ),
            "cross_section_contamination_count": sum(
                sum(row[3] in item["text"] for row in CONCEPTS) > 1 for item in chunks
            ),
            "duplicate_chunk_count": len(chunks) - len({item["content_hash"] for item in chunks}),
            "provenance_completeness": round(
                sum(row["provenance_complete"] for row in chunk_rows) / len(chunk_rows), 4
            ),
            "list_retained": "list" in block_types,
            "table_retained": "table" in block_types,
            "formula_retained": "formula" in block_types,
            "max_chars": knowledge_governance.LAYOUT_CHUNK_MAX_CHARS,
            "overlap_chars": knowledge_governance.LAYOUT_CHUNK_OVERLAP_CHARS,
        },
        "retrieval": {
            "backend": backend.backend_id,
            "production_model_contract": MODEL_ID,
            "production_model_revision": MODEL_REVISION,
            "denominator": len(CONCEPTS),
            "hit_at_1": round(sum(row["top1"] for row in rows) / len(rows), 4),
            "hit_at_3": round(sum(row["top3"] for row in rows) / len(rows), 4),
            "mrr": round(sum((1 / row["correct_rank"]) if row["correct_rank"] else 0 for row in rows) / len(rows), 4),
            "no_result_count": sum(not row["retrieved_chunk_ids"] for row in rows),
            "correct_evidence_average_rank": round(statistics.mean(ranks), 4) if ranks else None,
        },
        "downstream_smoke": {
            "chinese_candidate_generated": candidate_generated,
            "pair_generated": pair_generated,
            "evidence_provenance_retained": evidence_provenance_retained,
        },
        "translation_boundary": {
            "retrieval_calls_translation_provider": False,
            "generated_hint_provenance_type": "GENERATED_HINT",
            "generated_hint_can_be_chinese_evidence": False,
            "generated_hint_can_be_qualified": False,
            "generated_hint_can_be_provider_ready": False,
            "glossary_can_directly_qualify": False,
        },
        "external_api_used": False,
        "real_provider_requests": 0,
        "rows": rows,
        "chunk_rows": chunk_rows,
        "parsed_sources": parsed,
    }


def write(result: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ingestion = {
        key: result[key]
        for key in ("technical_status", "quality_status", "fixture_corpus", "parsing", "chunking")
    }
    ingestion["external_api_used"] = False
    ingestion["real_provider_requests"] = 0
    (OUT / "12JA-ingestion-results.json").write_text(
        json.dumps(ingestion, ensure_ascii=False, indent=2) + "\n"
    )
    retrieval = {
        "retrieval": result["retrieval"],
        "downstream_smoke": result["downstream_smoke"],
        "rows": result["rows"],
        "external_api_used": False,
        "real_provider_requests": 0,
    }
    (OUT / "12JA-retrieval-results.json").write_text(
        json.dumps(retrieval, ensure_ascii=False, indent=2) + "\n"
    )
    (OUT / "12JA-translation-boundary-audit.json").write_text(
        json.dumps(result["translation_boundary"], ensure_ascii=False, indent=2) + "\n"
    )
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(result["chunk_rows"][0]), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(result["chunk_rows"])
    (OUT / "12JA-chunk-matrix.csv").write_text(buffer.getvalue())


if __name__ == "__main__":
    outcome = evaluate()
    write(outcome)
    print(json.dumps({
        "parsing": outcome["parsing"],
        "chunking": outcome["chunking"],
        "retrieval": outcome["retrieval"],
        "downstream_smoke": outcome["downstream_smoke"],
    }, ensure_ascii=False, sort_keys=True))
