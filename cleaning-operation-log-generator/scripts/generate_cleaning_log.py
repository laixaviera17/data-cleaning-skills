#!/usr/bin/env python3
"""Normalize and summarize cleaning operation logs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from cleaning_log_file_utils import load_csv, load_json_any, save_csv, save_json_dict


LOG_COLUMNS = [
    "timestamp",
    "step",
    "rule_name",
    "action",
    "affected_rows",
    "result",
    "message",
    "source_skill",
    "input_count",
    "output_count",
]


def normalize_log_records(records: list[dict[str, Any]], source_skill: str) -> list[dict[str, Any]]:
    """Normalize log-like dictionaries to the shared cleaning log schema."""
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            continue
        normalized.append(_normalize_record(record, source_skill))
    return normalized


def generate_cleaning_log(input_paths: list[str | Path], output_dir: str | Path) -> dict[str, Path]:
    """Generate standard cleaning logs and summary files from log outputs."""
    all_logs: list[dict[str, Any]] = []
    for input_path in input_paths:
        path = Path(input_path)
        source_skill = _infer_source_skill(path)
        all_logs.extend(_load_logs_from_file(path, source_skill))

    log_frame = pd.DataFrame(all_logs, columns=LOG_COLUMNS)
    summary = _build_summary(log_frame)
    step_summary = _step_summary_frame(log_frame)
    result_summary = _result_summary_frame(log_frame)

    output_directory = Path(output_dir)
    cleaning_log_path = output_directory / "cleaning_log.csv"
    summary_path = output_directory / "cleaning_log_summary.json"
    step_summary_path = output_directory / "step_summary.csv"
    result_summary_path = output_directory / "result_summary.csv"

    save_csv(log_frame, cleaning_log_path)
    save_json_dict(summary, summary_path)
    save_csv(step_summary, step_summary_path)
    save_csv(result_summary, result_summary_path)

    return {
        "cleaning_log": cleaning_log_path,
        "cleaning_log_summary": summary_path,
        "step_summary": step_summary_path,
        "result_summary": result_summary_path,
    }


def _load_logs_from_file(path: Path, source_skill: str) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = load_csv(path)
        return normalize_log_records(frame.to_dict(orient="records"), source_skill)
    if suffix == ".json":
        data = load_json_any(path)
        if isinstance(data, list):
            return normalize_log_records(data, source_skill)
        if isinstance(data, dict):
            for key in ("cleaning_log", "logs", "records"):
                if isinstance(data.get(key), list):
                    return normalize_log_records(data[key], source_skill)
            return normalize_log_records([], source_skill)
        raise ValueError(f"JSON 日志文件根节点必须是对象或数组: {path}")
    raise ValueError(f"不支持的日志文件类型: {suffix}; 支持类型: .csv, .json")


def _normalize_record(record: dict[str, Any], default_source_skill: str) -> dict[str, Any]:
    rule_name = _clean_value(_first_present(record, ["rule_name", "step", "name"]))
    step = _clean_value(_first_present(record, ["step", "rule_name", "name"]))
    return {
        "timestamp": _clean_value(_first_present(record, ["timestamp", "time", "created_at"])),
        "step": step,
        "rule_name": rule_name,
        "action": _clean_value(_first_present(record, ["action", "operation"])),
        "affected_rows": _to_int(_first_present(record, ["affected_rows", "affected_count", "rows"])),
        "result": _clean_value(_first_present(record, ["result", "status"])),
        "message": _clean_value(_first_present(record, ["message", "detail", "reason"])),
        "source_skill": _clean_value(_first_present(record, ["source_skill"])) or default_source_skill,
        "input_count": _clean_value(_first_present(record, ["input_count", "input_rows"])),
        "output_count": _clean_value(_first_present(record, ["output_count", "output_rows"])),
    }


def _build_summary(log_frame: pd.DataFrame) -> dict[str, Any]:
    if log_frame.empty:
        return {
            "total_steps": 0,
            "source_count": 0,
            "success_steps": 0,
            "warning_steps": 0,
            "failed_steps": 0,
            "total_affected_rows": 0,
        }
    result_values = log_frame["result"].fillna("").astype(str).str.lower()
    return {
        "total_steps": len(log_frame),
        "source_count": int(log_frame["source_skill"].replace("", pd.NA).dropna().nunique()),
        "success_steps": int((result_values == "success").sum()),
        "warning_steps": int((result_values == "warning").sum()),
        "failed_steps": int(result_values.isin(["failed", "fail", "error"]).sum()),
        "total_affected_rows": int(pd.to_numeric(log_frame["affected_rows"], errors="coerce").fillna(0).sum()),
    }


def _step_summary_frame(log_frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["step", "rule_name", "step_count", "total_affected_rows"]
    if log_frame.empty:
        return pd.DataFrame(columns=columns)
    frame = log_frame.copy()
    frame["affected_rows"] = pd.to_numeric(frame["affected_rows"], errors="coerce").fillna(0).astype(int)
    return (
        frame.groupby(["step", "rule_name"], dropna=False)["affected_rows"]
        .agg(step_count="count", total_affected_rows="sum")
        .reset_index()[columns]
    )


def _result_summary_frame(log_frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["result", "step_count", "total_affected_rows"]
    if log_frame.empty:
        return pd.DataFrame(columns=columns)
    frame = log_frame.copy()
    frame["affected_rows"] = pd.to_numeric(frame["affected_rows"], errors="coerce").fillna(0).astype(int)
    return (
        frame.groupby("result", dropna=False)["affected_rows"]
        .agg(step_count="count", total_affected_rows="sum")
        .reset_index()[columns]
    )


def _infer_source_skill(path: Path) -> str:
    name = path.name.lower()
    if "cleaning_log" in name:
        return "csv-json-data-cleaning-pipeline"
    if "mapping" in name:
        return "table-field-mapping-converter"
    if "dictionary" in name:
        return "field-dictionary-value-validator"
    return path.stem


def _first_present(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return ""


def _clean_value(value: Any) -> Any:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value


def _to_int(value: Any) -> int:
    value = _clean_value(value)
    if value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def main(argv: list[str]) -> int:
    """Run cleaning log generation from the command line."""
    if len(argv) < 3:
        print(
            json.dumps(
                {"error": "用法: python scripts/generate_cleaning_log.py input_log1.csv [input_log2.json ...] output_dir"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    try:
        outputs = generate_cleaning_log(argv[1:-1], argv[-1])
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({key: str(value) for key, value in outputs.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
