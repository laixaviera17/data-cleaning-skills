"""Package-level access to deterministic end-to-end compatibility tools."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .registry import LegacyModuleSpec, _discover_repository_root, _load_legacy_skill


def _workflow_specs(root: Path) -> dict[str, tuple[LegacyModuleSpec, str]]:
    """Build checkout-backed workflow paths lazily."""
    pipeline_spec = LegacyModuleSpec(
        root / "csv-json-data-cleaning-pipeline" / "scripts" / "clean_dataset.py",
        (
            ("simple_yaml", root / "qa" / "shared" / "simple_yaml.py"),
            (
                "pipeline_file_utils",
                root / "csv-json-data-cleaning-pipeline" / "scripts" / "pipeline_file_utils.py",
            ),
            ("validate_rules", root / "csv-json-data-cleaning-pipeline" / "scripts" / "validate_rules.py"),
        ),
    )
    return {
        "process_dataframe": (pipeline_spec, "process_dataframe"),
        "process_dataset": (pipeline_spec, "process_dataset"),
        "validate_rules": (pipeline_spec, "validate_rules"),
        "compare_dataset_files": (
            LegacyModuleSpec(
                root / "dataset-before-after-diff-comparator" / "scripts" / "compare_datasets.py",
                (
                    (
                        "dataset_diff_file_utils",
                        root / "dataset-before-after-diff-comparator" / "scripts" / "dataset_diff_file_utils.py",
                    ),
                ),
            ),
            "compare_dataset_files",
        ),
        "generate_catalog_metadata": (
            LegacyModuleSpec(root / "dataset-catalog-metadata-generator" / "scripts" / "generate_catalog_metadata.py"),
            "generate_catalog_metadata",
        ),
        "generate_cleaning_log": (
            LegacyModuleSpec(
                root / "cleaning-operation-log-generator" / "scripts" / "generate_cleaning_log.py",
                (
                    (
                        "cleaning_log_file_utils",
                        root / "cleaning-operation-log-generator" / "scripts" / "cleaning_log_file_utils.py",
                    ),
                ),
            ),
            "generate_cleaning_log",
        ),
        "generate_dataset_documentation": (
            LegacyModuleSpec(
                root / "dataset-documentation-generator" / "scripts" / "generate_dataset_documentation.py"
            ),
            "generate_dataset_documentation",
        ),
        "generate_issue_list": (
            LegacyModuleSpec(
                root / "structured-issue-list-generator" / "scripts" / "generate_issue_list.py",
                (
                    (
                        "issue_list_file_utils",
                        root / "structured-issue-list-generator" / "scripts" / "issue_list_file_utils.py",
                    ),
                ),
            ),
            "generate_issue_list",
        ),
        "package_dataset": (
            LegacyModuleSpec(root / "cleaned-dataset-delivery-packager" / "scripts" / "package_cleaned_dataset.py"),
            "package_dataset",
        ),
    }


def load_workflow_tools() -> dict[str, Callable[..., Any]]:
    """Return checkout-backed callables without mutating ``sys.path``."""
    tools: dict[str, Callable[..., Any]] = {}
    for public_name, (spec, function_name) in _workflow_specs(_discover_repository_root()).items():
        module = _load_legacy_skill(f"workflow-{public_name}", spec, required_callable=None)
        function = getattr(module, function_name, None)
        if not callable(function):
            raise ImportError(f"Workflow tool does not expose {function_name}: {spec.script}")
        tools[public_name] = function
    return tools
