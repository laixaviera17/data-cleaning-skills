"""Shared file helpers for before/after dataset diff comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_ENCODING = "utf-8"
SUPPORTED_SUFFIXES = {".csv", ".json", ".jsonl"}


def ensure_directory(directory_path: str | Path) -> Path:
    """Create a directory when it does not exist and return it."""
    directory = Path(directory_path)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"无法创建目录: {directory}") from exc
    return directory


def load_dataset(file_path: str | Path) -> pd.DataFrame:
    """Load CSV, JSON, or JSONL data into a DataFrame."""
    path = _require_existing_file(file_path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(path, encoding=DEFAULT_ENCODING, keep_default_na=False)
        if suffix == ".json":
            return pd.read_json(path, encoding=DEFAULT_ENCODING)
        if suffix == ".jsonl":
            return pd.read_json(path, lines=True, encoding=DEFAULT_ENCODING)
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"文件编码错误，请确认是否为 UTF-8: {path}") from exc
    except pd.errors.EmptyDataError as exc:
        raise RuntimeError(f"输入文件为空: {path}") from exc
    except Exception as exc:
        raise RuntimeError(f"输入文件读取失败: {path}") from exc
    raise ValueError(f"不支持的输入文件类型: {suffix}; 支持类型: {sorted(SUPPORTED_SUFFIXES)}")


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
