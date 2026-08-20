# Evaluation

## How to run

```bash
cd backend
python eval/run_eval.py           # print the report
python eval/run_eval.py --check   # exit non-zero if thresholds fail (used in CI)
```

Default mode is fully offline and deterministic: 12 research questions across
three synthetic fixture filings (an annual report and a quarterly report for a
software company, and an annual report for a semiconductor company — all
clearly labeled synthetic, never presented as real SEC data), plus four
hand-labeled verification probes. Setting `LLM_PROVIDER=anthropic` runs the
identical harness against the real model.

## Metrics

| Metric | Definition |
|---|---|
| Citation validity | share of extracted evidence whose excerpt verifiably appears verbatim in the cited section |
| Claim support rate | share of claims verified as supported / partially supported |
| Unsupported-claim rate | share of claims blocked by verification |
| Blocked-claim leakage | blocked excerpts that appear in a final brief — **must be 0** |
| Retrieval relevance | recall of hand-labeled expected sections among the sections the pipeline selected (precision reported alongside) |
| Verification agreement | verifier verdicts matching hand-labeled probe expectations |
| Completion time | wall-clock seconds per research request (mean / max) |

Design notes:

- Retrieval is thresholded on **recall**, not precision: for evidence work the
  costly failure is missing the right section; an extra selected section only
  adds text the extractor can ignore. Precision is still reported (currently
  ~0.53 with the top-3 selector) because improving it is a stated future goal.
- Probe `p01-fabricated-citation` plants a quotation that does not exist in
  the filing. The harness asserts it is **blocked**; this is the
  required "extraction fabricates → verification blocks" scenario, and CI
  fails if it ever passes.
- Probe `p04-polarity-flip` pairs a "margin increased" claim with a "margin
  declined" source to catch directional errors.

## Current results (mock provider, 2026-08-20, Apple M-series laptop)

```
questions                  12
completed                  12
total_evidence             56
citation_validity          1.0
claim_support_rate         1.0
unsupported_claim_rate     0.0
blocked_claim_leaks        0
retrieval_relevance        1.0    (recall; precision 0.528)
verification_agreement     1.0    (4/4 probes)
fabricated_probe_blocked   True
mean_seconds               0.011
max_seconds                0.013
```

Read these numbers honestly: with the mock provider, citation validity is 1.0
**by construction** (the mock quotes real sentences), so the pipeline-level
metrics mainly prove the plumbing preserves grounding end-to-end. The numbers
that carry real signal in mock mode are the probe results (the verifier blocks
fabrications and polarity flips), zero leakage, retrieval recall, and latency.
Evaluating the real LLM provider on this same harness is the meaningful
model-quality measurement, and requires an API key.

## CI thresholds (`run_eval.py --check`)

- citation_validity ≥ 0.95
- claim_support_rate ≥ 0.60
- retrieval_relevance (recall) ≥ 0.75
- verification_agreement ≥ 0.75
- blocked_claim_leaks == 0
- fabricated citation probe blocked
- all runs complete

Thresholds are intentionally below the mock's perfect scores so the same gate
remains meaningful when the real provider (which is allowed to be imperfect)
is evaluated.
