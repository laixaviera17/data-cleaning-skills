#!/usr/bin/env python3
"""Compare datasets before and after cleaning."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from dataset_diff_file_utils import load_dataset, save_csv, save_json_dict


ADDED_REMOVED_COLUMNS = ["record_key", "source_row", "record_hash", "raw_record"]
CHANGED_COLUMNS = [
    "record_key",
    "field",
    "before_value",
    "after_value",
    "before_source_row",
    "after_source_row",
    "before_record_hash",
    "after_record_hash",
]
FIELD_SUMMARY_COLUMNS = ["field", "changed_cells"]


def compare_dataframes(before_dataframe: pd.DataFrame, after_dataframe: pd.DataFrame, key_fields: list[str]) -> dict[str, Any]:
    """Compare two DataFrames and return diff artifacts plus summary."""
    if not isinstance(before_dataframe, pd.DataFrame) or not isinstance(after_dataframe, pd.DataFrame):
        raise TypeError("before_dataframe 和 after_dataframe 必须是 pandas.DataFrame")
    normalized_keys = _normalize_key_fields(key_fields)
    _validate_key_fields(before_dataframe, after_dataframe, normalized_keys)

    before = before_dataframe.copy()
    after = after_dataframe.copy()
    before["_record_key"] = _record_keys(before, normalized_keys)
    after["_record_key"] = _record_keys(after, normalized_keys)
    _validate_unique_keys(before, after)

    before_keys = set(before["_record_key"])
    after_keys = set(after["_record_key"])
    added_keys = sorted(after_keys - before_keys)
    removed_keys = sorted(before_keys - after_keys)
    common_keys = sorted(before_keys & after_keys)

    added_rows = _record_rows(after, added_keys)
    removed_rows = _record_rows(before, removed_keys)
    changed_rows = _changed_rows(before, after, common_keys)
    field_summary = _field_summary(changed_rows)
    summary = {
        "before_rows": len(before_dataframe),
        "after_rows": len(after_dataframe),
        "added_rows": len(added_rows),
        "removed_rows": len(removed_rows),
        "changed_records": int(changed_rows["record_key"].nunique()) if not changed_rows.empty else 0,
        "changed_cells": len(changed_rows),
        "compared_fields": len(_compare_fields(before_dataframe, after_dataframe, normalized_keys)),
        "key_fields": normalized_keys,
        "lineage_fields": [field for field in ["_source_file", "_source_row", "_record_hash", "_batch_id", "_rule_version"] if field in set(before.columns) | set(after.columns)],
    }
    return {
        "summary": summary,
        "added_rows": added_rows,
        "removed_rows": removed_rows,
        "changed_rows": changed_rows,
        "field_change_summary": field_summary,
    }


def compare_dataset_files(
    before_path: str | Path,
    after_path: str | Path,
    key_fields: list[str] | str,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Compare dataset files and write diff outputs."""
    before_dataframe = load_dataset(before_path)
    after_dataframe = load_dataset(after_path)
    diff = compare_dataframes(before_dataframe, after_dataframe, _parse_key_fields(key_fields))

    output_directory = Path(output_dir)
    summary_path = output_directory / "diff_summary.json"
    added_path = output_directory / "added_rows.csv"
    removed_path = output_directory / "removed_rows.csv"
    changed_path = output_directory / "changed_rows.csv"
    field_summary_path = output_directory / "field_change_summary.csv"

    save_json_dict(diff["summary"], summary_path)
    save_csv(diff["added_rows"], added_path)
    save_csv(diff["removed_rows"], removed_path)
    save_csv(diff["changed_rows"], changed_path)
    save_csv(diff["field_change_summary"], field_summary_path)
    return {
        "diff_summary": summary_path,
        "added_rows": added_path,
        "removed_rows": removed_path,
        "changed_rows": changed_path,
        "field_change_summary": field_summary_path,
    }


def _normalize_key_fields(key_fields: list[str]) -> list[str]:
    keys = [field.strip() for field in key_fields if isinstance(field, str) and field.strip()]
    if not keys:
        raise ValueError("key_fields 不能为空")
    return keys


def _parse_key_fields(key_fields: list[str] | str) -> list[str]:
    if isinstance(key_fields, str):
        return [field.strip() for field in key_fields.split(",") if field.strip()]
    return _normalize_key_fields(key_fields)


def _validate_key_fields(before: pd.DataFrame, after: pd.DataFrame, key_fields: list[str]) -> None:
    missing_before = [field for field in key_fields if field not in before.columns]
    missing_after = [field for field in key_fields if field not in after.columns]
    errors = []
    if missing_before:
        errors.append(f"清洗前数据缺少主键字段: {', '.join(missing_before)}")
    if missing_after:
        errors.append(f"清洗后数据缺少主键字段: {', '.join(missing_after)}")
    if errors:
        raise ValueError("; ".join(errors))


def _validate_unique_keys(before: pd.DataFrame, after: pd.DataFrame) -> None:
    duplicate_before = before["_record_key"][before["_record_key"].duplicated()].unique().tolist()
    duplicate_after = after["_record_key"][after["_record_key"].duplicated()].unique().tolist()
    errors = []
    if duplicate_before:
        errors.append(f"清洗前数据主键重复: {', '.join(map(str, duplicate_before[:5]))}")
    if duplicate_after:
        errors.append(f"清洗后数据主键重复: {', '.join(map(str, duplicate_after[:5]))}")
    if errors:
        raise ValueError("; ".join(errors))


def _record_keys(dataframe: pd.DataFrame, key_fields: list[str]) -> pd.Series:
    return dataframe[key_fields].astype(str).agg("|".join, axis=1)


def _record_rows(dataframe: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if not keys:
        return pd.DataFrame(columns=ADDED_REMOVED_COLUMNS)
    rows = []
    source = dataframe.set_index("_record_key", drop=False)
    for key in keys:
        record = source.loc[key].drop(labels=["_record_key"], errors="ignore").to_dict()
        rows.append(
            {
                "record_key": key,
                "source_row": _cell_value(record.get("_source_row", "")),
                "record_hash": _cell_value(record.get("_record_hash", "")),
                "raw_record": json.dumps(record, ensure_ascii=False, default=str),
            }
        )
    return pd.DataFrame(rows, columns=ADDED_REMOVED_COLUMNS)


def _changed_rows(before: pd.DataFrame, after: pd.DataFrame, common_keys: list[str]) -> pd.DataFrame:
    compare_fields = _compare_fields(
        before.drop(columns=["_record_key"], errors="ignore"),
        after.drop(columns=["_record_key"], errors="ignore"),
        [],
    )
    before_indexed = before.set_index("_record_key", drop=False)
    after_indexed = after.set_index("_record_key", drop=False)
    rows = []
    for key in common_keys:
        before_row = before_indexed.loc[key]
        after_row = after_indexed.loc[key]
        for field in compare_fields:
            before_value = _cell_value(before_row.get(field, ""))
            after_value = _cell_value(after_row.get(field, ""))
            if before_value != after_value:
                rows.append(
                    {
                        "record_key": key,
                        "field": field,
                        "before_value": before_value,
                        "after_value": after_value,
                        "before_source_row": _cell_value(before_row.get("_source_row", "")),
                        "after_source_row": _cell_value(after_row.get("_source_row", "")),
                        "before_record_hash": _cell_value(before_row.get("_record_hash", "")),
                        "after_record_hash": _cell_value(after_row.get("_record_hash", "")),
                    }
                )
    return pd.DataFrame(rows, columns=CHANGED_COLUMNS)


def _compare_fields(before: pd.DataFrame, after: pd.DataFrame, key_fields: list[str]) -> list[str]:
    before_fields = set(before.columns)
    after_fields = set(after.columns)
    return sorted((before_fields | after_fields) - set(key_fields) - {"_record_key"})


def _field_summary(changed_rows: pd.DataFrame) -> pd.DataFrame:
    if changed_rows.empty:
        return pd.DataFrame(columns=FIELD_SUMMARY_COLUMNS)
    return (
        changed_rows["field"]
        .value_counts()
        .rename_axis("field")
        .reset_index(name="changed_cells")[FIELD_SUMMARY_COLUMNS]
    )


def _cell_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def main(argv: list[str]) -> int:
    """Run before/after dataset comparison from the command line."""
    if len(argv) != 5:
        print(
            json.dumps(
                {"error": "用法: python scripts/compare_datasets.py before.csv after.csv key_fields output_dir"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    try:
        outputs = compare_dataset_files(argv[1], argv[2], argv[3], argv[4])
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({key: str(value) for key, value in outputs.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
