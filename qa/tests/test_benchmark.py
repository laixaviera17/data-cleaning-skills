from __future__ import annotations

from benchmarks.benchmark_chunked_pipeline import benchmark_chunked
from benchmarks.benchmark_pipeline import benchmark, generate_dataset


def test_benchmark_dataset_is_deterministic():
    assert generate_dataset(5).to_dict(orient="records") == generate_dataset(5).to_dict(orient="records")


def test_benchmark_smoke_run_returns_metrics():
    result = benchmark(row_count=20, iterations=1)

    assert result["rows"] == 20
    assert result["iterations"] == 1
    assert result["rows_per_second"] > 0
    assert result["peak_python_memory_mb"] > 0


def test_chunked_benchmark_smoke_run_returns_metrics():
    result = benchmark_chunked(row_count=20, chunksize=7)

    assert result["rows"] == 20
    assert result["chunk_count"] == 3
    assert result["rows_per_second"] > 0
    assert result["peak_python_memory_mb"] > 0
