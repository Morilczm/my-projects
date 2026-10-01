# Cross-Corpus Benchmark V2

This frozen evaluation fixture models English-only course notes and separately
authored monolingual Chinese reference material. Corpus files are static and
are not generated from `gold.json`.

Gold is scorer-only. Production ingestion, extraction, retrieval, candidate
generation, pairing, and readiness never receive gold terms, aliases,
propositions, confusion sets, evidence labels, or concept IDs.

The fixture validates a controlled 25-concept physics funnel. It does not
validate OCR, broad textbook distributions, cross-discipline generalization,
large-scale performance, live knowledge updates, or teacher review accuracy.
