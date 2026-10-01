# LexiBridge AI Retrieval Design

## Goal

The retrieval engine must return trustworthy evidence or return nothing. It must not fill terminology cards with unrelated chunks.

Core policy:

```text
No evidence passed threshold -> return []
No fallback to latest chunks
No mock evidence
No semantic-only pass
```

## Metadata Hard Filter

Retrieval applies hard filters before scoring:

- English evidence only accepts `language in ["en", "bilingual"]`.
- Chinese evidence only accepts `language in ["zh", "bilingual"]`.
- English course evidence requires `knowledge_base_type = "en_course_kb"`.
- Chinese course evidence requires `knowledge_base_type = "zh_course_kb"`.
- Personal evidence requires `knowledge_base_type = "student_personal_kb"`.
- Course scope requires exact `course_id` and `visibility = "course"`.
- Personal scope requires exact `owner_user_id` and `visibility = "private"`.
- Global fallback only runs when `scope_type = "global"` is explicitly requested.

Student A cannot retrieve Student B personal chunks. Teachers do not retrieve student personal chunks by default.

## Text Normalization

The local engine normalizes punctuation, hyphens, case, and whitespace. Stopwords are removed from core evidence scoring:

```text
a, an, the, of, to, in, on, for, with, by, from,
and, or, is, are, was, were, be, been, being,
can, could, should, would, will, may, might,
this, that, these, those, it, its, as, at, into
```

Examples:

- `Fourier Transform` -> `fourier`, `transform`
- `Hash Table` -> `hash`, `table`

## Scoring Formula

`score_knowledge_chunk(query, chunk)` returns:

```json
{
  "evidence_score": 0.87,
  "score_breakdown": {
    "term_exact_or_alias_match": 1.0,
    "lexical_overlap_score": 0.82,
    "semantic_similarity_score": 0.0,
    "course_scope_score": 1.0,
    "discipline_match_score": 1.0,
    "source_quality_score": 0.8
  },
  "risk_flags": []
}
```

Formula:

```text
evidence_score =
0.30 * term_exact_or_alias_match
+ 0.20 * lexical_overlap_score
+ 0.20 * semantic_similarity_score
+ 0.15 * course_scope_score
+ 0.10 * discipline_match_score
+ 0.05 * source_quality_score
```

Current `retrieval_version = local_lexical_v1`. `semantic_similarity_score` is intentionally `0.0` because this Local MVP does not include a production embedding/reranker service.

## Thresholds

```text
evidence_score < 0.65 -> rejected
0.65 <= evidence_score < 0.80 -> weak
evidence_score >= 0.80 -> strong
```

Hard gates:

- `term_exact_or_alias_match = 0` and `lexical_overlap_score < 0.20` -> reject.
- `course_scope_score = 0` -> reject.
- private owner mismatch -> reject.
- restricted source without derivative permission -> reject.
- semantic similarity alone cannot pass.

## Examples

Expected matches:

- `Fourier Transform` -> `Fourier Transform converts a time-domain signal...`
- `Fourier Transform` -> `傅里叶变换用于将时域信号表示为频率分量。`
- `Hash Table` -> `A hash table maps keys to buckets...`
- `Hash Table` -> `哈希表通过哈希函数将关键字映射到桶...`

Expected non-matches:

- `Fourier Transform` != `Hash Table`
- `Hash Table` != `Fourier Transform`
- `Collision Resolution` != `卷积`
- No Chinese evidence -> `[]`
- No English evidence -> `[]`

## Card Generation Impact

- English evidence empty -> `alignment_status=no_en_evidence`, `status=needs_more_evidence`, confidence capped at 45.
- Chinese evidence empty -> `alignment_status=no_zh_evidence`, `status=needs_more_evidence`, confidence capped at 45.
- Weak evidence -> `status=pending_quality_control`.
- Domain mismatch -> `status=pending_quality_control`.
- `auto_approved` requires strong English evidence, strong Chinese evidence, live AI provider, no risk flags, and confidence >= 85.
