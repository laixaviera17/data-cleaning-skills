"""Shared file input/output helpers for CSV/JSON data cleaning skills.

This module only provides generic file reading, writing, directory creation,
and existence checks. It intentionally contains no business cleaning logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_ENCODING = "utf-8"


def file_exists(file_path: str | Path) -> bool:
    """Return whether a path exists and is a regular file."""
    return Path(file_path).is_file()


def ensure_directory(directory_path: str | Path) -> Path:
    """Create a directory when it does not exist and return its Path object.

    Args:
        directory_path: Directory path to create.

    Returns:
        The normalized directory Path.

    Raises:
        RuntimeError: If the directory cannot be created.
    """
    directory = Path(directory_path)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"无法创建目录: {directory}") from exc
    return directory


def load_csv(file_path: str | Path, encoding: str = DEFAULT_ENCODING, **kwargs: Any) -> pd.DataFrame:
    """Load a UTF-8 CSV file as a pandas DataFrame.

    Args:
        file_path: CSV file path.
        encoding: File encoding, defaults to UTF-8.
        **kwargs: Extra keyword arguments passed to pandas.read_csv.

    Returns:
        Loaded DataFrame.

    Raises:
        FileNotFoundError: If the input file does not exist.
        RuntimeError: If pandas fails to read the CSV file.
    """
    path = _require_existing_file(file_path)
    try:
        return pd.read_csv(path, encoding=encoding, **kwargs)
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"CSV 文件编码错误，请确认是否为 {encoding}: {path}") from exc
    except Exception as exc:
        raise RuntimeError(f"CSV 文件读取失败: {path}") from exc


def load_json(file_path: str | Path, encoding: str = DEFAULT_ENCODING, **kwargs: Any) -> pd.DataFrame:
    """Load a UTF-8 JSON file as a pandas DataFrame.

    Args:
        file_path: JSON file path. JSON array records are recommended.
        encoding: File encoding, defaults to UTF-8.
        **kwargs: Extra keyword arguments passed to pandas.read_json.

    Returns:
        Loaded DataFrame.

    Raises:
        FileNotFoundError: If the input file does not exist.
        RuntimeError: If pandas fails to read the JSON file.
    """
    path = _require_existing_file(file_path)
    try:
        return pd.read_json(path, encoding=encoding, **kwargs)
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"JSON 文件编码错误，请确认是否为 {encoding}: {path}") from exc
    except Exception as exc:
        raise RuntimeError(f"JSON 文件读取失败: {path}") from exc


def load_jsonl(file_path: str | Path, encoding: str = DEFAULT_ENCODING, **kwargs: Any) -> pd.DataFrame:
    """Load a UTF-8 JSONL file as a pandas DataFrame.

    Args:
        file_path: JSONL file path, one JSON object per line.
        encoding: File encoding, defaults to UTF-8.
        **kwargs: Extra keyword arguments passed to pandas.read_json.

    Returns:
        Loaded DataFrame.

    Raises:
        FileNotFoundError: If the input file does not exist.
        RuntimeError: If pandas fails to read the JSONL file.
    """
    path = _require_existing_file(file_path)
    try:
        return pd.read_json(path, lines=True, encoding=encoding, **kwargs)
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"JSONL 文件编码错误，请确认是否为 {encoding}: {path}") from exc
    except Exception as exc:
        raise RuntimeError(f"JSONL 文件读取失败: {path}") from exc


def save_csv(
    dataframe: pd.DataFrame,
    file_path: str | Path,
    encoding: str = DEFAULT_ENCODING,
    index: bool = False,
    **kwargs: Any,
) -> Path:
    """Save a DataFrame to CSV and create the output directory if needed.

    Args:
        dataframe: DataFrame to export.
        file_path: Output CSV path.
        encoding: File encoding, defaults to UTF-8.
        index: Whether to include the DataFrame index.
        **kwargs: Extra keyword arguments passed to DataFrame.to_csv.

    Returns:
        The output Path.

    Raises:
        TypeError: If dataframe is not a pandas DataFrame.
        RuntimeError: If writing fails.
    """
    _require_dataframe(dataframe)
    path = _prepare_output_path(file_path)
    try:
        dataframe.to_csv(path, encoding=encoding, index=index, **kwargs)
    except Exception as exc:
        raise RuntimeError(f"CSV 文件导出失败: {path}") from exc
    return path


def save_json(
    dataframe: pd.DataFrame,
    file_path: str | Path,
    encoding: str = DEFAULT_ENCODING,
    orient: str = "records",
    force_ascii: bool = False,
    **kwargs: Any,
) -> Path:
    """Save a DataFrame to JSON and create the output directory if needed.

    Args:
        dataframe: DataFrame to export.
        file_path: Output JSON path.
        encoding: File encoding, defaults to UTF-8.
        orient: JSON orientation passed to DataFrame.to_json.
        force_ascii: Whether to escape non-ASCII characters.
        **kwargs: Extra keyword arguments passed to DataFrame.to_json.

    Returns:
        The output Path.

    Raises:
        TypeError: If dataframe is not a pandas DataFrame.
        RuntimeError: If writing fails.
    """
    _require_dataframe(dataframe)
    path = _prepare_output_path(file_path)
    try:
        dataframe.to_json(
            path,
            orient=orient,
            force_ascii=force_ascii,
            indent=2,
            **kwargs,
        )
    except Exception as exc:
        raise RuntimeError(f"JSON 文件导出失败: {path}") from exc

    # pandas.to_json does not expose an encoding parameter consistently across
    # versions. Rewriting with explicit UTF-8 keeps the output contract stable.
    if encoding.lower().replace("_", "-") != DEFAULT_ENCODING:
        content = path.read_text(encoding=DEFAULT_ENCODING)
        path.write_text(content, encoding=encoding)
    return path


def save_jsonl(
    dataframe: pd.DataFrame,
    file_path: str | Path,
    encoding: str = DEFAULT_ENCODING,
    force_ascii: bool = False,
    **kwargs: Any,
) -> Path:
    """Save a DataFrame to JSONL and create the output directory if needed.

    Args:
        dataframe: DataFrame to export.
        file_path: Output JSONL path.
        encoding: File encoding, defaults to UTF-8.
        force_ascii: Whether to escape non-ASCII characters.
        **kwargs: Extra keyword arguments passed to DataFrame.to_json.

    Returns:
        The output Path.

    Raises:
        TypeError: If dataframe is not a pandas DataFrame.
        RuntimeError: If writing fails.
    """
    _require_dataframe(dataframe)
    path = _prepare_output_path(file_path)
    try:
        dataframe.to_json(
            path,
            orient="records",
            lines=True,
            force_ascii=force_ascii,
            **kwargs,
        )
    except Exception as exc:
        raise RuntimeError(f"JSONL 文件导出失败: {path}") from exc

    if encoding.lower().replace("_", "-") != DEFAULT_ENCODING:
        content = path.read_text(encoding=DEFAULT_ENCODING)
        path.write_text(content, encoding=encoding)
    return path


def _require_existing_file(file_path: str | Path) -> Path:
    """Return a Path when it exists, otherwise raise FileNotFoundError."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    return path


def _prepare_output_path(file_path: str | Path) -> Path:
    """Create the parent directory for an output file and return its Path."""
    path = Path(file_path)
    if path.parent and str(path.parent) != ".":
        ensure_directory(path.parent)
    return path


def _require_dataframe(dataframe: pd.DataFrame) -> None:
    """Validate that the input object is a pandas DataFrame."""
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe 必须是 pandas.DataFrame")
