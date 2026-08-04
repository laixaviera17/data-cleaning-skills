#!/usr/bin/env python3
"""Measure deterministic in-memory Pipeline throughput and peak Python memory."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import tracemalloc
from typing import Any

import pandas as pd

from data_cleaning_skills import load_workflow_tools


def generate_dataset(row_count: int) -> pd.DataFrame:
    """Generate deterministic synthetic records with controlled quality issues."""
    if row_count < 1:
        raise ValueError("row_count must be positive")
    records = []
    for index in range(row_count):
        records.append(
            {
                "id": str(index),
                "title": f"record-{index}",
                "content": "benchmark content",
                "publish_date": "2026/08/03" if index % 10 else "bad-date",
                "source": "" if index % 20 == 0 else "portal",
                "amount": "12.30" if index % 25 else "invalid",
                "status": "active" if index % 50 else "unexpected",
                "score": index % 105,
            }
        )
    return pd.DataFrame.from_records(records)


def benchmark(row_count: int, iterations: int) -> dict[str, Any]:
    """Run the public DataFrame workflow and return machine-readable metrics."""
    if iterations < 1:
        raise ValueError("iterations must be positive")
    process_dataframe = load_workflow_tools()["process_dataframe"]
    dataframe = generate_dataset(row_count)
    rules = _benchmark_rules()
    process_dataframe(dataframe.head(min(100, row_count)), rules)

    durations = []
    peak_bytes = 0
    output_rows = 0
    for _ in range(iterations):
        tracemalloc.start()
        started = time.perf_counter()
        cleaned, _ = process_dataframe(dataframe, rules)
        durations.append(time.perf_counter() - started)
        _, iteration_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes = max(peak_bytes, iteration_peak)
        output_rows = len(cleaned)

    median_seconds = statistics.median(durations)
    return {
        "benchmark": "in_memory_default_pipeline",
        "data_classification": "deterministic_synthetic",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "rows": row_count,
        "iterations": iterations,
        "median_seconds": round(median_seconds, 6),
        "rows_per_second": round(row_count / median_seconds, 2),
        "peak_python_memory_mb": round(peak_bytes / 1024 / 1024, 2),
        "output_rows": output_rows,
        "durations_seconds": [round(value, 6) for value in durations],
    }


def _benchmark_rules() -> dict[str, Any]:
    return {
        "required_fields": [{"field": "id", "action": "mark"}],
        "unique_keys": {"keys": [["id"]]},
        "null_handling": {
            "null_values": [""],
            "strategies": [{"field": "source", "action": "fill", "fill_value": "unknown"}],
        },
        "date_rules": {
            "enabled": True,
            "date_format": "YYYY-MM-DD",
            "fields": [{"field": "publish_date", "input_formats": ["YYYY/MM/DD"]}],
        },
        "phone_rules": {"enabled": False, "fields": []},
        "amount_rules": {
            "enabled": True,
            "amount_precision": 2,
            "fields": [{"field": "amount", "decimal_places": 2}],
        },
        "enum_rules": {"fields": [{"field": "status", "allowed_values": ["active"]}]},
        "anomaly_rules": {"rules": [{"field": "score", "rule_type": "range", "min": 0, "max": 100}]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args(argv)
    print(json.dumps(benchmark(args.rows, args.iterations), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
