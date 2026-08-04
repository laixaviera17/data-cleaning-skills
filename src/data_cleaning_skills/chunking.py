"""Memory-bounded CSV processing with explicit semantic safety constraints."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .errors import SkillConfigurationError
from .validation import validate_pipeline_rules
from .workflow import load_workflow_tools


@dataclass(frozen=True)
class ChunkMetrics:
    """Counters for one source chunk, including global exact duplicates."""

    chunk_index: int
    input_rows: int
    output_rows: int
    cross_chunk_duplicate_rows: int


@dataclass(frozen=True)
class ChunkResult:
    """One processed output chunk and its normalized Pipeline report."""

    dataframe: pd.DataFrame
    report: Mapping[str, Any]
    metrics: ChunkMetrics


def iter_clean_csv(
    input_path: str | Path,
    rules: Mapping[str, Any],
    *,
    chunksize: int = 50_000,
    runner: Callable[..., tuple[pd.DataFrame, dict[str, Any]]] | None = None,
) -> Iterator[ChunkResult]:
    """Yield cleaned CSV chunks while preserving global exact-key uniqueness.

    Field mapping and similarity deduplication are rejected because they need a
    different state/index strategy to guarantee equivalence with whole-file
    execution. The function never concatenates all outputs in memory.
    """
    path = Path(input_path)
    if path.suffix.lower() != ".csv":
        raise ValueError("chunked processing currently supports CSV input only")
    if chunksize < 1:
        raise ValueError("chunksize must be positive")
    _validate_chunk_safe_rules(rules)
    validate_pipeline_rules(rules)

    key_groups = _unique_key_groups(rules.get("unique_keys"))
    seen_by_group: list[set[tuple[Any, ...]]] = [set() for _ in key_groups]
    execute = runner or load_workflow_tools()["process_dataframe"]
    runtime_rules = deepcopy(dict(rules))

    for chunk_index, chunk in enumerate(pd.read_csv(path, chunksize=chunksize, keep_default_na=False), start=1):
        input_rows = len(chunk)
        filtered, cross_chunk_duplicates = _exclude_seen_keys(chunk, key_groups, seen_by_group)
        processed, report = execute(filtered, runtime_rules)
        normalized_report = dict(report)
        normalized_report["input_rows"] = input_rows
        normalized_report["cross_chunk_duplicate_rows"] = cross_chunk_duplicates
        normalized_report["duplicate_rows"] = int(report.get("duplicate_rows", 0)) + cross_chunk_duplicates
        normalized_report["removed_rows"] = int(report.get("removed_rows", 0)) + cross_chunk_duplicates
        yield ChunkResult(
            dataframe=processed,
            report=normalized_report,
            metrics=ChunkMetrics(
                chunk_index=chunk_index,
                input_rows=input_rows,
                output_rows=len(processed),
                cross_chunk_duplicate_rows=cross_chunk_duplicates,
            ),
        )


def _validate_chunk_safe_rules(rules: Mapping[str, Any]) -> None:
    mapping = rules.get("field_mapping")
    if isinstance(mapping, Mapping) and mapping.get("enabled", False):
        raise SkillConfigurationError("chunked processing does not support enabled field_mapping")
    unique_keys = rules.get("unique_keys")
    if isinstance(unique_keys, Mapping):
        similarity = unique_keys.get("similarity")
        if isinstance(similarity, Mapping) and similarity.get("enabled", False):
            raise SkillConfigurationError("chunked processing does not support similarity deduplication")


def _unique_key_groups(config: Any) -> list[tuple[str, ...]]:
    raw_groups = config.get("keys", []) if isinstance(config, Mapping) else config
    if not isinstance(raw_groups, list):
        return []
    groups: list[tuple[str, ...]] = []
    for raw_group in raw_groups:
        if isinstance(raw_group, str) and raw_group:
            groups.append((raw_group,))
        elif isinstance(raw_group, list) and raw_group and all(isinstance(value, str) and value for value in raw_group):
            groups.append(tuple(raw_group))
    return groups


def _exclude_seen_keys(
    dataframe: pd.DataFrame,
    key_groups: list[tuple[str, ...]],
    seen_by_group: list[set[tuple[Any, ...]]],
) -> tuple[pd.DataFrame, int]:
    if not key_groups:
        return dataframe.copy(), 0
    missing = sorted({field for group in key_groups for field in group if field not in dataframe.columns})
    if missing:
        raise SkillConfigurationError("chunked unique key fields are missing: " + ", ".join(missing))

    keep_indices: list[Any] = []
    pending_by_group: list[set[tuple[Any, ...]]] = [set() for _ in key_groups]
    cross_chunk_duplicates = 0
    for index, row in dataframe.iterrows():
        keys = [_row_key(row, group) for group in key_groups]
        if any(key in seen for key, seen in zip(keys, seen_by_group, strict=True)):
            cross_chunk_duplicates += 1
            continue
        keep_indices.append(index)
        for key, pending in zip(keys, pending_by_group, strict=True):
            pending.add(key)

    for seen, pending in zip(seen_by_group, pending_by_group, strict=True):
        seen.update(pending)
    return dataframe.loc[keep_indices].copy(), cross_chunk_duplicates


def _row_key(row: pd.Series, fields: tuple[str, ...]) -> tuple[Any, ...]:
    values = []
    for field in fields:
        value = row[field]
        values.append(None if pd.isna(value) else value)
    return tuple(values)
