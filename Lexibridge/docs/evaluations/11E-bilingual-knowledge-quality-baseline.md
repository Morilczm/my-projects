# Task 11E Bilingual Knowledge Quality Baseline

## Executive Conclusion

- Status: `BILINGUAL_KNOWLEDGE_QUALITY_VALIDATION_BLOCKED`
- Blocker: `FORMAL_WORKFLOW_PROVIDER_POLICY_ONLY_ALLOWS_MOCK_RULE_V1`
- Dominant failure stage: `PROVIDER_FAILURE`
- Current quality verdict: real semantic quality baseline is not established when the Formal Workflow only permits mock alignment verification.

## Corpus And Gold

- Course: Synthetic Physics Quality Pilot 11E
- Concept count: 25
- Corpus SHA-256: `33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc`
- Gold SHA-256: `199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302`
- Frozen before run: true

## Runtime

- Temporary DB: `/var/folders/7q/_0ffnnxj2wb8hvm0b77w647m0000gn/T/lexibridge-11e-lozzuq1u/11e-evaluation.sqlite`
- Provider: `mock-rule-v1`
- Model: `mock-rule-v1:v1`
- Provider requests: 0
- Provider preflight: `REAL_PROVIDER_UNAVAILABLE`

## Metrics

| Metric | Result | Threshold | Pass |
| ------ | -----: | --------: | :--: |
| `candidate_recall` | 0.0000 | 0.88 | False |
| `chinese_term_top1_accuracy` | 0.0000 | 0.8 | False |
| `chinese_term_top3_accuracy` | 0.0000 | 0.92 | False |
| `english_hit_at_3` | 0.2400 | 0.9 | False |
| `chinese_hit_at_3` | 1.0000 | 0.85 | True |
| `bilingual_evidence_completeness` | 0.2400 | 0.8 | False |
| `term_pair_accuracy` | 0.0000 | 0.8 | False |
| `unsupported_claim_rate` | 1.0000 | 0.1 | False |
| `critical_confusion_count` | 0 | 0 | True |
| `source_reference_completeness` | 1.0000 | 1.0 | True |
| `chunk_reference_completeness` | 1.0000 | 1.0 | True |
| `approve_proxy_rate` | 0.0000 | 0.6 | False |
| `reject_proxy_rate` | 1.0000 | 0.15 | False |

## Concept-Level Results

| Concept | EN Retrieval | ZH Retrieval | Term Pair | Explanation | Proxy Decision | Attribution |
| ------- | ------------ | ------------ | --------- | ----------- | -------------- | ----------- |
| physics-01 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-02 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-03 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-04 | hit@3 | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-05 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-06 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-07 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-08 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-09 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-10 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-11 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-12 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-13 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-14 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-15 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-16 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-17 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-18 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-19 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-20 | miss | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-21 | hit@3 | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-22 | hit@3 | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-23 | hit@3 | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-24 | hit@3 | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |
| physics-25 | hit@3 | hit@3 | wrong | 0 | reject | PROVIDER_FAILURE |

## Confusion Analysis

- speed / velocity, momentum / impulse, work / energy, electric potential / potential difference, and angular momentum / torque are present in the synthetic corpus and gold confusions.
- Confusion outcomes are recorded in `critical_confusion_count` and per-concept results.

## Provenance

- Source reference completeness: 1.0000
- Chunk reference completeness: 1.0000
- Page/bbox is not expected for simple text uploads; missing geometry is reported as location unavailable, not fabricated.

## Safety

- Accident DB before hash: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- Accident DB after hash: `9e6fb68ab13dff2763e2fff18d2aee531486360c557f058eb8a471d9209a9eaa`
- Private data egress: 0
- External document API requests: 0
- Synthetic Provider egress: 0

## Remaining Limitations

- Synthetic corpus only; no real teacher blind review.
- Real semantic quality is blocked unless a production allowlisted Provider is available through the Formal Workflow policy.
- Complex PDF parsing is outside Task 11E.
- Production embedding/vector retrieval is not implemented in this task.
- Formula structure recognition, LaTeX, and MathML are outside this task.
