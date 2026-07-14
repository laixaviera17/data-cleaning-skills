#!/usr/bin/env python3
"""Generate machine-readable catalog metadata for a cleaned dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


CATALOG_STANDARD = "NDI-TR-2025-06"
NDI_FIELD_MAPPING = {
    "dataset_identifier": "dataset_id",
    "dataset_title": "dataset_name",
    "abstract": "description",
    "version": "version",
    "data_source": "source",
    "license": "license",
    "authorization_type": "authorization_type",
    "keywords": "tags",
    "publication_time": "generated_at",
    "data_format": "format",
    "record_count": "record_count",
    "field_count": "field_count",
    "schema_description": "schema",
    "file_inventory": "files",
}
REQUIRED_METADATA_FIELDS = [
    "dataset_id",
    "dataset_name",
    "description",
    "version",
    "source",
    "license",
    "authorization_type",
    "generated_at",
    "format",
    "record_count",
    "field_count",
    "schema",
    "files",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def build_schema(records: list[dict]) -> list[dict]:
    fields: list[str] = []
    for record in records:
        for field in record:
            if field not in fields:
                fields.append(field)
    schema = []
    for field in fields:
        values = [record.get(field, "") for record in records]
        schema.append({
            "name": field,
            "type": infer_type(values),
            "missing_cells": sum(1 for value in values if value in ("", None)),
        })
    return schema


def read_config(config_path: str | Path | None) -> dict:
    if not config_path:
        return {}
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    if path.suffix.lower() != ".json":
        raise ValueError("metadata config must be a JSON file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("metadata config must be a JSON object")
    return value


def artifact_record(path: str | Path) -> dict:
    artifact = Path(path).expanduser().resolve()
    if not artifact.exists():
        raise FileNotFoundError(f"artifact file not found: {artifact}")
    return {
        "name": artifact.name,
        "path": str(artifact),
        "size_bytes": artifact.stat().st_size,
        "sha256": sha256_file(artifact),
    }


def validate_required_metadata(metadata: dict) -> dict:
    missing_fields = []
    for field in REQUIRED_METADATA_FIELDS:
        value = metadata.get(field)
        if value in ("", None, [], {}):
            missing_fields.append(field)
    return {
        "standard": CATALOG_STANDARD,
        "required_fields": REQUIRED_METADATA_FIELDS,
        "missing_fields": missing_fields,
        "valid": not missing_fields,
    }


def generate_catalog_metadata(
    data_path: str | Path,
    output_dir: str | Path,
    dataset_name: str | None = None,
    config_path: str | Path | None = None,
    artifacts: list[str | Path] | None = None,
) -> dict:
    data = Path(data_path).expanduser().resolve()
    records = load_records(data)
    config = read_config(config_path)
    name = dataset_name or config.get("dataset_name") or data.stem
    generated_at = datetime.now(timezone.utc).isoformat()
    dataset_id = config.get("dataset_id") or hashlib.sha256(f"{name}:{data}:{generated_at}".encode("utf-8")).hexdigest()[:16]

    metadata = {
        "catalog_standard": CATALOG_STANDARD,
        "dataset_id": dataset_id,
        "dataset_name": name,
        "description": config.get("description", ""),
        "version": config.get("version", "1.0.0"),
        "source": config.get("source", ""),
        "license": config.get("license", ""),
        "authorization_type": config.get("authorization_type", ""),
        "tags": config.get("tags", []),
        "generated_at": generated_at,
        "format": data.suffix.lower().lstrip("."),
        "record_count": len(records),
        "field_count": len(build_schema(records)),
        "schema": build_schema(records),
        "files": [
            {
                "name": data.name,
                "path": str(data),
                "role": "primary_data",
                "size_bytes": data.stat().st_size,
                "sha256": sha256_file(data),
            }
        ],
        "artifacts": [artifact_record(path) for path in artifacts or []],
        "lineage": {
            "stage": "cleaned_dataset_delivery",
            "notes": config.get("lineage_notes", ""),
        },
    }
    metadata["standard_field_mapping"] = NDI_FIELD_MAPPING
    metadata["required_field_status"] = validate_required_metadata(metadata)

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    metadata_path = output / "catalog_metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"metadata_path": str(metadata_path), "metadata": metadata}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate catalog metadata for a cleaned dataset.")
    parser.add_argument("data_path")
    parser.add_argument("output_dir")
    parser.add_argument("--dataset-name")
    parser.add_argument("--config")
    parser.add_argument("--artifact", action="append", default=[])
    args = parser.parse_args()
    result = generate_catalog_metadata(args.data_path, args.output_dir, args.dataset_name, args.config, args.artifact)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
