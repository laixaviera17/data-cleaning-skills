from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_cleaning_skills import ContractValidationError, validate_instance

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def test_manifest_contract_rejects_invalid_hash_and_timestamp():
    invalid_manifest = {
        "dataset_name": "sample",
        "generated_at": "not-a-timestamp",
        "package_layout": ["data/"],
        "file_count": 1,
        "files": [
            {
                "path": "data/sample.csv",
                "role": "data",
                "size_bytes": 10,
                "sha256": "not-sha256",
                "source_path": "sample.csv",
            }
        ],
    }

    with pytest.raises(ContractValidationError) as error:
        validate_instance(invalid_manifest, SCHEMA_DIR / "delivery_manifest.schema.json")

    message = str(error.value)
    assert "not-a-timestamp" in message
    assert "not-sha256" in message


def test_issue_contract_rejects_row_without_issue_type():
    contract = {
        "columns": ["row", "field", "value", "issue_type", "reason"],
        "rows": [{"row": 1, "field": "amount", "value": "abc", "reason": "invalid amount"}],
    }

    with pytest.raises(ContractValidationError, match="issue_type"):
        validate_instance(contract, SCHEMA_DIR / "issue_rows.schema.json")


def test_all_published_schemas_are_valid_draft_2020_12_documents():
    from jsonschema import Draft202012Validator

    for schema_path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        Draft202012Validator.check_schema(json.loads(schema_path.read_text(encoding="utf-8")))
