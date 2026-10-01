# Expected Demo Flow

This demo uses self-authored sample material and local SQLite data. It is designed for a repeatable course demonstration, not for measuring production accuracy.

Expected minimum result:

```text
Demo Flow Result:
- document ingestion: PASS
- alignment run: PASS
- cards generated: > 0
- QC cards: > 0
- auto approved cards: 0 when AI_PROVIDER=none/local/mock
- student search: PASS
- student feedback: PASS
- admin jobs: PASS
- evaluation run: PASS
- no evidence forced alignment rate: 0
```

Key checks:

- `Fourier Transform` in SP101 should not use `Hash Table` evidence.
- `Hash Table` in DS101 should not use `Fourier Transform` evidence.
- Formula-related items should be marked for review when no Formula OCR provider is configured.
- Student personal/demo actions should not publish private materials into course-public cards.
