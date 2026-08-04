# Pipeline benchmark

This benchmark measures the public in-memory workflow against deterministic synthetic data. It reports median wall time, throughput, and peak Python allocation measured by `tracemalloc`.

```bash
python benchmarks/benchmark_pipeline.py --rows 10000 --iterations 3
```

The result is a local engineering reference, not a cross-machine SLA. Run on the deployment machine with representative rules and data before capacity planning. Similarity deduplication and filesystem I/O are intentionally excluded so the benchmark isolates the default atomic-Skill path.

For a memory-bounded CSV pass that includes input parsing:

```bash
python benchmarks/benchmark_chunked_pipeline.py --rows 100000 --chunksize 10000
```

Chunk mode retains exact unique-key state but does not retain or concatenate processed output chunks. It rejects field mapping and similarity deduplication because those combinations do not yet have an equivalent cross-chunk implementation.
