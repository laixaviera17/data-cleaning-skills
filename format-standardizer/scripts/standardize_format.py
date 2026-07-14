"""Standardize format, unit, and encoding for CSV/JSON datasets."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError

SHARED_DIR = Path(__file__).resolve().parents[2] / "qa" / "shared"
if SHARED_DIR.exists() and str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from format_file_utils import ensure_directory, save_json
from simple_yaml import load_yaml_text


DEFAULT_REPORT_NAME = "standardization_report.json"
DEFAULT_ABNORMAL_NAME = "abnormal_records.json"
DEFAULT_DATA_NAME = "standardized_data.csv"
DEFAULT_ENCODING_REPORT_NAME = "encoding_report.json"
DEFAULT_ENCODING_CANDIDATES = ["utf-8-sig", "utf-8", "gb18030", "gbk"]

UNIT_FACTORS = {
    "weight": {
        "base_unit": "g",
        "aliases": {"mg": "mg", "g": "g", "kg": "kg", "t": "t", "吨": "t"},
        "to_base": {"mg": Decimal("0.001"), "g": Decimal("1"), "kg": Decimal("1000"), "t": Decimal("1000000")},
    },
    "length": {
        "base_unit": "m",
        "aliases": {"mm": "mm", "cm": "cm", "m": "m", "km": "km", "米": "m"},
        "to_base": {"mm": Decimal("0.001"), "cm": Decimal("0.01"), "m": Decimal("1"), "km": Decimal("1000")},
    },
    "time": {
        "base_unit": "s",
        "aliases": {"ms": "ms", "s": "s", "sec": "s", "min": "min", "h": "h", "hour": "h", "d": "d", "天": "d"},
        "to_base": {
            "ms": Decimal("0.001"),
            "s": Decimal("1"),
            "min": Decimal("60"),
            "h": Decimal("3600"),
            "d": Decimal("86400"),
        },
    },
    "currency": {
        "base_unit": "cny",
        "aliases": {"¥": "cny", "￥": "cny", "cny": "cny", "rmb": "cny", "元": "cny", "fen": "fen", "分": "fen"},
        "to_base": {"cny": Decimal("1"), "fen": Decimal("0.01")},
    },
}


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


def process_dataset(input_path: str | Path, rules_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Load data and rules, standardize values, and write reports/artifacts."""
    rules = load_rules(rules_path)
    dataframe, encoding_report = _load_data_with_encoding(input_path, rules)
    standardized, report = process_dataframe(dataframe, rules)
    report["encoding_report"] = encoding_report

    report_path = _resolve_output_path(rules, output_dir, "standardization_report_name", DEFAULT_REPORT_NAME)
    abnormal_path = _resolve_output_path(rules, output_dir, "abnormal_records_name", DEFAULT_ABNORMAL_NAME)
    encoding_path = _resolve_output_path(rules, output_dir, "encoding_report_name", DEFAULT_ENCODING_REPORT_NAME)
    data_path = _resolve_output_path(rules, output_dir, "standardized_data_name", DEFAULT_DATA_NAME)

    save_json(report, report_path)
    save_json({"abnormal_records": report["abnormal_records"]}, abnormal_path)
    save_json(encoding_report, encoding_path)
    _save_standardized_data(standardized, data_path, rules)
    return report


def process_dataframe(dataframe: pd.DataFrame, rules: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Standardize configured fields and return data plus report."""
    standardized = dataframe.copy()
    configs = _get_standardize_fields(rules)
    missing_fields: list[str] = []
    field_stats: dict[str, dict[str, Any]] = {}
    abnormal_records: list[dict[str, Any]] = []
    unit_conversion_records: list[dict[str, Any]] = []

    for field_type, field_configs in configs.items():
        for config in field_configs:
            if not config.get("enable", True):
                continue
            field = config.get("field")
            if not isinstance(field, str) or not field:
                raise ValueError(f"{field_type} 标准化配置缺少 field")
            if field not in standardized.columns:
                missing_fields.append(field)
                continue
            field_stats[field] = _standardize_field(
                standardized,
                field,
                field_type,
                config,
                abnormal_records,
                unit_conversion_records,
            )

    standardized_cells = sum(item["standardized_cells"] for item in field_stats.values())
    failed_cells = sum(item["failed_cells"] for item in field_stats.values())

    report = {
        "total_rows": int(len(dataframe)),
        "standardized_cells": int(standardized_cells),
        "failed_cells": int(failed_cells),
        "missing_fields": missing_fields,
        "abnormal_records": abnormal_records,
        "field_stats": field_stats,
        "unit_conversion_records": unit_conversion_records,
    }
    return standardized, report


def standardize_date(value: Any) -> str | None:
    """Standardize supported date formats to YYYY-MM-DD."""
    text = _to_clean_text(value)
    if text is None:
        return None
    normalized = text.replace("年", "-").replace("月", "-").replace("日", "")

    formats = ["%Y/%m/%d", "%Y-%m-%d", "%d-%m-%Y", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"]
    for date_format in formats:
        try:
            return datetime.strptime(normalized, date_format).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def standardize_phone(value: Any, country_code: str = "86") -> str | None:
    """Standardize supported phone formats to 11 digits."""
    text = _to_clean_text(value)
    if text is None:
        return None

    digits = re.sub(r"\D", "", text)
    if digits.startswith(f"00{country_code}") and len(digits) == 15:
        digits = digits[4:]
    elif digits.startswith(country_code) and len(digits) == 13:
        digits = digits[2:]

    if re.fullmatch(r"1[3-9]\d{9}", digits):
        return digits
    return None


def standardize_amount(value: Any, decimal_places: int = 2, allow_negative: bool = True) -> str | None:
    """Standardize supported amount formats to a fixed decimal string."""
    text = _to_clean_text(value)
    if text is None:
        return None

    cleaned = (
        text.replace("￥", "")
        .replace("¥", "")
        .replace("$", "")
        .replace(",", "")
        .replace("元", "")
        .replace("rmb", "")
        .replace("RMB", "")
        .replace("CNY", "")
        .replace("cny", "")
        .strip()
    )
    if not re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
        return None

    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not allow_negative and amount < 0:
        return None
    quantizer = Decimal("1").scaleb(-decimal_places)
    return str(amount.quantize(quantizer))


def standardize_id_card(value: Any) -> str | None:
    """Standardize CN ID card values to 18-char uppercase format."""
    text = _to_clean_text(value)
    if text is None:
        return None
    normalized = re.sub(r"\s+", "", text).upper()
    if re.fullmatch(r"\d{17}[\dX]", normalized):
        return normalized
    return None


def standardize_unit_with_detail(value: Any, config: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """Standardize unit-like values and return conversion detail."""
    text = _to_clean_text(value)
    if text is None:
        return None, None
    unit_type = str(config.get("unit_type", "")).strip().lower()
    target_unit = str(config.get("target_unit", "")).strip().lower()
    precision = int(config.get("decimal_places", 4))
    keep_unit_suffix = bool(config.get("keep_unit_suffix", True))
    if unit_type not in UNIT_FACTORS:
        return None, None

    unit_spec = UNIT_FACTORS[unit_type]
    if target_unit not in unit_spec["to_base"]:
        return None, None

    parsed = _parse_numeric_with_unit(text, unit_spec["aliases"])
    if parsed is None:
        return None, None
    numeric, parsed_unit = parsed

    try:
        number = Decimal(numeric)
    except InvalidOperation:
        return None, None

    source_unit = parsed_unit or target_unit
    if source_unit not in unit_spec["to_base"]:
        return None, None

    base_value = number * unit_spec["to_base"][source_unit]
    converted = base_value / unit_spec["to_base"][target_unit]
    quantizer = Decimal("1").scaleb(-precision)
    converted_text = str(converted.quantize(quantizer))
    output_value = f"{converted_text}{target_unit}" if keep_unit_suffix else converted_text
    detail = {
        "field": config.get("field", ""),
        "original_value": text,
        "target_value": output_value,
        "rule": f"{unit_type}:{source_unit}->{target_unit}",
    }
    return output_value, detail


def _standardize_field(
    dataframe: pd.DataFrame,
    field: str,
    field_type: str,
    config: dict[str, Any],
    abnormal_records: list[dict[str, Any]],
    unit_conversion_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Standardize one field in place and return field-level stats."""
    standardized_cells = 0
    failed_cells = 0
    total_cells = int(len(dataframe))
    strict = bool(config.get("strict", False))
    if dataframe[field].dtype != "object":
        dataframe[field] = dataframe[field].astype("object")

    for index, value in dataframe[field].items():
        if field_type == "unit":
            standardized_value, detail = standardize_unit_with_detail(value, config)
            if detail is not None and standardized_value is not None:
                detail["row"] = int(index) + 1
                unit_conversion_records.append(detail)
        else:
            standardized_value = _standardize_value(value, field_type, config)

        if standardized_value is None:
            failed_cells += 1
            if _should_clear_invalid_value(config):
                dataframe.at[index, field] = ""
            if strict:
                abnormal_records.append(
                    {
                        "row": int(index) + 1,
                        "field": field,
                        "value": None if pd.isna(value) else str(value),
                        "issue_type": "standardization_failed",
                        "reason": f"{field_type}_standardization_failed",
                        "source_skill": "format-standardizer",
                        "action": "standardize",
                    }
                )
            continue
        dataframe.at[index, field] = standardized_value
        standardized_cells += 1

    return {
        "type": field_type,
        "total_cells": total_cells,
        "standardized_cells": standardized_cells,
        "failed_cells": failed_cells,
    }


def _standardize_value(value: Any, field_type: str, config: dict[str, Any]) -> str | None:
    """Dispatch value standardization by type."""
    if field_type == "date":
        return standardize_date(value)
    if field_type == "phone":
        return standardize_phone(value, str(config.get("country_code", "86")))
    if field_type == "amount":
        decimal_places = int(config.get("decimal_places", 2))
        allow_negative = bool(config.get("allow_negative", True))
        return standardize_amount(value, decimal_places, allow_negative=allow_negative)
    if field_type == "id_card":
        return standardize_id_card(value)
    raise ValueError(f"不支持的标准化类型: {field_type}")


def _should_clear_invalid_value(config: dict[str, Any]) -> bool:
    """Return whether failed standardization should blank the original value."""
    action = str(config.get("invalid_action", "mark")).lower()
    return action in {"set_null", "null", "clear", "blank", "empty"}


def _get_standardize_fields(rules: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Extract field configs from both legacy and rule-driven sections."""
    if any(key in rules for key in ("date_rules", "phone_rules", "amount_rules", "id_card_rules", "unit_rules")):
        return _get_rule_driven_fields(rules)

    standardize_fields = rules.get("standardize_fields", {})
    if not isinstance(standardize_fields, dict):
        raise ValueError("standardize_fields 必须是字典")

    result: dict[str, list[dict[str, Any]]] = {"date": [], "phone": [], "amount": [], "id_card": [], "unit": []}
    for field_type in result:
        configs = standardize_fields.get(field_type, [])
        if configs is None:
            continue
        if not isinstance(configs, list):
            raise ValueError(f"standardize_fields.{field_type} 必须是列表")
        for config in configs:
            if not isinstance(config, dict):
                raise ValueError(f"standardize_fields.{field_type} 列表项必须是字典")
            result[field_type].append(config)
    return result


def _get_rule_driven_fields(rules: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Extract field configs from rule-driven sections."""
    mapping = {
        "date": "date_rules",
        "phone": "phone_rules",
        "amount": "amount_rules",
        "id_card": "id_card_rules",
        "unit": "unit_rules",
    }
    result: dict[str, list[dict[str, Any]]] = {"date": [], "phone": [], "amount": [], "id_card": [], "unit": []}
    for field_type, rule_name in mapping.items():
        rule_config = rules.get(rule_name, {})
        if rule_config in (None, ""):
            continue
        if not isinstance(rule_config, dict):
            raise ValueError(f"{rule_name} 必须是字典")
        if not rule_config.get("enable", True):
            continue
        fields = rule_config.get("fields", [])
        if not isinstance(fields, list):
            raise ValueError(f"{rule_name}.fields 必须是列表")
        for item in fields:
            if isinstance(item, str):
                field = item
                item_config: dict[str, Any] = {}
            elif isinstance(item, dict) and isinstance(item.get("field"), str):
                field = item["field"]
                item_config = item
            else:
                raise ValueError(f"{rule_name}.fields 中的字段必须是字符串或包含 field 的字典")
            config = {
                "field": field,
                "enable": True,
                "strict": bool(item_config.get("strict", rule_config.get("strict", False))),
                "invalid_action": item_config.get("invalid_action", rule_config.get("invalid_action", "mark")),
            }
            if field_type == "date":
                config["output_format"] = item_config.get("output_format", rule_config.get("output_format", "%Y-%m-%d"))
            if field_type == "phone":
                config["country_code"] = item_config.get("country_code", rule_config.get("country_code", "86"))
            if field_type == "amount":
                config["decimal_places"] = int(item_config.get("decimal_places", rule_config.get("decimal_places", 2)))
                config["allow_negative"] = bool(item_config.get("allow_negative", rule_config.get("allow_negative", True)))
            if field_type == "unit":
                config["unit_type"] = item_config.get("unit_type", rule_config.get("unit_type", "weight"))
                config["target_unit"] = item_config.get("target_unit", rule_config.get("target_unit", "g"))
                config["decimal_places"] = int(item_config.get("decimal_places", rule_config.get("decimal_places", 4)))
                config["keep_unit_suffix"] = bool(item_config.get("keep_unit_suffix", rule_config.get("keep_unit_suffix", True)))
            result[field_type].append(config)
    return result


def _resolve_output_path(
    rules: dict[str, Any],
    output_dir: str | Path | None,
    output_name_key: str,
    default_name: str,
) -> Path:
    """Resolve report output path."""
    output_config = rules.get("output", {}) if isinstance(rules.get("output", {}), dict) else {}
    report_name = output_config.get(output_name_key, default_name)
    directory = output_dir or output_config.get("output_dir", "examples/expected_outputs")
    return Path(directory) / str(report_name)


def _to_clean_text(value: Any) -> str | None:
    """Convert a value to non-empty stripped text."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _load_yaml_content(content: str, path: Path) -> dict[str, Any]:
    """Load YAML content through the workspace shared YAML helper."""
    try:
        return load_yaml_text(content)
    except ValueError as exc:
        raise RuntimeError(f"规则文件解析失败: {path}") from exc


def _detect_encoding(path: Path, rules: dict[str, Any]) -> tuple[str, list[str]]:
    """Detect file encoding by trying a configured candidate list."""
    config = rules.get("encoding_rules", {}) if isinstance(rules.get("encoding_rules"), dict) else {}
    candidates = config.get("detect_order", DEFAULT_ENCODING_CANDIDATES)
    if not isinstance(candidates, list) or not candidates:
        candidates = DEFAULT_ENCODING_CANDIDATES
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", ["utf-8-sig:bom"]

    attempted: list[str] = []
    successful: list[tuple[str, str]] = []
    for candidate in candidates:
        try:
            decoded = data.decode(candidate)
        except UnicodeDecodeError:
            attempted.append(f"{candidate}:fail")
            continue
        attempted.append(f"{candidate}:ok")
        successful.append((candidate, decoded))
    if not successful:
        raise RuntimeError(f"无法识别编码: {path}")
    if len(successful) == 1:
        return successful[0][0], attempted

    non_ascii = any(byte > 0x7F for byte in data)
    if not non_ascii:
        return "utf-8", attempted

    scored = sorted(
        successful,
        key=lambda item: (_decoded_text_score(item[1]), 1 if item[0] in {"utf-8", "utf-8-sig"} else 0),
        reverse=True,
    )
    return scored[0][0], attempted


def _decoded_text_score(text: str) -> int:
    """Score decoded text quality. Higher score means more likely correct."""
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    printable = sum(1 for char in text if char.isprintable() or char in "\n\r\t")
    weird = sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t")
    replacement = text.count("\ufffd")
    return cjk * 5 + printable - weird * 4 - replacement * 20


def _load_data_with_encoding(input_path: str | Path, rules: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load CSV/JSON with detected source encoding."""
    path = Path(input_path)
    if not path.is_file():
        raise FileNotFoundError(f"输入文件不存在: {path}")
    source_encoding, attempted = _detect_encoding(path, rules)
    target_encoding = "utf-8"
    text = path.read_bytes().decode(source_encoding)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            dataframe = pd.read_csv(StringIO(text), keep_default_na=False)
        except EmptyDataError:
            dataframe = pd.DataFrame()
    elif suffix == ".json":
        payload = json.loads(text)
        if isinstance(payload, list):
            dataframe = pd.DataFrame(payload)
        elif isinstance(payload, dict):
            dataframe = pd.DataFrame([payload])
        else:
            raise ValueError("JSON 输入必须是对象或对象数组")
    else:
        raise ValueError(f"不支持的文件格式: {suffix}")

    report = {
        "input_file": str(path),
        "detected_encoding": source_encoding,
        "target_encoding": target_encoding,
        "attempted": attempted,
        "converted_to_utf8": source_encoding.lower() not in {"utf-8", "utf_8"},
    }
    return dataframe, report


def _save_standardized_data(dataframe: pd.DataFrame, data_path: Path, rules: dict[str, Any]) -> None:
    """Save standardized data with UTF-8 encoding."""
    output_config = rules.get("output", {}) if isinstance(rules.get("output"), dict) else {}
    if output_config.get("write_standardized_data", True) is False:
        return
    ensure_directory(data_path.parent)
    if data_path.suffix.lower() == ".json":
        data_path.write_text(dataframe.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    else:
        dataframe.to_csv(data_path, index=False, encoding="utf-8")


def _parse_numeric_with_unit(text: str, aliases: dict[str, str]) -> tuple[str, str | None] | None:
    """Parse values like '1.5kg' or '1000 m'."""
    match = re.fullmatch(r"\s*([-+]?\d+(?:\.\d+)?)\s*([A-Za-z\u4e00-\u9fff¥￥]+)?\s*", text)
    if not match:
        return None
    number = match.group(1)
    raw_unit = match.group(2)
    if raw_unit is None:
        return number, None
    normalized_unit = aliases.get(raw_unit.strip().lower(), aliases.get(raw_unit.strip(), ""))
    if not normalized_unit:
        return None
    return number, normalized_unit


def main() -> int:
    """Command-line entry point."""
    if len(sys.argv) not in (3, 4):
        print("Usage: python3 standardize_format.py input.csv rules.yaml [output_dir]", file=sys.stderr)
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
