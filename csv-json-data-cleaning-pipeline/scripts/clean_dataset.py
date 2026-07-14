#!/usr/bin/env python3
"""Orchestrate CSV/JSON/JSONL dataset cleaning.

This module implements data loading, required field existence checks,
deduplication, atomic Skill orchestration, issue export, summary output, and
cleaning logs.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import importlib.util
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline_file_utils import ensure_directory, load_csv, load_json, load_jsonl, save_csv
from validate_rules import load_yaml_file, validate_rules


SUPPORTED_SUFFIXES = {".csv", ".json", ".jsonl"}
OUTPUTS_DIR = Path(__file__).resolve().parents[2]
ATOMIC_SKILL_SCRIPTS = {
    "missing-value-checker": OUTPUTS_DIR / "missing-value-checker" / "scripts" / "check_missing_values.py",
    "format-standardizer": OUTPUTS_DIR / "format-standardizer" / "scripts" / "standardize_format.py",
    "abnormal-value-detector": OUTPUTS_DIR / "abnormal-value-detector" / "scripts" / "detect_abnormal_values.py",
}


def load_dataset(input_path: str | Path) -> pd.DataFrame:
    """Load a CSV, JSON, or JSONL file into a pandas DataFrame.

    Args:
        input_path: Input data file path.

    Returns:
        Loaded DataFrame.

    Raises:
        ValueError: If the file extension is unsupported.
        FileNotFoundError: If the file does not exist.
        RuntimeError: If file loading fails.
    """
    path = Path(input_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return load_csv(path)
    if suffix == ".json":
        return load_json(path)
    if suffix == ".jsonl":
        return load_jsonl(path)
    raise ValueError(f"不支持的输入文件类型: {suffix}; 支持类型: {sorted(SUPPORTED_SUFFIXES)}")


def load_rules(rules_path: str | Path) -> dict[str, Any]:
    """Load a YAML rules file as a dictionary.

    Args:
        rules_path: YAML rule file path.

    Returns:
        Parsed rule dictionary.

    Raises:
        ValueError: If the rules file cannot be read or is not a dictionary.
    """
    rules, errors = load_yaml_file(rules_path)
    if errors:
        raise ValueError("; ".join(errors))
    if not isinstance(rules, dict):
        raise ValueError("规则文件根节点必须是字典对象")
    validation_result = validate_rules(rules)
    if not validation_result["valid"]:
        raise ValueError("规则校验失败: " + "; ".join(validation_result["errors"]))
    return rules


def check_required_fields(dataframe: pd.DataFrame, rules: dict[str, Any]) -> list[str]:
    """Check whether required fields configured in rules exist in the DataFrame.

    This function only checks field existence. It does not check empty values.

    Args:
        dataframe: Input DataFrame.
        rules: Parsed cleaning rules.

    Returns:
        Sorted list of required fields missing from the DataFrame.
    """
    required_fields = _extract_required_field_names(rules.get("required_fields", []))
    dataframe_fields = set(dataframe.columns)
    return sorted(field for field in required_fields if field not in dataframe_fields)


def deduplicate_dataframe(dataframe: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    """Deduplicate a DataFrame according to unique key rules.

    Single-field and multi-field composite deduplication are both supported.
    The first matching record is always kept.

    Args:
        dataframe: Input DataFrame.
        rules: Parsed cleaning rules.

    Returns:
        Deduplicated DataFrame.
    """
    deduplicated = dataframe.copy()
    for key_group in _extract_unique_key_groups(rules.get("unique_keys", {})):
        if all(field in deduplicated.columns for field in key_group):
            deduplicated = deduplicated.drop_duplicates(subset=key_group, keep="first")
    return deduplicated


def process_dataframe(dataframe: pd.DataFrame, rules: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run the orchestration pipeline on an in-memory DataFrame.

    The pipeline owns loading, deduplication, output aggregation, and reporting.
    Missing-value repair, format standardization, and abnormal-value detection
    are delegated to the three atomic Skills through their stable
    process_dataframe(dataframe, rules) interfaces.
    """
    processed, result, _, _, _ = _process_dataframe_detailed(dataframe, rules, input_path=None)
    return processed, result


def process_dataset(input_path: str | Path, rules_path: str | Path) -> dict[str, Any]:
    """Run the cleaning pipeline and configured outputs.

    Args:
        input_path: CSV, JSON, or JSONL input file path.
        rules_path: YAML rules file path.

    Returns:
        A dictionary containing row counts, missing required fields, and
        repair/standardization counts.
    """
    dataframe = load_dataset(input_path)
    rules = load_rules(rules_path)
    processed, result, issue_rows, cleaning_log, dedup_report = _process_dataframe_detailed(dataframe, rules, input_path=input_path)
    if isinstance(rules.get("output"), dict) and rules["output"].get("output_dir"):
        write_outputs(processed, result, issue_rows, cleaning_log, dedup_report, rules)
    return result


def write_outputs(
    cleaned_data: pd.DataFrame,
    result: dict[str, Any],
    issue_rows: list[dict[str, Any]],
    cleaning_log: list[dict[str, Any]],
    dedup_report: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Path]:
    """Write cleaned data, issue rows, summary, and logs to the output directory.

    Args:
        cleaned_data: Final processed DataFrame.
        result: Processing summary dictionary.
        issue_rows: Issue records collected during processing.
        cleaning_log: Step-level cleaning log records.
        rules: Parsed rules containing the output directory and file names.

    Returns:
        Mapping of output artifact names to written paths.
    """
    output_config = rules.get("output", {})
    output_dir = ensure_directory(output_config.get("output_dir", "outputs/cleaning_result"))

    cleaned_data_path = output_dir / output_config.get("cleaned_data_name", "cleaned_data.csv")
    issue_rows_path = output_dir / output_config.get("issue_rows_name", "issue_rows.csv")
    summary_path = output_dir / output_config.get("cleaning_summary_name", "cleaning_summary.json")
    log_path = output_dir / output_config.get("cleaning_log_name", "cleaning_log.csv")
    dedup_path = output_dir / output_config.get("dedup_report_name", "dedup_report.json")

    save_csv(cleaned_data, cleaned_data_path)
    save_csv(_issue_rows_dataframe(issue_rows), issue_rows_path)
    save_csv(pd.DataFrame(cleaning_log, columns=["timestamp", "rule_name", "action", "affected_rows", "result"]), log_path)
    dedup_path.write_text(json.dumps(dedup_report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "input_rows": result["input_rows"],
        "output_rows": len(cleaned_data),
        "removed_rows": result["removed_rows"],
        "duplicate_rows": result["duplicate_rows"],
        "duplicate_exact_rows": result.get("duplicate_exact_rows", 0),
        "duplicate_similarity_rows": result.get("duplicate_similarity_rows", 0),
        "quarantined_rows": result["quarantined_rows"],
        "null_rows": result["processed_null_rows"],
        "null_dropped_rows": result.get("null_dropped_rows", 0),
        "null_repaired_rows": result.get("null_repaired_rows", 0),
        "abnormal_rows": result["abnormal_rows"],
        "repaired_rows": result["repaired_rows"],
        "issue_rows": len(issue_rows),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "cleaned_data": cleaned_data_path,
        "issue_rows": issue_rows_path,
        "cleaning_summary": summary_path,
        "cleaning_log": log_path,
        "dedup_report": dedup_path,
    }


def _process_dataframe_detailed(
    dataframe: pd.DataFrame,
    rules: dict[str, Any],
    input_path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Orchestrate atomic Skills and collect issue rows and cleaning logs."""
    input_rows = len(dataframe)
    issue_rows: list[dict[str, Any]] = []
    cleaning_log: list[dict[str, Any]] = []

    cleaning_log.append(_log_record("load_input", "check", input_rows, "success"))

    deduplicated, duplicate_issues, dedup_report = _deduplicate_with_issues(dataframe, rules)
    issue_rows.extend(duplicate_issues)
    duplicate_exact_rows = int(dedup_report.get("exact_duplicate_rows", 0))
    duplicate_similarity_rows = int(dedup_report.get("similarity_duplicate_rows", 0))
    duplicate_rows = duplicate_exact_rows + duplicate_similarity_rows
    cleaning_log.append(_log_record("unique_keys", "drop", duplicate_rows, "success"))

    missing_module = _load_atomic_module("missing-value-checker")
    missing_processed, missing_report = missing_module.process_dataframe(
        deduplicated,
        _build_missing_value_rules(rules),
    )
    issue_rows.extend(_missing_report_issues(missing_report))
    missing_cell_issues = _missing_cell_issues(deduplicated, missing_processed, rules)
    issue_rows.extend(missing_cell_issues)
    quarantine_indices = _unrepaired_missing_indices(missing_cell_issues)
    missing_fields = list(missing_report.get("missing_fields", []))
    processed_null_rows = int(missing_report.get("missing_cells", 0))
    null_repaired_cells = int(missing_report.get("repaired_cells", 0))
    null_dropped_rows = int(missing_report.get("dropped_rows", 0))
    cleaning_log.append(
        _log_record(
            "missing-value-checker",
            "repair",
            processed_null_rows,
            "warning" if missing_fields else "success",
        )
    )
    cleaning_log.append(_log_record("required_fields", "check", len(missing_fields), "warning" if missing_fields else "success"))
    cleaning_log.append(_log_record("null_handling", "process", processed_null_rows, "success"))

    format_module = _load_atomic_module("format-standardizer")
    standardized, format_report = format_module.process_dataframe(
        missing_processed,
        _build_format_rules(rules),
    )
    format_issues = _normalize_atomic_issues(
        format_report.get("abnormal_records", []),
        "format-standardizer",
        context_dataframe=missing_processed,
    )
    issue_rows.extend(format_issues)
    quarantine_indices.update(_unrepaired_format_indices(format_issues, rules))
    standardized_cells = int(format_report.get("standardized_cells", 0))
    format_failed_cells = int(format_report.get("failed_cells", 0))
    cleaning_log.append(_log_record("format-standardizer", "standardize", standardized_cells, "success"))

    abnormal_module = _load_atomic_module("abnormal-value-detector")
    _, abnormal_report = abnormal_module.process_dataframe(
        standardized,
        _build_abnormal_rules(rules),
    )
    abnormal_issues = _normalize_atomic_issues(
        abnormal_report.get("abnormal_records", []),
        "abnormal-value-detector",
        context_dataframe=standardized,
    )
    issue_rows.extend(abnormal_issues)
    quarantine_indices.update(_issue_indices(abnormal_issues))
    abnormal_count = int(abnormal_report.get("abnormal_count", 0))
    cleaning_log.append(_log_record("abnormal-value-detector", "detect", abnormal_count, "success"))

    cleaned = standardized.drop(index=[index for index in quarantine_indices if index in standardized.index]).copy()
    cleaned = _attach_lineage_fields(cleaned, rules, input_path=input_path)
    quarantined_rows = len(standardized) - len(cleaned)
    cleaning_log.append(_log_record("quarantine_unrepaired_rows", "drop", quarantined_rows, "success"))

    result = {
        "input_rows": input_rows,
        "after_deduplicate_rows": len(deduplicated),
        "duplicate_exact_rows": duplicate_exact_rows,
        "duplicate_similarity_rows": duplicate_similarity_rows,
        "duplicate_rows": duplicate_rows,
        "quarantined_rows": quarantined_rows,
        "removed_rows": duplicate_rows + quarantined_rows,
        "missing_fields": missing_fields,
        "repaired_rows": null_repaired_cells + standardized_cells,
        "processed_null_rows": processed_null_rows,
        "null_dropped_rows": null_dropped_rows,
        "null_repaired_rows": null_repaired_cells,
        "standardized_rows": standardized_cells,
        "abnormal_rows": format_failed_cells + abnormal_count,
        "atomic_reports": {
            "missing-value-checker": missing_report,
            "format-standardizer": format_report,
            "abnormal-value-detector": abnormal_report,
        },
    }
    cleaning_log.append(_log_record("export_outputs", "export", len(issue_rows), "success"))
    return cleaned, result, issue_rows, cleaning_log, dedup_report


def _load_atomic_module(skill_name: str) -> Any:
    """Load an atomic Skill script by path without requiring package imports."""
    script_path = ATOMIC_SKILL_SCRIPTS[skill_name]
    if not script_path.is_file():
        raise FileNotFoundError(f"原子 Skill 脚本不存在: {script_path}")

    module_name = skill_name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载原子 Skill: {skill_name}")

    module = importlib.util.module_from_spec(spec)
    previous_file_utils = sys.modules.pop("file_utils", None)
    sys.path.insert(0, str(script_path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
        if previous_file_utils is not None:
            sys.modules["file_utils"] = previous_file_utils
        else:
            sys.modules.pop("file_utils", None)

    if not hasattr(module, "process_dataframe"):
        raise AttributeError(f"{skill_name} 缺少 process_dataframe(dataframe, rules) 接口")
    return module


def _build_missing_value_rules(rules: dict[str, Any]) -> dict[str, Any]:
    """Translate pipeline rules into missing-value-checker rules."""
    null_config = rules.get("null_handling", {}) if isinstance(rules.get("null_handling", {}), dict) else {}
    strategies = null_config.get("strategies", []) if isinstance(null_config.get("strategies", []), list) else []
    field_rules: dict[str, dict[str, Any]] = {}

    for strategy in strategies:
        if not isinstance(strategy, dict) or not isinstance(strategy.get("field"), str):
            continue
        field = strategy["field"]
        action = str(strategy.get("action", "keep_null")).strip()
        if action in {"fill_custom", "fill"}:
            field_rules[field] = {
                "action": action,
                "value": strategy.get("fill_value", strategy.get("custom_value", strategy.get("value", ""))),
            }
        elif action == "fill_default":
            field_rules[field] = {"action": "fill_default", "value": strategy.get("default_value", strategy.get("value", "unknown"))}
        elif action in {"drop", "mean", "median", "mode", "ffill", "bfill", "keep_null"}:
            field_rules[field] = {"action": action}
        else:
            # mark / ignore / unsupported actions should preserve missing values.
            field_rules[field] = {"action": "keep_null"}

    return {
        "required_fields": _extract_required_field_names(rules.get("required_fields", [])),
        "null_values": null_config.get("null_values", ["", "null", "NULL", "N/A", "NA", "未知"]),
        "field_rules": field_rules,
    }


def _build_format_rules(rules: dict[str, Any]) -> dict[str, Any]:
    """Translate pipeline rules into format-standardizer rules."""
    return {
        "date_rules": _convert_format_section(rules.get("date_rules", {}), "date"),
        "phone_rules": _convert_format_section(rules.get("phone_rules", {}), "phone"),
        "amount_rules": _convert_format_section(rules.get("amount_rules", {}), "amount"),
        "id_card_rules": _convert_format_section(rules.get("id_card_rules", {}), "id_card"),
        "unit_rules": _convert_format_section(rules.get("unit_rules", {}), "unit"),
        "encoding_rules": rules.get("encoding_rules", {}),
    }


def _convert_format_section(section: Any, field_type: str) -> dict[str, Any]:
    """Convert one pipeline format rule section to atomic format rules."""
    if not isinstance(section, dict):
        return {"enable": False, "fields": []}
    enabled = section.get("enabled", section.get("enable", True))
    fields = []
    for item in section.get("fields", []):
        if isinstance(item, str):
            fields.append(item)
        elif isinstance(item, dict) and isinstance(item.get("field"), str):
            field_config: dict[str, Any] = {"field": item["field"]}
            for key in ("country_code", "decimal_places", "amount_precision", "allow_negative", "strict", "invalid_action"):
                if key in item:
                    field_config[key] = item[key]
            fields.append(field_config)
    converted: dict[str, Any] = {
        "enable": bool(enabled),
        "strict": True,
        "fields": fields,
    }
    if field_type == "phone":
        converted["country_code"] = str(section.get("country_code", "86"))
    if field_type == "amount":
        converted["decimal_places"] = int(section.get("amount_precision", section.get("decimal_places", 2)))
        converted["allow_negative"] = bool(section.get("allow_negative", True))
        converted["invalid_action"] = section.get("invalid_action", "mark")
    if field_type == "unit":
        converted["unit_type"] = str(section.get("unit_type", "weight"))
        converted["target_unit"] = str(section.get("target_unit", "g"))
        converted["decimal_places"] = int(section.get("decimal_places", 4))
        converted["keep_unit_suffix"] = bool(section.get("keep_unit_suffix", True))
    return converted


def _build_abnormal_rules(rules: dict[str, Any]) -> dict[str, Any]:
    """Translate pipeline enum/range/regex rules into abnormal-value-detector rules."""
    return {
        "strict": False,
        "range_rules": _build_range_rules(rules),
        "enum_rules": _build_enum_rules(rules),
        "regex_rules": _build_regex_rules(rules),
    }


def _build_range_rules(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract range rules from pipeline anomaly/custom rules."""
    range_rules: dict[str, dict[str, Any]] = {}
    for item in _iter_anomaly_rule_items(rules):
        if not isinstance(item, dict) or item.get("rule_type") != "range":
            continue
        field = item.get("field")
        if isinstance(field, str) and field:
            rule: dict[str, Any] = {}
            if "min" in item:
                rule["min"] = item["min"]
            if "max" in item:
                rule["max"] = item["max"]
            range_rules[field] = rule
    return range_rules


def _build_enum_rules(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract enum rules from pipeline enum_rules."""
    enum_rules: dict[str, dict[str, Any]] = {}
    config = rules.get("enum_rules", {})
    fields = config.get("fields", []) if isinstance(config, dict) else []
    if not isinstance(fields, list):
        return enum_rules
    for item in fields:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        allowed = item.get("allowed_values", item.get("allowed"))
        if isinstance(field, str) and isinstance(allowed, list):
            enum_rules[field] = {"allowed": allowed}
    return enum_rules


def _build_regex_rules(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract regex and length rules from pipeline anomaly/custom rules."""
    regex_rules: dict[str, dict[str, Any]] = {}
    for item in _iter_anomaly_rule_items(rules):
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        if not isinstance(field, str) or not field:
            continue
        rule_type = item.get("rule_type")
        if rule_type == "regex":
            pattern = item.get("pattern")
            if isinstance(pattern, str):
                regex_rules[field] = {"pattern": pattern}
        elif rule_type in {"min_length", "max_length", "length"}:
            pattern = _length_rule_pattern(item)
            if pattern:
                regex_rules[field] = {"pattern": pattern}
    return regex_rules


def _iter_anomaly_rule_items(rules: dict[str, Any]) -> list[dict[str, Any]]:
    """Return enabled anomaly rule items from the current and legacy sections."""
    items: list[dict[str, Any]] = []
    for section_name in ("anomaly_rules", "custom_rules"):
        section = rules.get(section_name, {})
        if not isinstance(section, dict) or section.get("enabled", True) is False:
            continue
        raw_rules = section.get("rules", [])
        if isinstance(raw_rules, list):
            items.extend(item for item in raw_rules if isinstance(item, dict))
    return items


def _length_rule_pattern(rule: dict[str, Any]) -> str:
    """Convert simple length rules to regex patterns for the atomic detector."""
    rule_type = rule.get("rule_type")
    if rule_type == "min_length":
        min_length = rule.get("value", rule.get("min"))
        if isinstance(min_length, int) and min_length >= 0:
            return f"(?s)^.{{{min_length},}}$"
    if rule_type == "max_length":
        max_length = rule.get("value", rule.get("max"))
        if isinstance(max_length, int) and max_length >= 0:
            return f"(?s)^.{{0,{max_length}}}$"
    if rule_type == "length":
        min_length = rule.get("min", 0)
        max_length = rule.get("max")
        if isinstance(min_length, int) and isinstance(max_length, int) and 0 <= min_length <= max_length:
            return f"(?s)^.{{{min_length},{max_length}}}$"
    return ""


def _missing_report_issues(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert missing-value-checker report-level findings to issue rows."""
    issues = []
    for field in report.get("missing_fields", []):
        issues.append(
            _issue_record(
                row="",
                field=field,
                value="",
                issue_type="missing_field",
                reason=f"必填字段不存在: {field}",
                source_skill="missing-value-checker",
                action="check",
            )
        )
    return issues


def _missing_cell_issues(
    original_dataframe: pd.DataFrame,
    repaired_dataframe: pd.DataFrame,
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    """Create issue rows for missing cells detected before missing-value repair."""
    null_values = _configured_null_values(rules)
    tracked_fields = _missing_tracked_fields(rules)
    strategy_actions = _null_strategy_action_map(rules)
    issues: list[dict[str, Any]] = []

    for field in tracked_fields:
        if field not in original_dataframe.columns:
            continue
        for index, value in original_dataframe[field].items():
            if not _is_null_like(value, null_values):
                continue
            configured_action = strategy_actions.get(field, "mark")
            dropped = index not in repaired_dataframe.index
            repaired_value = repaired_dataframe.at[index, field] if field in repaired_dataframe.columns and index in repaired_dataframe.index else value
            repaired = (not dropped) and (not _is_null_like(repaired_value, null_values))
            if dropped:
                reason = "缺失值行已按规则删除"
                action = "drop"
                process_result = "dropped"
            elif repaired:
                reason = "缺失值已按规则填充"
                action = "fill"
                process_result = "repaired"
            else:
                reason = "缺失值保留并标记"
                action = configured_action if configured_action in {"mark", "ffill", "bfill", "mean", "median", "mode"} else "mark"
                process_result = "marked"
            issues.append(
                _issue_record(
                    row=int(index) + 1,
                    field=field,
                    value=value,
                    issue_type="missing_value",
                    reason=reason,
                    source_skill="missing-value-checker",
                    action=action,
                    record_id=_record_id(original_dataframe.loc[index]),
                    process_result=process_result,
                    raw_record=original_dataframe.loc[index].to_dict(),
                )
            )
    return issues


def _configured_null_values(rules: dict[str, Any]) -> set[str]:
    """Return null-like values configured for the pipeline."""
    null_config = rules.get("null_handling", {}) if isinstance(rules.get("null_handling", {}), dict) else {}
    values = null_config.get("null_values", ["", "null", "NULL", "N/A", "NA", "未知"])
    if not isinstance(values, list):
        values = ["", "null", "NULL", "N/A", "NA", "未知"]
    return {str(value).strip() for value in values}


def _missing_tracked_fields(rules: dict[str, Any]) -> list[str]:
    """Return fields whose missing cells should be exported to issue rows."""
    fields = _extract_required_field_names(rules.get("required_fields", []))
    null_config = rules.get("null_handling", {}) if isinstance(rules.get("null_handling", {}), dict) else {}
    strategies = null_config.get("strategies", [])
    if isinstance(strategies, list):
        for strategy in strategies:
            if isinstance(strategy, dict) and isinstance(strategy.get("field"), str) and strategy["field"].strip():
                fields.append(strategy["field"].strip())
    return list(dict.fromkeys(fields))


def _null_strategy_action_map(rules: dict[str, Any]) -> dict[str, str]:
    """Map each null-handling field to its configured action."""
    null_config = rules.get("null_handling", {}) if isinstance(rules.get("null_handling", {}), dict) else {}
    strategies = null_config.get("strategies", [])
    mapping: dict[str, str] = {}
    if not isinstance(strategies, list):
        return mapping
    for strategy in strategies:
        if not isinstance(strategy, dict) or not isinstance(strategy.get("field"), str):
            continue
        mapping[strategy["field"].strip()] = str(strategy.get("action", "mark")).strip()
    return mapping


def _is_null_like(value: Any, null_values: set[str]) -> bool:
    """Return whether a value should be treated as missing."""
    if pd.isna(value):
        return True
    return str(value).strip() in null_values


def _normalize_atomic_issues(
    records: list[dict[str, Any]],
    default_source_skill: str,
    context_dataframe: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Normalize atomic Skill issue records to the shared issue schema."""
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            continue
        reason = str(record.get("reason", record.get("issue_type", "unknown_issue")))
        row_value = record.get("row", record.get("row_index", ""))
        row_index = _row_to_dataframe_index(row_value)
        raw_record = None
        record_id = ""
        if context_dataframe is not None and row_index is not None and row_index in context_dataframe.index:
            row_series = context_dataframe.loc[row_index]
            if isinstance(row_series, pd.Series):
                raw_record = row_series.to_dict()
                record_id = _record_id(row_series)
        normalized.append(
            _issue_record(
                row=row_value,
                field=record.get("field", ""),
                value=record.get("value", record.get("original_value", "")),
                issue_type=record.get("issue_type", reason),
                reason=reason,
                source_skill=record.get("source_skill", default_source_skill),
                action=record.get("action", "detect"),
                record_id=record_id,
                raw_record=raw_record,
            )
        )
    return normalized


def _unrepaired_missing_indices(issue_rows: list[dict[str, Any]]) -> set[Any]:
    """Return row indices for missing values that were marked but not repaired."""
    unrepaired: set[Any] = set()
    for issue in issue_rows:
        if issue.get("issue_type") != "missing_value":
            continue
        if issue.get("process_result") != "marked":
            continue
        index = _row_to_dataframe_index(issue.get("row"))
        if index is not None:
            unrepaired.add(index)
    return unrepaired


def _unrepaired_format_indices(issue_rows: list[dict[str, Any]], rules: dict[str, Any]) -> set[Any]:
    """Return row indices for failed standardization that was not auto-cleared."""
    set_null_fields = _format_fields_with_set_null_action(rules)
    unrepaired: set[Any] = set()
    for issue in issue_rows:
        if issue.get("issue_type") != "standardization_failed":
            continue
        if str(issue.get("field", "")) in set_null_fields:
            continue
        index = _row_to_dataframe_index(issue.get("row"))
        if index is not None:
            unrepaired.add(index)
    return unrepaired


def _format_fields_with_set_null_action(rules: dict[str, Any]) -> set[str]:
    """Return format-rule fields whose invalid values are explicitly cleared."""
    fields: set[str] = set()
    for section_name in ("date_rules", "phone_rules", "amount_rules"):
        section = rules.get(section_name, {})
        if not isinstance(section, dict):
            continue
        section_action = str(section.get("invalid_action", "mark")).lower()
        for item in section.get("fields", []):
            if isinstance(item, str):
                field = item
                action = section_action
            elif isinstance(item, dict) and isinstance(item.get("field"), str):
                field = item["field"]
                action = str(item.get("invalid_action", section_action)).lower()
            else:
                continue
            if action in {"set_null", "null", "clear", "blank", "empty"}:
                fields.add(field)
    return fields


def _issue_indices(issue_rows: list[dict[str, Any]]) -> set[Any]:
    """Return DataFrame indices referenced by normalized issue rows."""
    indices: set[Any] = set()
    for issue in issue_rows:
        index = _row_to_dataframe_index(issue.get("row"))
        if index is not None:
            indices.add(index)
    return indices


def _row_to_dataframe_index(row: Any) -> int | None:
    """Convert the one-based row marker used by atomic reports to a DataFrame index."""
    if row in ("", None):
        return None
    try:
        return int(row) - 1
    except (TypeError, ValueError):
        return None


def _extract_required_field_names(required_fields: Any) -> list[str]:
    """Extract required field names from the rules configuration."""
    if not isinstance(required_fields, list):
        return []

    field_names: list[str] = []
    for item in required_fields:
        if isinstance(item, dict) and isinstance(item.get("field"), str) and item["field"].strip():
            field_names.append(item["field"].strip())
        elif isinstance(item, str) and item.strip():
            field_names.append(item.strip())
    return field_names


def _extract_unique_key_groups(unique_keys: Any) -> list[list[str]]:
    """Extract unique key groups from the rules configuration."""
    raw_keys = unique_keys.get("keys") if isinstance(unique_keys, dict) else unique_keys
    if not isinstance(raw_keys, list):
        return []

    key_groups: list[list[str]] = []
    for item in raw_keys:
        if isinstance(item, str) and item.strip():
            key_groups.append([item.strip()])
        elif isinstance(item, list):
            fields = [field.strip() for field in item if isinstance(field, str) and field.strip()]
            if fields:
                key_groups.append(fields)
    return key_groups


def _deduplicate_with_issues(
    dataframe: pd.DataFrame,
    rules: dict[str, Any],
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Deduplicate records and collect duplicate issue rows."""
    deduplicated = dataframe.copy()
    issues: list[dict[str, Any]] = []
    exact_duplicate_rows = 0
    similarity_duplicate_rows = 0
    similarity_matches: list[dict[str, Any]] = []

    for key_group in _extract_unique_key_groups(rules.get("unique_keys", {})):
        if not all(field in deduplicated.columns for field in key_group):
            continue
        duplicate_mask = deduplicated.duplicated(subset=key_group, keep="first")
        for index, row in deduplicated.loc[duplicate_mask].iterrows():
            issues.append(
                _issue_record(
                    row_id=index,
                    record_id=_record_id(row),
                    issue_type="duplicate",
                    field_name="+".join(key_group),
                    original_value=_joined_values(row, key_group),
                    issue_reason=f"按字段 {', '.join(key_group)} 判断为重复记录",
                    suggested_action="drop",
                    raw_record=row.to_dict(),
                    process_result="dropped",
                )
            )
        exact_duplicate_rows += int(duplicate_mask.sum())
        deduplicated = deduplicated.loc[~duplicate_mask].copy()

    deduplicated, similarity_issues, similarity_matches = _deduplicate_by_similarity(deduplicated, rules)
    issues.extend(similarity_issues)
    similarity_duplicate_rows = len(similarity_issues)

    dedup_report = {
        "input_rows": int(len(dataframe)),
        "output_rows": int(len(deduplicated)),
        "exact_duplicate_rows": int(exact_duplicate_rows),
        "similarity_duplicate_rows": int(similarity_duplicate_rows),
        "total_duplicate_rows": int(exact_duplicate_rows + similarity_duplicate_rows),
        "similarity_matches": similarity_matches,
    }
    return deduplicated, issues, dedup_report


def _deduplicate_by_similarity(
    dataframe: pd.DataFrame,
    rules: dict[str, Any],
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove near-duplicate rows based on similarity threshold."""
    unique_keys = rules.get("unique_keys", {}) if isinstance(rules.get("unique_keys"), dict) else {}
    similarity_cfg = unique_keys.get("similarity", {}) if isinstance(unique_keys, dict) else {}
    if not isinstance(similarity_cfg, dict) or not similarity_cfg.get("enabled", False):
        return dataframe, [], []

    raw_fields = similarity_cfg.get("fields", similarity_cfg.get("field", []))
    if isinstance(raw_fields, str):
        fields = [raw_fields]
    elif isinstance(raw_fields, list):
        fields = [field for field in raw_fields if isinstance(field, str) and field.strip()]
    else:
        fields = []
    fields = [field.strip() for field in fields if field.strip() and field in dataframe.columns]
    if not fields:
        return dataframe, [], []

    threshold = float(similarity_cfg.get("threshold", 0.92))
    threshold = max(0.0, min(1.0, threshold))
    issues: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    keep_indices: list[Any] = []
    keep_texts: list[tuple[Any, str, Any]] = []

    for index, row in dataframe.iterrows():
        current_text = _similarity_text(row, fields)
        current_record_id = _record_id(row)
        matched = False
        for kept_index, kept_text, kept_record_id in keep_texts:
            score = SequenceMatcher(None, current_text, kept_text).ratio()
            if score < threshold:
                continue
            matched = True
            matches.append(
                {
                    "kept_row": int(kept_index) + 1,
                    "dropped_row": int(index) + 1,
                    "kept_record_id": kept_record_id,
                    "dropped_record_id": current_record_id,
                    "score": round(float(score), 4),
                    "fields": fields,
                }
            )
            issues.append(
                _issue_record(
                    row=int(index) + 1,
                    field="+".join(fields),
                    value=current_text,
                    issue_type="similar_duplicate",
                    reason=f"相似度去重命中(阈值={threshold}, score={round(float(score), 4)})",
                    source_skill="csv-json-data-cleaning-pipeline",
                    action="drop",
                    record_id=current_record_id,
                    process_result="dropped",
                    raw_record=row.to_dict(),
                )
            )
            break
        if not matched:
            keep_indices.append(index)
            keep_texts.append((index, current_text, current_record_id))

    return dataframe.loc[keep_indices].copy(), issues, matches


def _similarity_text(row: pd.Series, fields: list[str]) -> str:
    """Join selected fields into a normalized text for similarity comparison."""
    values = []
    for field in fields:
        value = row.get(field, "")
        if pd.isna(value):
            values.append("")
        else:
            values.append(str(value).strip().lower())
    return " | ".join(values)


def _issue_record(
    row: Any | None = None,
    field: str | None = None,
    value: Any | None = None,
    issue_type: str = "unknown_issue",
    reason: str | None = None,
    source_skill: str = "csv-json-data-cleaning-pipeline",
    action: str = "review",
    row_id: Any | None = None,
    record_id: Any | None = None,
    field_name: str | None = None,
    original_value: Any | None = None,
    issue_reason: str | None = None,
    suggested_action: str | None = None,
    raw_record: dict[str, Any] | None = None,
    process_result: str | None = None,
) -> dict[str, Any]:
    """Create a shared issue row record.

    The canonical schema is row, field, value, issue_type, reason,
    source_skill, and action. Older keyword names are accepted so legacy helper
    functions can still feed duplicate records into the orchestration layer.
    """
    final_row = row if row is not None else row_id
    final_field = field if field is not None else field_name
    final_value = value if value is not None else original_value
    final_reason = reason if reason is not None else issue_reason
    final_action = action if suggested_action is None else suggested_action
    return {
        "row": "" if final_row is None else final_row,
        "field": "" if final_field is None else final_field,
        "value": "" if pd.isna(final_value) else final_value,
        "issue_type": issue_type,
        "reason": "" if final_reason is None else final_reason,
        "source_skill": source_skill,
        "action": final_action,
        "record_id": "" if record_id is None else record_id,
        "process_result": "" if process_result is None else process_result,
        "raw_record": json.dumps(_json_safe_record(raw_record), ensure_ascii=False, default=str),
    }


def _json_safe_record(raw_record: dict[str, Any] | None) -> dict[str, Any]:
    """Convert pandas missing values in raw records to JSON null."""
    if raw_record is None:
        return {}
    safe_record: dict[str, Any] = {}
    for key, value in raw_record.items():
        safe_record[key] = None if pd.isna(value) else value
    return safe_record


def _issue_rows_dataframe(issue_rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Return issue rows as a DataFrame with stable output columns."""
    columns = [
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
    return pd.DataFrame(issue_rows, columns=columns)


def _log_record(rule_name: str, action: str, affected_rows: int, result: str) -> dict[str, Any]:
    """Create a standard cleaning log record."""
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rule_name": rule_name,
        "action": action,
        "affected_rows": affected_rows,
        "result": result,
    }


def _record_id(row: pd.Series) -> Any:
    """Return the business record id when the row has an id field."""
    return row.get("id", "")


def _joined_values(row: pd.Series, fields: list[str]) -> str:
    """Join values from a row for display in issue rows."""
    return "|".join(str(row.get(field, "")) for field in fields)


def _attach_lineage_fields(dataframe: pd.DataFrame, rules: dict[str, Any], input_path: str | Path | None) -> pd.DataFrame:
    """Attach stable lineage fields to cleaned data."""
    if dataframe.empty:
        dataframe = dataframe.copy()
    lineage_config = rules.get("lineage", {}) if isinstance(rules.get("lineage"), dict) else {}
    source_file = str(input_path) if input_path else str(lineage_config.get("source_file", "in_memory"))
    batch_id = str(lineage_config.get("batch_id", datetime.now().strftime("%Y%m%d%H%M%S")))
    rule_version = str(lineage_config.get("rule_version", "v1"))

    with_lineage = dataframe.copy()
    with_lineage["_source_file"] = source_file
    with_lineage["_source_row"] = [int(index) + 1 for index in with_lineage.index]
    with_lineage["_batch_id"] = batch_id
    with_lineage["_rule_version"] = rule_version
    with_lineage["_record_hash"] = with_lineage.apply(_record_hash, axis=1)
    return with_lineage


def _record_hash(row: pd.Series) -> str:
    """Generate a stable hash for one cleaned record."""
    payload: dict[str, Any] = {}
    for key, value in row.to_dict().items():
        if key in {"_record_hash"}:
            continue
        payload[str(key)] = None if pd.isna(value) else value
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def main(argv: list[str]) -> int:
    """Run pipeline processing from the command line."""
    if len(argv) != 3:
        print(
            json.dumps(
                {
                    "error": "用法: python clean_dataset.py input.csv rules.yaml",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    try:
        result = process_dataset(argv[1], argv[2])
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
