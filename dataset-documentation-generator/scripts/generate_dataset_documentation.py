#!/usr/bin/env python3
"""Generate human-readable dataset documentation."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load_records(path: str | Path) -> list[dict]:
    data_path = Path(path).expanduser().resolve()
    if not data_path.exists():
        raise FileNotFoundError(f"data file not found: {data_path}")
    suffix = data_path.suffix.lower()
    if suffix == ".csv":
        with data_path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    if suffix == ".jsonl":
        records = []
        with data_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("JSONL rows must be objects")
                    records.append(value)
        return records
    if suffix == ".json":
        value = json.loads(data_path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            for key in ("records", "data", "items"):
                if isinstance(value.get(key), list):
                    return [row for row in value[key] if isinstance(row, dict)]
            return [value]
    raise ValueError(f"unsupported data format: {data_path.suffix}")


def infer_type(values: list[object]) -> str:
    non_empty = [value for value in values if value not in ("", None)]
    if not non_empty:
        return "empty"
    if all(str(value).lower() in {"true", "false"} for value in non_empty):
        return "boolean"
    try:
        for value in non_empty:
            int(str(value))
        return "integer"
    except ValueError:
        pass
    try:
        for value in non_empty:
            float(str(value))
        return "number"
    except ValueError:
        return "string"


def schema_summary(records: list[dict]) -> list[dict]:
    fields: list[str] = []
    for record in records:
        for field in record:
            if field not in fields:
                fields.append(field)
    summary = []
    for field in fields:
        values = [record.get(field, "") for record in records]
        missing = sum(1 for value in values if value in ("", None))
        summary.append({"field": field, "type": infer_type(values), "missing_cells": missing})
    return summary


def summarize_report(path: str | Path) -> dict:
    report_path = Path(path).expanduser().resolve()
    if not report_path.exists():
        raise FileNotFoundError(f"report file not found: {report_path}")
    suffix = report_path.suffix.lower()
    if suffix == ".json":
        value = json.loads(report_path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            simple = {
                key: val
                for key, val in value.items()
                if isinstance(val, (str, int, float, bool)) or val is None
            }
            return {"path": str(report_path), "type": "json", "summary": simple}
    if suffix == ".csv":
        with report_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
            fields = rows[0].keys() if rows else []
        return {"path": str(report_path), "type": "csv", "rows": len(rows), "fields": list(fields)}
    return {"path": str(report_path), "type": suffix.lstrip(".") or "unknown"}


def generate_markdown(dataset_name: str, data_path: Path, records: list[dict], reports: list[dict]) -> str:
    fields = schema_summary(records)
    lines = [
        f"# {dataset_name} 数据集说明文档",
        "",
        "## 基本信息",
        "",
        f"- 数据集名称：{dataset_name}",
        f"- 数据文件：{data_path.name}",
        f"- 生成时间：{datetime.now(timezone.utc).isoformat()}",
        f"- 记录数：{len(records)}",
        f"- 字段数：{len(fields)}",
        "",
        "## 内容特征",
        "",
        "| 字段 | 推断类型 | 缺失单元格 |",
        "|---|---|---|",
    ]
    for field in fields:
        lines.append(f"| {field['field']} | {field['type']} | {field['missing_cells']} |")

    lines.extend(["", "## 建设过程与质量摘要", ""])
    if reports:
        for report in reports:
            lines.append(f"### {Path(report['path']).name}")
            if report.get("type") == "json":
                summary = report.get("summary", {})
                if summary:
                    for key, value in summary.items():
                        lines.append(f"- {key}: {value}")
                else:
                    lines.append("- 已关联 JSON 报告，未发现简单摘要字段。")
            elif report.get("type") == "csv":
                lines.append(f"- 记录数：{report.get('rows', 0)}")
                lines.append(f"- 字段：{', '.join(report.get('fields', []))}")
            else:
                lines.append(f"- 已关联附件类型：{report.get('type')}")
            lines.append("")
    else:
        lines.append("未提供清洗日志、质量报告、问题清单或差异摘要附件。")
        lines.append("")

    field_type_count = Counter(field["type"] for field in fields)
    lines.extend([
        "## 应用说明",
        "",
        "该文档用于交付阶段说明数据集基本信息、内容特征和建设过程摘要。实际使用时应结合授权协议、目录元数据和质量评测报告判断适用范围。",
        "",
        "## 字段类型统计",
        "",
    ])
    for field_type, count in sorted(field_type_count.items()):
        lines.append(f"- {field_type}: {count}")
    lines.append("")
    return "\n".join(lines)


def generate_dataset_documentation(
    data_path: str | Path,
    output_dir: str | Path,
    dataset_name: str | None = None,
    reports: list[str | Path] | None = None,
) -> dict:
    data = Path(data_path).expanduser().resolve()
    records = load_records(data)
    report_summaries = [summarize_report(path) for path in reports or []]
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = dataset_name or data.stem
    markdown = generate_markdown(name, data, records, report_summaries)
    readme_path = output / "dataset_readme.md"
    readme_path.write_text(markdown, encoding="utf-8")
    return {
        "documentation_path": str(readme_path),
        "dataset_name": name,
        "row_count": len(records),
        "field_count": len(schema_summary(records)),
        "report_count": len(report_summaries),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate dataset README documentation.")
    parser.add_argument("data_path")
    parser.add_argument("output_dir")
    parser.add_argument("--dataset-name")
    parser.add_argument("--report", action="append", default=[])
    args = parser.parse_args()
    result = generate_dataset_documentation(args.data_path, args.output_dir, args.dataset_name, args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
