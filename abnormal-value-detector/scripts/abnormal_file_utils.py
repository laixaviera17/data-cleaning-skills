"""Shared file helpers for abnormal-value-detector.

This module only handles generic CSV/JSON reading, JSON writing, directory
creation, and file existence checks. It does not contain detection logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError


DEFAULT_ENCODING = "utf-8"


def file_exists(file_path: str | Path) -> bool:
    """Return whether a path exists and is a regular file."""
    return Path(file_path).is_file()


def ensure_directory(directory_path: str | Path) -> Path:
    """Create a directory if needed and return the normalized Path."""
    directory = Path(directory_path)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"无法创建目录: {directory}") from exc
    return directory


def load_csv(file_path: str | Path, encoding: str = DEFAULT_ENCODING, **kwargs: Any) -> pd.DataFrame:
    """Load a UTF-8 CSV file as a pandas DataFrame."""
    path = _require_existing_file(file_path)
    try:
        return pd.read_csv(path, encoding=encoding, keep_default_na=False, **kwargs)
    except EmptyDataError:
        return pd.DataFrame()
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"CSV 文件编码错误，请确认是否为 {encoding}: {path}") from exc
    except Exception as exc:
        raise RuntimeError(f"CSV 文件读取失败: {path}") from exc


def load_json(file_path: str | Path, encoding: str = DEFAULT_ENCODING, **kwargs: Any) -> pd.DataFrame:
    """Load a UTF-8 JSON file as a pandas DataFrame."""
    path = _require_existing_file(file_path)
    if path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_json(path, encoding=encoding, **kwargs)
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"JSON 文件编码错误，请确认是否为 {encoding}: {path}") from exc
    except Exception as exc:
        raise RuntimeError(f"JSON 文件读取失败: {path}") from exc


def load_data(file_path: str | Path) -> pd.DataFrame:
    """Load CSV or JSON data based on file extension."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_csv(path)
    if suffix == ".json":
        return load_json(path)
    raise ValueError(f"不支持的文件格式: {suffix}")


def save_json(data: dict[str, Any], file_path: str | Path, encoding: str = DEFAULT_ENCODING) -> Path:
    """Save a dictionary as a UTF-8 JSON file and create its directory."""
    path = Path(file_path)
    if path.parent and str(path.parent) != ".":
        ensure_directory(path.parent)
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding=encoding)
    except OSError as exc:
        raise RuntimeError(f"JSON 文件写入失败: {path}") from exc
    return path


def _require_existing_file(file_path: str | Path) -> Path:
    """Return a Path when it exists, otherwise raise FileNotFoundError."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return path
