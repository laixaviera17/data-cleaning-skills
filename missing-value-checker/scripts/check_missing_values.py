"""Check and repair missing fields and missing cells in CSV/JSON datasets.

This module implements rule-driven repair for missing cells and quality report
generation. It does not export cleaned data or generate issue rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SHARED_DIR = Path(__file__).resolve().parents[2] / "qa" / "shared"
if SHARED_DIR.exists() and str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from missing_file_utils import load_data, save_json
from simple_yaml import load_yaml_text


DEFAULT_NULL_VALUES = ["", "null", "NULL", "None", "N/A", "NA", "nan", "NaN", "未知"]
DEFAULT_REPORT_NAME = "quality_report.json"


def load_rules(rules_path: str | Path) -> dict[str, Any]:
    """Load a YAML rules file.

    Args:
        rules_path: YAML file path.

    Returns:
        Parsed rules dictionary.

    Raises:
        FileNotFoundError: If the rules file does not exist.
        RuntimeError: If YAML parsing fails.
        ValueError: If the YAML root is not a dictionary.
    """
    path = Path(rules_path)
    if not path.is_file():
        raise FileNotFoundError(f"规则文件不存在: {path}")

    content = path.read_text(encoding="utf-8")
    rules = _load_yaml_content(content, path)

    if not isinstance(rules, dict):
        raise ValueError("规则文件根节点必须是字典")
    return rules


def _load_yaml_content(content: str, path: Path) -> dict[str, Any]:
    """Load YAML content through the workspace shared YAML helper."""
    try:
        return load_yaml_text(content)
    except ValueError as exc:
        raise RuntimeError(f"规则文件解析失败: {path}") from exc


def build_quality_report(dataframe: pd.DataFrame, rules: dict[str, Any]) -> dict[str, Any]:
    """Build missing-value quality statistics and repair counts for a DataFrame."""
    _, report = process_dataframe(dataframe, rules)
    return report


def process_dataframe(dataframe: pd.DataFrame, rules: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Repair missing cells according to rules and return the report."""
    required_fields = _get_required_fields(rules)
    null_values = _get_null_values(rules)
    missing_mask = _build_missing_mask(dataframe, null_values)
    field_stats = _build_field_stats(dataframe, missing_mask)
    missing_fields = [field for field in required_fields if field not in dataframe.columns]
    repaired_dataframe = dataframe.copy()
    repair_stats = _apply_repair_rules(repaired_dataframe, null_values, _get_field_rules(rules))
    repaired_cells = int(repair_stats["repaired_cells"])
    dropped_cells = int(repair_stats["dropped_cells"])
    dropped_rows = int(repair_stats["dropped_rows"])
    missing_cells = int(missing_mask.sum().sum()) if not missing_mask.empty else 0

    report = {
        "total_rows": int(len(dataframe)),
        "output_rows": int(len(repaired_dataframe)),
        "total_fields": int(len(dataframe.columns)),
        "missing_cells": missing_cells,
        "repaired_cells": repaired_cells,
        "dropped_rows": dropped_rows,
        "dropped_cells": dropped_cells,
        "unrepaired_cells": int(max(missing_cells - repaired_cells - dropped_cells, 0)),
        "missing_fields": missing_fields,
        "field_stats": field_stats,
        "strategy_stats": repair_stats["strategy_stats"],
    }
    return repaired_dataframe, report


def process_dataset(input_path: str | Path, rules_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Read input data and rules, then write quality_report.json."""
    dataframe = load_data(input_path)
    rules = load_rules(rules_path)
    _, report = process_dataframe(dataframe, rules)

    output_path = _resolve_output_path(rules, output_dir)
    save_json(report, output_path)
    return report


def _get_required_fields(rules: dict[str, Any]) -> list[str]:
    """Extract required field names from rules."""
    required_fields = rules.get("required_fields", [])
    if required_fields is None:
        return []
    if not isinstance(required_fields, list):
        raise ValueError("required_fields 必须是列表")

    fields: list[str] = []
    for item in required_fields:
        if isinstance(item, str):
            fields.append(item)
        elif isinstance(item, dict) and isinstance(item.get("field"), str):
            fields.append(item["field"])
        else:
            raise ValueError("required_fields 中的字段必须是字符串或包含 field 的字典")
    return fields


def _get_null_values(rules: dict[str, Any]) -> set[str]:
    """Extract configured null-like values from rules."""
    null_values = rules.get("null_values", DEFAULT_NULL_VALUES)
    if null_values is None:
        return set(DEFAULT_NULL_VALUES)
    if not isinstance(null_values, list):
        raise ValueError("null_values 必须是列表")
    return {str(value).strip() for value in null_values}


def _get_field_rules(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract per-field repair rules."""
    field_rules = rules.get("field_rules", {})
    if field_rules in (None, ""):
        return {}

    if isinstance(field_rules, dict):
        normalized: dict[str, dict[str, Any]] = {}
        for field, config in field_rules.items():
            if isinstance(config, dict):
                normalized[str(field)] = config
            else:
                raise ValueError("field_rules 中每个字段的配置必须是字典")
        return normalized

    if isinstance(field_rules, list):
        normalized = {}
        for item in field_rules:
            if not isinstance(item, dict) or not isinstance(item.get("field"), str):
                raise ValueError("field_rules 列表项必须包含 field")
            normalized[item["field"]] = {key: value for key, value in item.items() if key != "field"}
        return normalized

    raise ValueError("field_rules 必须是字典或列表")


def _apply_repair_rules(
    dataframe: pd.DataFrame,
    null_values: set[str],
    field_rules: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Repair/drop missing values in place and return action stats."""
    repaired_cells = 0
    dropped_cells = 0
    dropped_rows = 0
    drop_indices: set[Any] = set()
    strategy_stats: dict[str, int] = {}

    for field, rule in field_rules.items():
        if field not in dataframe.columns:
            continue

        action = str(rule.get("action", "keep_null")).strip()
        mask = _series_missing_mask(dataframe[field], null_values)
        affected_cells = int(mask.sum())
        if affected_cells == 0:
            continue

        if action == "keep_null":
            strategy_stats[action] = strategy_stats.get(action, 0) + affected_cells
            continue
        if action not in {"fill_default", "fill_custom", "fill", "mean", "median", "mode", "ffill", "bfill", "drop"}:
            raise ValueError(f"不支持的缺失值修复动作: {action}")

        if action == "drop":
            drop_indices.update(dataframe.index[mask].tolist())
            dropped_cells += affected_cells
            strategy_stats[action] = strategy_stats.get(action, 0) + affected_cells
            continue

        filled_count, fill_value = _resolve_fill_value(dataframe[field], mask, rule, action)
        if filled_count <= 0:
            continue
        if dataframe[field].dtype != "object":
            dataframe[field] = dataframe[field].astype("object")
        if isinstance(fill_value, pd.Series):
            dataframe.loc[mask & fill_value.notna(), field] = fill_value.loc[mask & fill_value.notna()]
        else:
            dataframe.loc[mask, field] = fill_value
        repaired_cells += filled_count
        strategy_stats[action] = strategy_stats.get(action, 0) + filled_count

    if drop_indices:
        dataframe.drop(index=sorted(drop_indices), inplace=True)
        dropped_rows = len(drop_indices)

    return {
        "repaired_cells": repaired_cells,
        "dropped_cells": dropped_cells,
        "dropped_rows": dropped_rows,
        "strategy_stats": strategy_stats,
    }


def _resolve_fill_value(series: pd.Series, mask: pd.Series, rule: dict[str, Any], action: str) -> tuple[int, Any]:
    """Resolve one missing-value strategy into a concrete fill value."""
    if action in {"fill_default", "fill_custom", "fill"}:
        value = rule.get("value", rule.get("fill_value"))
        if value is None:
            return 0, None
        return int(mask.sum()), value

    non_missing_series = series.where(~mask)
    numeric = pd.to_numeric(non_missing_series, errors="coerce").dropna()
    if action == "mean":
        if numeric.empty:
            return 0, None
        return int(mask.sum()), float(numeric.mean())
    if action == "median":
        if numeric.empty:
            return 0, None
        return int(mask.sum()), float(numeric.median())
    if action == "mode":
        mode = non_missing_series.dropna().mode()
        if mode.empty:
            return 0, None
        return int(mask.sum()), mode.iloc[0]
    if action == "ffill":
        filled = non_missing_series.ffill()
        fill_mask = mask & filled.notna()
        return int(fill_mask.sum()), filled
    if action == "bfill":
        filled = non_missing_series.bfill()
        fill_mask = mask & filled.notna()
        return int(fill_mask.sum()), filled
    return 0, None


def _build_missing_mask(dataframe: pd.DataFrame, null_values: set[str]) -> pd.DataFrame:
    """Build a boolean mask for missing cells."""
    if dataframe.empty and len(dataframe.columns) == 0:
        return pd.DataFrame()

    def is_missing(value: Any) -> bool:
        if pd.isna(value):
            return True
        return str(value).strip() in null_values

    if hasattr(dataframe, "map"):
        return dataframe.map(is_missing)
    return dataframe.applymap(is_missing)


def _series_missing_mask(series: pd.Series, null_values: set[str]) -> pd.Series:
    """Build a missing mask for one pandas Series."""
    return series.map(lambda value: pd.isna(value) or str(value).strip() in null_values)


def _build_field_stats(dataframe: pd.DataFrame, missing_mask: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Build per-field missing statistics."""
    stats: dict[str, dict[str, Any]] = {}
    total_rows = int(len(dataframe))
    for field in dataframe.columns:
        missing_count = int(missing_mask[field].sum()) if field in missing_mask else 0
        missing_rate = round(missing_count / total_rows, 4) if total_rows else 0
        stats[str(field)] = {
            "missing_cells": missing_count,
            "non_missing_cells": total_rows - missing_count,
            "missing_rate": missing_rate,
        }
    return stats


def _resolve_output_path(rules: dict[str, Any], output_dir: str | Path | None) -> Path:
    """Resolve the quality report output path."""
    output_config = rules.get("output", {}) if isinstance(rules.get("output", {}), dict) else {}
    report_name = output_config.get("quality_report_name", DEFAULT_REPORT_NAME)
    directory = output_dir or output_config.get("output_dir", "examples/expected_outputs")
    return Path(directory) / str(report_name)


def main() -> int:
    """Command-line entry point."""
    if len(sys.argv) not in (3, 4):
        print("Usage: python check_missing_values.py input.csv rules.yaml [output_dir]", file=sys.stderr)
        return 2

    input_path = sys.argv[1]
    rules_path = sys.argv[2]
    output_dir = sys.argv[3] if len(sys.argv) == 4 else None

    try:
        report = process_dataset(input_path, rules_path, output_dir)
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
