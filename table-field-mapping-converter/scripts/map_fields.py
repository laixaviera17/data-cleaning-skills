#!/usr/bin/env python3
"""Map source table fields to standard target field names."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from field_mapping_file_utils import load_dataset, load_mapping_csv, save_csv, save_dataset, save_json_dict


REQUIRED_MAPPING_COLUMNS = [
    "source_field",
    "target_field",
    "target_type",
    "required",
    "default_value",
    "description",
]
ISSUE_COLUMNS = ["source_field", "target_field", "issue_type", "reason", "action"]
UNMAPPED_COLUMNS = ["field", "reason"]


def process_dataframe(dataframe: pd.DataFrame, mapping_rules: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply field name mapping rules to an in-memory DataFrame.

    Args:
        dataframe: Source data.
        mapping_rules: Mapping rules as a DataFrame, list of dictionaries, or
            dictionary with a ``mappings`` list.

    Returns:
        A mapped DataFrame and a structured mapping report.
    """
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe 必须是 pandas.DataFrame")

    mappings = normalize_mapping_rules(mapping_rules)
    source_fields = list(dataframe.columns)
    mapped = dataframe.copy()
    issues: list[dict[str, Any]] = []

    duplicate_targets = _duplicate_targets(mappings)
    for rule in mappings:
        source_field = rule["source_field"]
        target_field = rule["target_field"]
        required = rule["required"]
        default_value = rule["default_value"]

        if not target_field:
            issues.append(_issue(source_field, target_field, "empty_target_field", "目标字段名为空", "skip"))
            continue
        if target_field in duplicate_targets:
            issues.append(
                _issue(
                    source_field,
                    target_field,
                    "duplicate_target_field",
                    f"多个源字段映射到同一目标字段: {target_field}",
                    "skip",
                )
            )
            continue
        if source_field not in source_fields:
            action = "fill_default" if required and default_value != "" else "report"
            issues.append(
                _issue(
                    source_field,
                    target_field,
                    "missing_required_source_field" if required else "missing_source_field",
                    f"源字段不存在: {source_field}",
                    action,
                )
            )
            if required and default_value != "" and target_field not in mapped.columns:
                mapped[target_field] = default_value
            continue
        mapped = mapped.rename(columns={source_field: target_field})

    mapped_source_fields = {rule["source_field"] for rule in mappings if rule["source_field"] in source_fields}
    unmapped_fields = [field for field in source_fields if field not in mapped_source_fields]
    unmapped_records = [{"field": field, "reason": "未在字段映射文件中配置，已保留原字段"} for field in unmapped_fields]

    report = {
        "input_fields": len(source_fields),
        "output_fields": len(mapped.columns),
        "mapped_fields": _mapped_field_count(mappings, source_fields, duplicate_targets),
        "unmapped_fields": len(unmapped_fields),
        "missing_required_fields": sum(1 for issue in issues if issue["issue_type"] == "missing_required_source_field"),
        "duplicate_target_fields": sum(1 for issue in issues if issue["issue_type"] == "duplicate_target_field"),
        "empty_target_fields": sum(1 for issue in issues if issue["issue_type"] == "empty_target_field"),
        "issues": issues,
        "unmapped_field_records": unmapped_records,
    }
    return mapped, report


def map_dataset(input_path: str | Path, mapping_path: str | Path, output_dir: str | Path) -> dict[str, Path]:
    """Map a dataset file and write standard output artifacts."""
    input_file = Path(input_path)
    dataframe = load_dataset(input_file)
    mappings = load_mapping_csv(mapping_path)
    mapped, report = process_dataframe(dataframe, mappings)

    output_directory = Path(output_dir)
    suffix = input_file.suffix.lower()
    mapped_path = output_directory / f"mapped_data{suffix}"
    report_path = output_directory / "field_mapping_report.json"
    unmapped_path = output_directory / "unmapped_fields.csv"
    issues_path = output_directory / "mapping_issues.csv"

    save_dataset(mapped, mapped_path)
    save_json_dict(_report_without_records(report), report_path)
    save_csv(pd.DataFrame(report["unmapped_field_records"], columns=UNMAPPED_COLUMNS), unmapped_path)
    save_csv(pd.DataFrame(report["issues"], columns=ISSUE_COLUMNS), issues_path)

    return {
        "mapped_data": mapped_path,
        "field_mapping_report": report_path,
        "unmapped_fields": unmapped_path,
        "mapping_issues": issues_path,
    }


def normalize_mapping_rules(mapping_rules: Any) -> list[dict[str, Any]]:
    """Normalize supported mapping rule inputs to dictionaries."""
    if isinstance(mapping_rules, pd.DataFrame):
        records = mapping_rules.to_dict(orient="records")
        columns = list(mapping_rules.columns)
    elif isinstance(mapping_rules, dict) and isinstance(mapping_rules.get("mappings"), list):
        records = mapping_rules["mappings"]
        columns = list(records[0].keys()) if records else []
    elif isinstance(mapping_rules, list):
        records = mapping_rules
        columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []
    else:
        raise TypeError("mapping_rules 必须是 DataFrame、规则列表或包含 mappings 的字典")

    if not records:
        raise ValueError("字段映射规则不能为空")

    missing_columns = [column for column in REQUIRED_MAPPING_COLUMNS if column not in columns]
    if missing_columns:
        raise ValueError(f"字段映射文件缺少必需列: {', '.join(missing_columns)}")

    normalized = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"字段映射第 {index} 行必须是字典")
        source_field = str(record.get("source_field", "")).strip()
        target_field = str(record.get("target_field", "")).strip()
        if not source_field:
            raise ValueError(f"字段映射第 {index} 行 source_field 不能为空")
        normalized.append(
            {
                "source_field": source_field,
                "target_field": target_field,
                "target_type": str(record.get("target_type", "")).strip(),
                "required": _to_bool(record.get("required", False)),
                "default_value": str(record.get("default_value", "")),
                "description": str(record.get("description", "")),
            }
        )
    return normalized


def _duplicate_targets(mappings: list[dict[str, Any]]) -> set[str]:
    counts: dict[str, int] = {}
    for rule in mappings:
        target_field = rule["target_field"]
        if target_field:
            counts[target_field] = counts.get(target_field, 0) + 1
    return {field for field, count in counts.items() if count > 1}


def _mapped_field_count(mappings: list[dict[str, Any]], source_fields: list[str], duplicate_targets: set[str]) -> int:
    return sum(
        1
        for rule in mappings
        if rule["source_field"] in source_fields and rule["target_field"] and rule["target_field"] not in duplicate_targets
    )


def _issue(source_field: str, target_field: str, issue_type: str, reason: str, action: str) -> dict[str, Any]:
    return {
        "source_field": source_field,
        "target_field": target_field,
        "issue_type": issue_type,
        "reason": reason,
        "action": action,
    }


def _report_without_records(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key not in {"issues", "unmapped_field_records"}}


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "1", "yes", "y", "required", "是", "必填"}


def main(argv: list[str]) -> int:
    """Run field mapping from the command line."""
    if len(argv) != 4:
        print(
            json.dumps(
                {"error": "用法: python scripts/map_fields.py input.csv field_mapping.csv output_dir"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    try:
        outputs = map_dataset(argv[1], argv[2], argv[3])
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({key: str(value) for key, value in outputs.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
