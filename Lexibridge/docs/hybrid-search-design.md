# Hybrid Search Design

Hybrid search merges lexical and vector candidates.

```text
hybrid_score = lexical_weight * normalized_lexical_score
             + vector_weight * normalized_vector_score
```

Default local weights:

```text
HYBRID_LEXICAL_WEIGHT=0.55
HYBRID_VECTOR_WEIGHT=0.45
HYBRID_MIN_LEXICAL_GATE=0.20
```

The lexical gate prevents a high vector score from becoming strong evidence when there is no exact/alias match and no meaningful core-token overlap.

Source governance remains active: restricted sources cannot become public strong evidence, deprecated sources are downgraded, and removed sources are excluded.
