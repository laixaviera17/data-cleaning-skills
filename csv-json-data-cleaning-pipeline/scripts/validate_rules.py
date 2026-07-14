#!/usr/bin/env python3
"""Validate CSV/JSON data cleaning rule files.

This script only validates rule configuration files. It does not read, clean,
repair, or transform business data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SHARED_DIR = Path(__file__).resolve().parents[2] / "qa" / "shared"
if SHARED_DIR.exists() and str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from simple_yaml import load_yaml_text


REQUIRED_SECTIONS = [
    "required_fields",
    "unique_keys",
    "null_handling",
    "date_rules",
    "phone_rules",
    "amount_rules",
]

ALLOWED_ACTIONS = {
    "mark",
    "drop",
    "fill",
    "fill_custom",
    "fill_default",
    "ignore",
    "export",
    "standardize",
    "manual_review",
    "keep_with_mark",
    "set_null",
    "mean",
    "median",
    "mode",
    "ffill",
    "bfill",
}


def load_yaml_file(path: str | Path) -> tuple[Any | None, list[str]]:
    """Read a UTF-8 YAML file and return parsed data plus read errors."""
    file_path = Path(path)
    errors: list[str] = []

    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, [f"配置文件不存在: {file_path}"]
    except UnicodeDecodeError:
        return None, [f"配置文件不是有效的 UTF-8 编码: {file_path}"]
    except OSError as exc:
        return None, [f"配置文件读取失败: {exc}"]

    if not text.strip():
        return None, ["配置文件为空"]

    try:
        return load_yaml_text(text), errors
    except ValueError as exc:
        return None, [f"YAML 解析失败: {exc}"]


def validate_rules(config: Any) -> dict[str, Any]:
    """Validate a parsed rule configuration and return a standard report."""
    errors: list[str] = []

    if not isinstance(config, dict):
        return {"valid": False, "errors": ["配置文件根节点必须是字典对象"]}
    if not config:
        return {"valid": False, "errors": ["配置文件不能为空"]}

    _validate_required_sections(config, errors)
    _validate_section_types(config, errors)

    if isinstance(config.get("required_fields"), list):
        _validate_required_fields(config["required_fields"], errors)
    if isinstance(config.get("unique_keys"), (dict, list)):
        _validate_unique_keys(config["unique_keys"], errors)
    if isinstance(config.get("null_handling"), dict):
        _validate_null_handling(config["null_handling"], errors)
    if isinstance(config.get("date_rules"), dict):
        _validate_date_rules(config["date_rules"], errors)
    if isinstance(config.get("phone_rules"), dict):
        _validate_phone_rules(config["phone_rules"], errors)
    if isinstance(config.get("amount_rules"), dict):
        _validate_amount_rules(config["amount_rules"], errors)
    if isinstance(config.get("enum_rules"), dict):
        _validate_enum_rules(config["enum_rules"], errors)

    return {"valid": not errors, "errors": errors}


def _validate_required_sections(config: dict[str, Any], errors: list[str]) -> None:
    """Check whether all required top-level sections exist."""
    for section in REQUIRED_SECTIONS:
        if section not in config:
            errors.append(f"缺少必需配置项: {section}")


def _validate_section_types(config: dict[str, Any], errors: list[str]) -> None:
    """Validate the expected type of each top-level section."""
    expected_types = {
        "required_fields": list,
        "null_handling": dict,
        "date_rules": dict,
        "phone_rules": dict,
        "amount_rules": dict,
    }
    for key, expected_type in expected_types.items():
        if key in config and not isinstance(config[key], expected_type):
            errors.append(f"{key} 必须为 {expected_type.__name__} 类型")

    if "unique_keys" in config and not isinstance(config["unique_keys"], (list, dict)):
        errors.append("unique_keys 必须为 list 类型，或包含 keys 列表的 dict 类型")


def _validate_required_fields(required_fields: list[Any], errors: list[str]) -> None:
    """Validate required field entries."""
    if not required_fields:
        errors.append("required_fields 不能为空")
        return

    for index, item in enumerate(required_fields):
        prefix = f"required_fields[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} 必须为字典")
            continue
        if not item.get("field"):
            errors.append(f"{prefix}.field 不能为空")
        if "allow_blank" in item and not isinstance(item["allow_blank"], bool):
            errors.append(f"{prefix}.allow_blank 必须为布尔值")
        _validate_action(item.get("action"), f"{prefix}.action", errors)


def _validate_unique_keys(unique_keys: dict[str, Any] | list[Any], errors: list[str]) -> None:
    """Validate unique key rules."""
    keys = unique_keys.get("keys") if isinstance(unique_keys, dict) else unique_keys
    if not isinstance(keys, list) or not keys:
        errors.append("unique_keys.keys 必须为非空列表")
        return

    for index, key_group in enumerate(keys):
        if isinstance(key_group, str):
            if not key_group.strip():
                errors.append(f"unique_keys.keys[{index}] 不能为空")
        elif isinstance(key_group, list):
            if not key_group or not all(isinstance(key, str) and key.strip() for key in key_group):
                errors.append(f"unique_keys.keys[{index}] 必须为非空字段列表")
        else:
            errors.append(f"unique_keys.keys[{index}] 必须为字符串或字符串列表")

    if isinstance(unique_keys, dict):
        keep = unique_keys.get("keep")
        if keep and keep not in {"first", "last", "latest"}:
            errors.append("unique_keys.keep 仅支持 first、last、latest")
        _validate_action(unique_keys.get("issue_action"), "unique_keys.issue_action", errors)
        similarity = unique_keys.get("similarity")
        if similarity is not None:
            _validate_similarity_config(similarity, errors)


def _validate_null_handling(null_handling: dict[str, Any], errors: list[str]) -> None:
    """Validate missing value handling rules."""
    null_values = null_handling.get("null_values")
    strategies = null_handling.get("strategies")

    if not isinstance(null_values, list) or not null_values:
        errors.append("null_handling.null_values 必须为非空列表")
    if strategies is not None and not isinstance(strategies, list):
        errors.append("null_handling.strategies 必须为列表")
        return

    for index, item in enumerate(strategies or []):
        prefix = f"null_handling.strategies[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} 必须为字典")
            continue
        if not item.get("field"):
            errors.append(f"{prefix}.field 不能为空")
        action = item.get("action")
        _validate_action(action, f"{prefix}.action", errors)
        if action in {"fill", "fill_custom", "fill_default"} and "fill_value" not in item and "value" not in item and "default_value" not in item:
            errors.append(f"{prefix}.fill_value 在 action=fill 时不能为空")


def _validate_date_rules(date_rules: dict[str, Any], errors: list[str]) -> None:
    """Validate date format rules."""
    date_format = date_rules.get("date_format") or date_rules.get("target_format")
    if not date_format:
        errors.append("date_rules.date_format 或 date_rules.target_format 不能为空")
    _validate_fields_list(date_rules, "date_rules", errors, require_input_formats=True)


def _validate_phone_rules(phone_rules: dict[str, Any], errors: list[str]) -> None:
    """Validate phone format rules."""
    if phone_rules.get("enabled", True) and not phone_rules.get("phone_pattern"):
        errors.append("phone_rules.phone_pattern 不能为空")
    _validate_fields_list(phone_rules, "phone_rules", errors)


def _validate_amount_rules(amount_rules: dict[str, Any], errors: list[str]) -> None:
    """Validate amount format rules."""
    precision = amount_rules.get("amount_precision")
    if precision is None:
        precision = amount_rules.get("decimal_places")
    if not isinstance(precision, int):
        errors.append("amount_rules.amount_precision 必须为整数")
    _validate_fields_list(amount_rules, "amount_rules", errors)


def _validate_enum_rules(enum_rules: dict[str, Any], errors: list[str]) -> None:
    """Validate enum value rules when configured."""
    fields = enum_rules.get("fields")
    if enum_rules.get("enabled", True) and (not isinstance(fields, list) or not fields):
        errors.append("enum_rules.fields 必须为非空列表")
        return

    for index, item in enumerate(fields or []):
        prefix = f"enum_rules.fields[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} 必须为字典")
            continue
        if not item.get("field"):
            errors.append(f"{prefix}.field 不能为空")
        allowed_values = item.get("allowed_values")
        if not isinstance(allowed_values, list) or not allowed_values:
            errors.append(f"{prefix}.allowed_values 必须为非空列表")
        _validate_action(item.get("invalid_action"), f"{prefix}.invalid_action", errors)


def _validate_fields_list(
    section: dict[str, Any],
    section_name: str,
    errors: list[str],
    require_input_formats: bool = False,
) -> None:
    """Validate a section with a fields list."""
    fields = section.get("fields")
    if section.get("enabled", True) and (not isinstance(fields, list) or not fields):
        errors.append(f"{section_name}.fields 必须为非空列表")
        return

    for index, item in enumerate(fields or []):
        prefix = f"{section_name}.fields[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} 必须为字典")
            continue
        if not item.get("field"):
            errors.append(f"{prefix}.field 不能为空")
        if require_input_formats:
            input_formats = item.get("input_formats")
            if not isinstance(input_formats, list) or not input_formats:
                errors.append(f"{prefix}.input_formats 必须为非空列表")
        _validate_action(item.get("invalid_action"), f"{prefix}.invalid_action", errors)


def _validate_action(action: Any, path: str, errors: list[str]) -> None:
    """Validate a rule action value when present."""
    if action is None:
        return
    if action not in ALLOWED_ACTIONS:
        errors.append(f"{path} 不支持: {action}")


def _validate_similarity_config(similarity: Any, errors: list[str]) -> None:
    """Validate similarity dedup configuration."""
    if not isinstance(similarity, dict):
        errors.append("unique_keys.similarity 必须为字典")
        return
    enabled = similarity.get("enabled", False)
    if not isinstance(enabled, bool):
        errors.append("unique_keys.similarity.enabled 必须为布尔值")
    if not enabled:
        return
    fields = similarity.get("fields", similarity.get("field"))
    if isinstance(fields, str):
        fields_list = [fields] if fields.strip() else []
    elif isinstance(fields, list):
        fields_list = [field for field in fields if isinstance(field, str) and field.strip()]
    else:
        fields_list = []
    if not fields_list:
        errors.append("unique_keys.similarity.fields 必须为非空字段列表或字符串")
    threshold = similarity.get("threshold", 0.92)
    if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
        errors.append("unique_keys.similarity.threshold 必须在 0 到 1 之间")


def validate_file(path: str | Path) -> dict[str, Any]:
    """Load and validate a YAML rule file."""
    config, errors = load_yaml_file(path)
    if errors:
        return {"valid": False, "errors": errors}
    return validate_rules(config)


def main(argv: list[str]) -> int:
    """Run validation from the command line."""
    if len(argv) != 2:
        print(
            json.dumps(
                {"valid": False, "errors": ["用法: python validate_rules.py sample_rules.yaml"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    result = validate_file(argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
