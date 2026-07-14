#!/usr/bin/env python3
"""Normalize structured issue outputs into standard issue_rows.csv."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from issue_list_file_utils import load_csv, load_json_dict, save_csv, save_json_dict


ISSUE_COLUMNS = [
    "row",
    "field",
    "value",
    "issue_type",
    "reason",
    "source_skill",
    "action",
    "record_id",
    "process_result",
    "raw_record",
]


def normalize_issue_records(records: list[dict[str, Any]], source_skill: str) -> list[dict[str, Any]]:
    """Normalize issue-like dictionaries to the shared issue schema."""
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            continue
        normalized.append(_normalize_record(record, source_skill))
    return normalized


def generate_issue_list(input_paths: list[str | Path], output_dir: str | Path) -> dict[str, Path]:
    """Generate standard issue list and summary files from issue outputs."""
    all_issues: list[dict[str, Any]] = []
    for input_path in input_paths:
        path = Path(input_path)
        source_skill = _infer_source_skill(path)
        all_issues.extend(_load_issues_from_file(path, source_skill))

    issue_frame = pd.DataFrame(all_issues, columns=ISSUE_COLUMNS)
    type_summary = _summary_frame(issue_frame, "issue_type", "issue_count")
    field_summary = _summary_frame(issue_frame, "field", "issue_count")
    summary = {
        "total_issues": len(issue_frame),
        "source_count": int(issue_frame["source_skill"].replace("", pd.NA).dropna().nunique()) if not issue_frame.empty else 0,
        "issue_type_count": int(issue_frame["issue_type"].replace("", pd.NA).dropna().nunique()) if not issue_frame.empty else 0,
        "field_count": int(issue_frame["field"].replace("", pd.NA).dropna().nunique()) if not issue_frame.empty else 0,
    }

    output_directory = Path(output_dir)
    issue_rows_path = output_directory / "issue_rows.csv"
    summary_path = output_directory / "issue_summary.json"
    type_summary_path = output_directory / "issue_type_summary.csv"
    field_summary_path = output_directory / "field_issue_summary.csv"

    save_csv(issue_frame, issue_rows_path)
    save_json_dict(summary, summary_path)
    save_csv(type_summary, type_summary_path)
    save_csv(field_summary, field_summary_path)

    return {
        "issue_rows": issue_rows_path,
        "issue_summary": summary_path,
        "issue_type_summary": type_summary_path,
        "field_issue_summary": field_summary_path,
    }


def _load_issues_from_file(path: Path, source_skill: str) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = load_csv(path)
        records = frame.to_dict(orient="records")
        return normalize_issue_records(records, source_skill)
    if suffix == ".json":
        data = load_json_dict(path)
        if "abnormal_records" in data and isinstance(data["abnormal_records"], list):
            return normalize_issue_records(data["abnormal_records"], source_skill)
        if "issues" in data and isinstance(data["issues"], list):
            return normalize_issue_records(data["issues"], source_skill)
        return normalize_issue_records([], source_skill)
    raise ValueError(f"不支持的问题文件类型: {suffix}; 支持类型: .csv, .json")


def _normalize_record(record: dict[str, Any], default_source_skill: str) -> dict[str, Any]:
    field = _first_present(record, ["field", "field_name", "source_field"])
    value = _first_present(record, ["value", "raw_value", "original_value"])
    issue_type = _first_present(record, ["issue_type", "reason"])
    reason = _first_present(record, ["reason", "message", "issue_reason", "issue_type"])
    source_skill = _first_present(record, ["source_skill"]) or default_source_skill
    action = _first_present(record, ["action", "suggested_action"]) or "report"
    raw_record = _first_present(record, ["raw_record"])

    if "target_field" in record and not raw_record:
        raw_record = json.dumps({"target_field": record.get("target_field", "")}, ensure_ascii=False)
    return {
        "row": _clean_value(_first_present(record, ["row", "row_id", "row_index"])),
        "field": _clean_value(field),
        "value": _clean_value(value),
        "issue_type": _clean_value(issue_type),
        "reason": _clean_value(reason),
        "source_skill": _clean_value(source_skill),
        "action": _clean_value(action),
        "record_id": _clean_value(_first_present(record, ["record_id"])),
        "process_result": _clean_value(_first_present(record, ["process_result"])),
        "raw_record": _clean_value(raw_record),
    }


def _summary_frame(issue_frame: pd.DataFrame, column: str, count_column: str) -> pd.DataFrame:
    if issue_frame.empty:
        return pd.DataFrame(columns=[column, count_column])
    summary = (
        issue_frame[column]
        .fillna("")
        .replace("", pd.NA)
        .dropna()
        .value_counts()
        .rename_axis(column)
        .reset_index(name=count_column)
    )
    return summary


def _infer_source_skill(path: Path) -> str:
    name = path.name.lower()
    if name.startswith("issue_rows"):
        return "issue-rows"
    if "mapping_issues" in name:
        return "table-field-mapping-converter"
    if "dictionary_issues" in name:
        return "field-dictionary-value-validator"
    if "abnormal_records" in name:
        return "abnormal-value-detector"
    return path.stem


def _first_present(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return ""


def _clean_value(value: Any) -> Any:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value


def main(argv: list[str]) -> int:
    """Run issue list generation from the command line."""
    if len(argv) < 3:
        print(
            json.dumps(
                {"error": "用法: python scripts/generate_issue_list.py input1.csv [input2.json ...] output_dir"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    try:
        outputs = generate_issue_list(argv[1:-1], argv[-1])
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({key: str(value) for key, value in outputs.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
