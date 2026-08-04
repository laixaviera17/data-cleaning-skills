"""JSON Schema validation for published JSON and CSV artifact contracts."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker

from .errors import ContractValidationError, SkillConfigurationError
from .workflow import load_workflow_tools


def validate_pipeline_rules(
    rules: Mapping[str, Any],
    *,
    validator: Callable[[Any], Mapping[str, Any]] | None = None,
) -> None:
    """Validate Pipeline rules through the shared legacy-compatible validator."""
    validate = validator or load_workflow_tools()["validate_rules"]
    result = validate(dict(rules))
    if result.get("valid", False):
        return
    errors = result.get("errors", ["unknown rule validation error"])
    raise SkillConfigurationError("规则校验失败: " + "; ".join(str(error) for error in errors))


def validate_instance(instance: Any, schema_path: str | Path) -> None:
    """Validate an in-memory value and raise one domain error with all findings."""
    path = Path(schema_path)
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if not errors:
        return

    findings = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        findings.append(f"{location}: {error.message}")
    raise ContractValidationError(f"{path.name} 校验失败: " + "; ".join(findings))


def validate_json_contract(artifact_path: str | Path, schema_path: str | Path) -> None:
    """Validate one JSON artifact against a Draft 2020-12 schema."""
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    validate_instance(artifact, schema_path)


def validate_csv_contract(artifact_path: str | Path, schema_path: str | Path) -> None:
    """Validate CSV columns and normalized row values against a JSON Schema."""
    frame = pd.read_csv(artifact_path, keep_default_na=False)
    rows = json.loads(frame.to_json(orient="records", force_ascii=False))
    validate_instance({"columns": list(frame.columns), "rows": rows}, schema_path)
