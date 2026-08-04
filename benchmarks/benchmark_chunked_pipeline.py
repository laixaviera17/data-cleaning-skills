#!/usr/bin/env python3
"""Measure end-to-end CSV chunk processing without retaining all outputs."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

from data_cleaning_skills import iter_clean_csv

if __package__:
    from .benchmark_pipeline import _benchmark_rules, generate_dataset
else:
    from benchmark_pipeline import _benchmark_rules, generate_dataset


def benchmark_chunked(row_count: int, chunksize: int) -> dict[str, Any]:
    """Generate a temporary CSV and measure one streaming Pipeline pass."""
    if row_count < 1:
        raise ValueError("row_count must be positive")
    if chunksize < 1:
        raise ValueError("chunksize must be positive")

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "benchmark.csv"
        generate_dataset(row_count).to_csv(input_path, index=False)
        tracemalloc.start()
        started = time.perf_counter()
        output_rows = 0
        chunk_count = 0
        cross_chunk_duplicates = 0
        for result in iter_clean_csv(input_path, _benchmark_rules(), chunksize=chunksize):
            output_rows += len(result.dataframe)
            chunk_count += 1
            cross_chunk_duplicates += result.metrics.cross_chunk_duplicate_rows
        duration = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    return {
        "benchmark": "chunked_csv_default_pipeline",
        "data_classification": "deterministic_synthetic",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "rows": row_count,
        "chunksize": chunksize,
        "chunk_count": chunk_count,
        "seconds": round(duration, 6),
        "rows_per_second": round(row_count / duration, 2),
        "peak_python_memory_mb": round(peak_bytes / 1024 / 1024, 2),
        "output_rows": output_rows,
        "cross_chunk_duplicate_rows": cross_chunk_duplicates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--chunksize", type=int, default=10_000)
    args = parser.parse_args(argv)
    print(json.dumps(benchmark_chunked(args.rows, args.chunksize), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
