"""Shared file helpers for structured issue list generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_ENCODING = "utf-8"


def ensure_directory(directory_path: str | Path) -> Path:
    """Create a directory when it does not exist and return it."""
    directory = Path(directory_path)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"无法创建目录: {directory}") from exc
    return directory


def load_csv(file_path: str | Path) -> pd.DataFrame:
    """Load a CSV file, returning an empty DataFrame for a header-only file."""
    path = _require_existing_file(file_path)
    try:
        return pd.read_csv(path, encoding=DEFAULT_ENCODING, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"CSV 文件编码错误，请确认是否为 UTF-8: {path}") from exc
    except Exception as exc:
        raise RuntimeError(f"CSV 文件读取失败: {path}") from exc


def load_json_dict(file_path: str | Path) -> dict[str, Any]:
    """Load a JSON object from a UTF-8 file."""
    path = _require_existing_file(file_path)
    try:
        data = json.loads(path.read_text(encoding=DEFAULT_ENCODING))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON 文件解析失败: {path}") from exc
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"JSON 文件编码错误，请确认是否为 UTF-8: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON 文件根节点必须是对象: {path}")
    return data


def save_csv(dataframe: pd.DataFrame, file_path: str | Path) -> Path:
    """Save a DataFrame to CSV."""
    path = _prepare_output_path(file_path)
    try:
        dataframe.to_csv(path, encoding=DEFAULT_ENCODING, index=False)
    except Exception as exc:
        raise RuntimeError(f"CSV 文件导出失败: {path}") from exc
    return path


def save_json_dict(data: dict[str, Any], file_path: str | Path) -> Path:
    """Save a dictionary as UTF-8 JSON."""
    path = _prepare_output_path(file_path)
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding=DEFAULT_ENCODING)
    except Exception as exc:
        raise RuntimeError(f"JSON 文件导出失败: {path}") from exc
    return path


def _require_existing_file(file_path: str | Path) -> Path:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return path


def _prepare_output_path(file_path: str | Path) -> Path:
    path = Path(file_path)
    ensure_directory(path.parent)
    return path
