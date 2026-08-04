# Five-minute interview guide

## 0:00–1:00 — Problem

“The project turns inconsistent CSV/JSON cleaning scripts into a reproducible data-quality delivery workflow. The business output is not only a cleaned table: it includes row-level findings, operation logs, before/after comparison, catalog metadata, documentation, checksums, and a portable delivery manifest.”

## 1:00–2:00 — Architecture

Show `docs/architecture.md`. Explain the boundary:

```text
Atomic Skill → Registry contract → DAG Pipeline → Rule policy
             → Evaluation → Human review → Validated delivery
```

Emphasize that atomic transformations do not own orchestration or delivery concerns, and Agent integration does not allow an LLM to bypass deterministic validation.

## 2:00–3:00 — Engineering evidence

- 12 independently documented Skills.
- Unit, boundary, workspace integration, contract, Agent, chunking, and benchmark tests.
- Branch coverage failure gate, Ruff, mypy, and Python 3.10–3.12 CI matrix.
- Draft 2020-12 validation of actual artifacts.
- Stable dataset IDs, SHA-256 manifest entries, and no absolute source paths.

Run `python scripts/run_recruiter_demo.py` and open `demo/output/delivery_manifest.json`.

## 3:00–4:00 — Trade-offs

Be explicit:

- Compatibility adapters still load legacy scripts from the checkout.
- Similarity deduplication is quadratic and intentionally excluded from the throughput benchmark.
- Chunk mode rejects field mapping and similarity deduplication until cross-chunk equivalence is implemented.
- The public case study is synthetic and does not claim a production deployment.

## 4:00–5:00 — Depth questions

Prepare to answer:

1. Why use a registry instead of importing scripts directly?
2. How does the DAG detect unknown Skills and cycles?
3. What makes a Skill atomic, and where should filesystem writes live?
4. How are schema contracts different from type hints?
5. Why is the Agent evaluator deterministic?
6. How would you implement distributed or similarity-aware deduplication?
7. Why is branch coverage gated at 75% rather than presenting the higher trace estimate?
8. How would you migrate compatibility modules fully into the installable package?

The strongest answer is not “everything is production-ready.” It is a precise explanation of what is proven, which trade-offs remain, and how the architecture supports the next step.
