"""Detect abnormal and invalid values in CSV/JSON datasets.

The current version supports range rules, allowed-value rules, regex rules,
strict rule validation, summary statistics, and abnormal_records.json output.
It only detects issues and does not repair data.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SHARED_DIR = Path(__file__).resolve().parents[2] / "qa" / "shared"
if SHARED_DIR.exists() and str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from abnormal_file_utils import load_data, save_json
from simple_yaml import load_yaml_text


DEFAULT_ABNORMAL_NAME = "abnormal_records.json"
DEFAULT_VALIDATION_NAME = "rule_validation_report.json"


def load_rules(rules_path: str | Path) -> dict[str, Any]:
    """Load a YAML rules file."""
    path = Path(rules_path)
    if not path.is_file():
        raise FileNotFoundError(f"规则文件不存在: {path}")

    content = path.read_text(encoding="utf-8")
    rules = _load_yaml_content(content, path)
    if not isinstance(rules, dict):
        raise ValueError("规则文件根节点必须是字典")
    return rules


def detect_dataset(input_path: str | Path, rules_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Load data and rules, detect abnormal values, then write the report."""
    dataframe = load_data(input_path)
    rules = load_rules(rules_path)
    validation_report = validate_rules(dataframe, rules)
    validation_path = _resolve_validation_output_path(rules, output_dir)
    save_json(validation_report, validation_path)
    if validation_report["strict"] and not validation_report["valid"]:
        raise ValueError("; ".join(validation_report["errors"]))

    report = detect_dataframe(dataframe, rules)
    output_path = _resolve_output_path(rules, output_dir)
    save_json(report, output_path)
    return report


def validate_rules(dataframe: pd.DataFrame, rules: dict[str, Any]) -> dict[str, Any]:
    """Validate rule configuration against the input DataFrame."""
    strict = bool(rules.get("strict", False))
    issues: list[dict[str, Any]] = []

    _validate_range_rules(dataframe, rules.get("range_rules", {}), issues)
    _validate_enum_rules(dataframe, rules.get("enum_rules", {}), issues)
    _validate_regex_rules(dataframe, rules.get("regex_rules", {}), issues)

    errors = [_format_issue(issue) for issue in issues]
    return {
        "valid": not errors,
        "strict": strict,
        "errors": errors if strict else [],
        "warnings": [] if strict else errors,
    }


def detect_dataframe(dataframe: pd.DataFrame, rules: dict[str, Any]) -> dict[str, Any]:
    """Detect abnormal values in a DataFrame and return a fixed report structure."""
    abnormal_records: list[dict[str, Any]] = []

    _detect_range_rules(dataframe, rules.get("range_rules", {}), abnormal_records)
    _detect_enum_rules(dataframe, rules.get("enum_rules", {}), abnormal_records)
    _detect_regex_rules(dataframe, rules.get("regex_rules", {}), abnormal_records)

    return {
        "total_rows": int(len(dataframe)),
        "abnormal_count": int(len(abnormal_records)),
        "abnormal_summary": _summarize_by_key(abnormal_records, "reason"),
        "field_summary": _summarize_by_key(abnormal_records, "field"),
        "abnormal_records": abnormal_records,
    }


def process_dataframe(dataframe: pd.DataFrame, rules: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Detect abnormal values and return the unchanged DataFrame plus report.

    This stable interface is provided for orchestration skills. The detector is
    an atomic read-only capability, so it never repairs or mutates data.
    """
    return dataframe.copy(), detect_dataframe(dataframe, rules)


def _validate_range_rules(dataframe: pd.DataFrame, range_rules: Any, issues: list[dict[str, Any]]) -> None:
    """Validate range rules."""
    if range_rules in (None, ""):
        return
    if not isinstance(range_rules, dict):
        _add_issue(issues, "range_rules", None, "invalid_rule_format", "range_rules 必须是字典")
        return

    for field, rule in range_rules.items():
        if not _has_rule(rule):
            continue
        if not isinstance(field, str) or not field:
            _add_issue(issues, "range_rules", str(field), "invalid_rule_format", "字段名不能为空")
            continue
        if field not in dataframe.columns:
            _add_issue(issues, "range_rules", field, "missing_field", f"字段不存在: {field}")
            continue
        minimum = rule.get("min")
        maximum = rule.get("max")
        parsed_min = _to_rule_number(minimum)
        parsed_max = _to_rule_number(maximum)
        if minimum is None and maximum is None:
            _add_issue(issues, "range_rules", field, "invalid_rule_format", "min 和 max 至少配置一个")
            continue
        if minimum is not None and parsed_min is None:
            _add_issue(issues, "range_rules", field, "invalid_min", "min 必须是数字")
            continue
        if maximum is not None and parsed_max is None:
            _add_issue(issues, "range_rules", field, "invalid_max", "max 必须是数字")
            continue
        if parsed_min is not None and parsed_max is not None and parsed_min > parsed_max:
            _add_issue(issues, "range_rules", field, "invalid_min_max", "min 不能大于 max")


def _validate_enum_rules(dataframe: pd.DataFrame, enum_rules: Any, issues: list[dict[str, Any]]) -> None:
    """Validate allowed-value rules."""
    if enum_rules in (None, ""):
        return
    if not isinstance(enum_rules, dict):
        _add_issue(issues, "enum_rules", None, "invalid_rule_format", "enum_rules 必须是字典")
        return

    for field, rule in enum_rules.items():
        if not _has_rule(rule):
            continue
        if not isinstance(field, str) or not field:
            _add_issue(issues, "enum_rules", str(field), "invalid_rule_format", "字段名不能为空")
            continue
        if field not in dataframe.columns:
            _add_issue(issues, "enum_rules", field, "missing_field", f"字段不存在: {field}")
            continue
        allowed = rule.get("allowed")
        if not isinstance(allowed, list) or not allowed:
            _add_issue(issues, "enum_rules", field, "invalid_allowed", "allowed 必须是非空列表")


def _validate_regex_rules(dataframe: pd.DataFrame, regex_rules: Any, issues: list[dict[str, Any]]) -> None:
    """Validate regex rules."""
    if regex_rules in (None, ""):
        return
    if not isinstance(regex_rules, dict):
        _add_issue(issues, "regex_rules", None, "invalid_rule_format", "regex_rules 必须是字典")
        return

    for field, rule in regex_rules.items():
        if not _has_rule(rule):
            continue
        if not isinstance(field, str) or not field:
            _add_issue(issues, "regex_rules", str(field), "invalid_rule_format", "字段名不能为空")
            continue
        if field not in dataframe.columns:
            _add_issue(issues, "regex_rules", field, "missing_field", f"字段不存在: {field}")
            continue
        pattern = rule.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            _add_issue(issues, "regex_rules", field, "invalid_pattern", "pattern 必须是非空字符串")
            continue
        try:
            re.compile(pattern)
        except re.error:
            _add_issue(issues, "regex_rules", field, "invalid_pattern", "pattern 不是合法正则表达式")


def _detect_range_rules(
    dataframe: pd.DataFrame,
    range_rules: Any,
    abnormal_records: list[dict[str, Any]],
) -> None:
    """Detect values outside configured numeric ranges."""
    if not isinstance(range_rules, dict):
        return

    for field, rule in range_rules.items():
        if not _has_rule(rule) or field not in dataframe.columns:
            continue
        minimum = rule.get("min")
        maximum = rule.get("max")
        parsed_min = _to_rule_number(minimum)
        parsed_max = _to_rule_number(maximum)
        if minimum is None and maximum is None:
            continue
        if (minimum is not None and parsed_min is None) or (maximum is not None and parsed_max is None):
            continue
        if parsed_min is not None and parsed_max is not None and parsed_min > parsed_max:
            continue

        for index, value in dataframe[field].items():
            numeric_value = _to_number(value)
            if numeric_value is None:
                _append_record(abnormal_records, index, field, value, "out_of_range")
                continue
            if parsed_min is not None and numeric_value < parsed_min:
                _append_record(abnormal_records, index, field, value, "out_of_range")
                continue
            if parsed_max is not None and numeric_value > parsed_max:
                _append_record(abnormal_records, index, field, value, "out_of_range")


def _detect_enum_rules(
    dataframe: pd.DataFrame,
    enum_rules: Any,
    abnormal_records: list[dict[str, Any]],
) -> None:
    """Detect values that are not in configured allowed lists."""
    if not isinstance(enum_rules, dict):
        return

    for field, rule in enum_rules.items():
        if not _has_rule(rule) or field not in dataframe.columns:
            continue
        allowed = rule.get("allowed")
        if not isinstance(allowed, list) or not allowed:
            continue
        allowed_values = {str(item) for item in allowed}

        for index, value in dataframe[field].items():
            if str(value) not in allowed_values:
                _append_record(abnormal_records, index, field, value, "not_allowed")


def _detect_regex_rules(
    dataframe: pd.DataFrame,
    regex_rules: Any,
    abnormal_records: list[dict[str, Any]],
) -> None:
    """Detect values that do not match configured regex patterns."""
    if not isinstance(regex_rules, dict):
        return

    for field, rule in regex_rules.items():
        if not _has_rule(rule) or field not in dataframe.columns:
            continue
        pattern = rule.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            continue
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue

        for index, value in dataframe[field].items():
            if not compiled.fullmatch(str(value)):
                _append_record(abnormal_records, index, field, value, "regex_not_match")


def _append_record(
    abnormal_records: list[dict[str, Any]],
    index: Any,
    field: str,
    value: Any,
    reason: str,
) -> None:
    """Append one abnormal record using the fixed output field names."""
    abnormal_records.append(
        {
            "row": int(index) + 1,
            "field": field,
            "value": _to_json_value(value),
            "issue_type": reason,
            "reason": reason,
            "source_skill": "abnormal-value-detector",
            "action": "detect",
        }
    )


def _has_rule(rule: Any) -> bool:
    """Return whether a rule is a non-empty dictionary."""
    return isinstance(rule, dict) and bool(rule)


def _add_issue(
    issues: list[dict[str, Any]],
    rule_type: str,
    field: str | None,
    reason: str,
    message: str,
) -> None:
    """Append one rule validation issue."""
    issues.append(
        {
            "rule_type": rule_type,
            "field": field,
            "reason": reason,
            "message": message,
        }
    )


def _format_issue(issue: dict[str, Any]) -> str:
    """Format a validation issue for user-facing reports."""
    field = issue["field"] if issue["field"] is not None else "-"
    return f"{issue['rule_type']}.{field}: {issue['reason']} - {issue['message']}"


def _summarize_by_key(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Count abnormal records by a given key."""
    summary: dict[str, int] = {}
    for record in records:
        value = str(record[key])
        summary[value] = summary.get(value, 0) + 1
    return summary


def _to_rule_number(value: Any) -> float | None:
    """Convert rule min/max to float when possible."""
    if value is None or pd.isna(value):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _to_number(value: Any) -> float | None:
    """Convert a value to float when possible."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_json_value(value: Any) -> Any:
    """Convert pandas/numpy values to JSON-safe native values."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass
    return value


def _resolve_output_path(rules: dict[str, Any], output_dir: str | Path | None = None) -> Path:
    """Resolve abnormal_records.json output path."""
    output_config = rules.get("output", {}) if isinstance(rules.get("output", {}), dict) else {}
    report_name = output_config.get("abnormal_records_name", DEFAULT_ABNORMAL_NAME)
    directory = output_dir or output_config.get("output_dir", "examples/expected_outputs")
    return Path(directory) / str(report_name)


def _resolve_validation_output_path(rules: dict[str, Any], output_dir: str | Path | None = None) -> Path:
    """Resolve rule_validation_report.json output path."""
    output_config = rules.get("output", {}) if isinstance(rules.get("output", {}), dict) else {}
    report_name = output_config.get("rule_validation_report_name", DEFAULT_VALIDATION_NAME)
    directory = output_dir or output_config.get("output_dir", "examples/expected_outputs")
    return Path(directory) / str(report_name)


def _load_yaml_content(content: str, path: Path) -> dict[str, Any]:
    """Load YAML content through the workspace shared YAML helper."""
    try:
        return load_yaml_text(content)
    except ValueError as exc:
        raise RuntimeError(f"规则文件解析失败: {path}") from exc


def main() -> int:
    """Command-line entry point."""
    if len(sys.argv) not in (3, 4):
        print("Usage: python3 detect_abnormal_values.py input.csv rules.yaml [output_dir]", file=sys.stderr)
        return 2

    input_path = sys.argv[1]
    rules_path = sys.argv[2]
    output_dir = sys.argv[3] if len(sys.argv) == 4 else None

    try:
        report = detect_dataset(input_path, rules_path, output_dir)
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
