#!/usr/bin/env python3
"""Validate and standardize structured field values with a dictionary file."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from dictionary_file_utils import load_dataset, load_dictionary_csv, save_csv, save_dataset, save_json_dict


REQUIRED_DICTIONARY_COLUMNS = ["field_name", "raw_value", "standard_value", "allowed", "remark"]
ISSUE_COLUMNS = ["row", "field_name", "value", "issue_type", "reason", "action", "remark"]
CHANGE_COLUMNS = ["row", "field_name", "raw_value", "standard_value", "remark"]


def process_dataframe(dataframe: pd.DataFrame, dictionary_rules: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate and standardize DataFrame values with dictionary rules."""
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe 必须是 pandas.DataFrame")

    rules = normalize_dictionary_rules(dictionary_rules)
    processed = dataframe.copy()
    issues: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []

    dictionary_fields = sorted({rule["field_name"] for rule in rules})
    fields_by_name = _group_rules_by_field(rules)

    for field_name in dictionary_fields:
        field_rules = fields_by_name[field_name]
        if field_name not in processed.columns:
            issues.append(
                _issue(
                    row="",
                    field_name=field_name,
                    value="",
                    issue_type="missing_field",
                    reason=f"字典字段不存在于输入数据: {field_name}",
                    action="report",
                    remark="",
                )
            )
            continue

        for index, value in processed[field_name].items():
            raw_key = _value_key(value)
            rule = field_rules.get(raw_key)
            row_number = int(index) + 1 if isinstance(index, int) else index
            if rule is None:
                issues.append(
                    _issue(
                        row=row_number,
                        field_name=field_name,
                        value=value,
                        issue_type="unknown_dictionary_value",
                        reason=f"字段值未在字典中配置: {raw_key}",
                        action="report",
                        remark="",
                    )
                )
                continue
            if not rule["allowed"]:
                issues.append(
                    _issue(
                        row=row_number,
                        field_name=field_name,
                        value=value,
                        issue_type="disallowed_dictionary_value",
                        reason=f"字段值在字典中被标记为不允许: {raw_key}",
                        action="report",
                        remark=rule["remark"],
                    )
                )
                continue
            standard_value = rule["standard_value"]
            if standard_value != "" and raw_key != standard_value:
                processed.at[index, field_name] = standard_value
                changes.append(
                    {
                        "row": row_number,
                        "field_name": field_name,
                        "raw_value": raw_key,
                        "standard_value": standard_value,
                        "remark": rule["remark"],
                    }
                )

    report = {
        "input_rows": len(dataframe),
        "processed_fields": sum(1 for field in dictionary_fields if field in dataframe.columns),
        "changed_values": len(changes),
        "illegal_values": sum(1 for issue in issues if issue["issue_type"] == "disallowed_dictionary_value"),
        "unknown_values": sum(1 for issue in issues if issue["issue_type"] == "unknown_dictionary_value"),
        "missing_fields": sum(1 for issue in issues if issue["issue_type"] == "missing_field"),
        "issues": issues,
        "changes": changes,
    }
    return processed, report


def validate_dataset(input_path: str | Path, dictionary_path: str | Path, output_dir: str | Path) -> dict[str, Path]:
    """Validate a dataset file and write standard output artifacts."""
    input_file = Path(input_path)
    dataframe = load_dataset(input_file)
    dictionary = load_dictionary_csv(dictionary_path)
    processed, report = process_dataframe(dataframe, dictionary)

    output_directory = Path(output_dir)
    suffix = input_file.suffix.lower()
    standardized_path = output_directory / f"standardized_data{suffix}"
    report_path = output_directory / "dictionary_validation_report.json"
    issues_path = output_directory / "dictionary_issues.csv"
    changes_path = output_directory / "dictionary_changes.csv"

    save_dataset(processed, standardized_path)
    save_json_dict(_report_without_records(report), report_path)
    save_csv(pd.DataFrame(report["issues"], columns=ISSUE_COLUMNS), issues_path)
    save_csv(pd.DataFrame(report["changes"], columns=CHANGE_COLUMNS), changes_path)

    return {
        "standardized_data": standardized_path,
        "dictionary_validation_report": report_path,
        "dictionary_issues": issues_path,
        "dictionary_changes": changes_path,
    }


def normalize_dictionary_rules(dictionary_rules: Any) -> list[dict[str, Any]]:
    """Normalize supported dictionary rule inputs to dictionaries."""
    if isinstance(dictionary_rules, pd.DataFrame):
        records = dictionary_rules.to_dict(orient="records")
        columns = list(dictionary_rules.columns)
    elif isinstance(dictionary_rules, dict) and isinstance(dictionary_rules.get("dictionary"), list):
        records = dictionary_rules["dictionary"]
        columns = list(records[0].keys()) if records else []
    elif isinstance(dictionary_rules, list):
        records = dictionary_rules
        columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []
    else:
        raise TypeError("dictionary_rules 必须是 DataFrame、规则列表或包含 dictionary 的字典")

    if not records:
        raise ValueError("字典规则不能为空")

    missing_columns = [column for column in REQUIRED_DICTIONARY_COLUMNS if column not in columns]
    if missing_columns:
        raise ValueError(f"字典文件缺少必需列: {', '.join(missing_columns)}")

    normalized = []
    seen_keys: set[tuple[str, str]] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"字典第 {index} 行必须是字典")
        field_name = str(record.get("field_name", "")).strip()
        raw_value = str(record.get("raw_value", ""))
        if not field_name:
            raise ValueError(f"字典第 {index} 行 field_name 不能为空")
        rule_key = (field_name, raw_value)
        if rule_key in seen_keys:
            raise ValueError(f"字典存在重复配置: {field_name}={raw_value}")
        seen_keys.add(rule_key)
        normalized.append(
            {
                "field_name": field_name,
                "raw_value": raw_value,
                "standard_value": str(record.get("standard_value", "")),
                "allowed": _to_bool(record.get("allowed", True)),
                "remark": str(record.get("remark", "")),
            }
        )
    return normalized


def _group_rules_by_field(rules: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for rule in rules:
        grouped.setdefault(rule["field_name"], {})[rule["raw_value"]] = rule
    return grouped


def _issue(
    row: Any,
    field_name: str,
    value: Any,
    issue_type: str,
    reason: str,
    action: str,
    remark: str,
) -> dict[str, Any]:
    return {
        "row": row,
        "field_name": field_name,
        "value": "" if pd.isna(value) else value,
        "issue_type": issue_type,
        "reason": reason,
        "action": action,
        "remark": remark,
    }


def _report_without_records(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key not in {"issues", "changes"}}


def _value_key(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "1", "yes", "y", "allowed", "是", "允许"}


def main(argv: list[str]) -> int:
    """Run dictionary value validation from the command line."""
    if len(argv) != 4:
        print(
            json.dumps(
                {"error": "用法: python scripts/validate_dictionary_values.py input.csv dictionary.csv output_dir"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    try:
        outputs = validate_dataset(argv[1], argv[2], argv[3])
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({key: str(value) for key, value in outputs.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
