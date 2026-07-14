"""Shared YAML loader with a small standard-library fallback.

Use PyYAML when it is installed. Fall back to a deliberately small parser that
supports the project rule files: dictionaries, nested lists, booleans, nulls,
integers, floats, and quoted strings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - depends on environment
    yaml = None


def load_yaml_file(path: str | Path) -> Any:
    yaml_path = Path(path)
    if not yaml_path.is_file():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")
    return load_yaml_text(yaml_path.read_text(encoding="utf-8"))


def load_yaml_text(text: str) -> Any:
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return parse_simple_yaml(text)


def parse_simple_yaml(text: str) -> Any:
    lines = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))
    if not lines:
        return {}
    parsed, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError("unsupported YAML structure")
    return parsed


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    if lines[index][1].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_dict(lines, index, indent)


def _parse_dict(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError(f"unexpected indentation near: {text}")
        if text.startswith("- "):
            break
        key, value = _split_key_value(text)
        if value == "":
            if index + 1 < len(lines) and lines[index + 1][0] > current_indent:
                nested, index = _parse_block(lines, index + 1, lines[index + 1][0])
                result[key] = nested
                continue
            result[key] = {}
        else:
            result[key] = _parse_scalar(value)
        index += 1
    return result, index


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError(f"unexpected indentation near: {text}")
        if not text.startswith("- "):
            break
        item_text = text[2:].strip()
        if item_text == "":
            if index + 1 < len(lines) and lines[index + 1][0] > current_indent:
                nested, index = _parse_block(lines, index + 1, lines[index + 1][0])
                result.append(nested)
                continue
            result.append(None)
        elif _has_top_level_colon(item_text):
            key, value = _split_key_value(item_text)
            item: dict[str, Any] = {key: _parse_scalar(value) if value else {}}
            index += 1
            while index < len(lines) and lines[index][0] > current_indent:
                nested_indent, nested_text = lines[index]
                if nested_indent <= current_indent:
                    break
                nested_key, nested_value = _split_key_value(nested_text)
                if nested_value == "":
                    if index + 1 < len(lines) and lines[index + 1][0] > nested_indent:
                        nested, index = _parse_block(lines, index + 1, lines[index + 1][0])
                        item[nested_key] = nested
                        continue
                    item[nested_key] = {}
                else:
                    item[nested_key] = _parse_scalar(nested_value)
                index += 1
            result.append(item)
            continue
        else:
            result.append(_parse_scalar(item_text))
        index += 1
    return result, index


def _split_key_value(text: str) -> tuple[str, str]:
    colon_index = _find_top_level_colon(text)
    if colon_index < 0:
        raise ValueError(f"expected key/value pair: {text}")
    key = text[:colon_index].strip()
    value = text[colon_index + 1 :].strip()
    if not key:
        raise ValueError(f"empty YAML key: {text}")
    return key, value


def _has_top_level_colon(text: str) -> bool:
    return _find_top_level_colon(text) >= 0


def _find_top_level_colon(text: str) -> int:
    quote: str | None = None
    for index, char in enumerate(text):
        if char in {'"', "'"}:
            quote = char if quote is None else None if quote == char else quote
        elif char == ":" and quote is None:
            return index
    return -1


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
