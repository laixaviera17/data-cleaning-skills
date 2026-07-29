#!/usr/bin/env python3
"""Run a small, reproducible walkthrough of the existing data-quality toolchain."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_INPUT = ROOT / "csv-json-data-cleaning-pipeline" / "examples" / "manual_demo" / "input_dirty.csv"
PUBLIC_RULES = ROOT / "csv-json-data-cleaning-pipeline" / "examples" / "manual_demo" / "rules.yaml"
DEFAULT_OUTPUT = ROOT / "demo" / "output"
SCRIPT_DIRS = [
    ROOT / "csv-json-data-cleaning-pipeline" / "scripts",
    ROOT / "structured-issue-list-generator" / "scripts",
    ROOT / "cleaning-operation-log-generator" / "scripts",
    ROOT / "dataset-before-after-diff-comparator" / "scripts",
    ROOT / "dataset-documentation-generator" / "scripts",
    ROOT / "dataset-catalog-metadata-generator" / "scripts",
    ROOT / "cleaned-dataset-delivery-packager" / "scripts",
]


def _load_existing_tools() -> dict[str, Any]:
    """Import the stable public functions already used by workspace QA."""
    for script_dir in reversed(SCRIPT_DIRS):
        sys.path.insert(0, str(script_dir))

    from clean_dataset import process_dataset
    from compare_datasets import compare_dataset_files
    from generate_catalog_metadata import generate_catalog_metadata
    from generate_cleaning_log import generate_cleaning_log
    from generate_dataset_documentation import generate_dataset_documentation
    from generate_issue_list import generate_issue_list
    from package_cleaned_dataset import package_dataset

    return {
        "process_dataset": process_dataset,
        "compare_dataset_files": compare_dataset_files,
        "generate_catalog_metadata": generate_catalog_metadata,
        "generate_cleaning_log": generate_cleaning_log,
        "generate_dataset_documentation": generate_dataset_documentation,
        "generate_issue_list": generate_issue_list,
        "package_dataset": package_dataset,
    }


def _prepare_output_directory(output_dir: Path) -> None:
    resolved = output_dir.resolve()
    if resolved == ROOT:
        raise ValueError("演示输出目录不能是仓库根目录")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _write_runtime_rules(output_dir: Path) -> Path:
    """Reuse the public manual-demo rules while redirecting only generated outputs."""
    rules = yaml.safe_load(PUBLIC_RULES.read_text(encoding="utf-8"))
    if not isinstance(rules, dict):
        raise ValueError("公开演示规则必须是 YAML 对象")
    rules["output"] = {
        "output_dir": str(output_dir),
        "cleaned_data_name": "cleaned_data.csv",
        "issue_rows_name": "issue_rows.csv",
        "cleaning_summary_name": "cleaning_summary.json",
        "cleaning_log_name": "cleaning_log.csv",
        "dedup_report_name": "dedup_report.json",
    }
    runtime_rules = output_dir / ".runtime_rules.yaml"
    runtime_rules.write_text(yaml.safe_dump(rules, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return runtime_rules


def _write_metadata_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "dataset_name": "recruiter_demo_news_dataset",
                "description": "Repository-local mock data used to demonstrate the existing data-quality toolchain.",
                "version": "1.0.0",
                "source": "csv-json-data-cleaning-pipeline/examples/manual_demo",
                "license": "MIT",
                "authorization_type": "public-demo",
                "tags": ["demo", "data-quality", "csv"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def run_demo(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Generate a deterministic-path demo with data, reports, and a delivery manifest."""
    output_dir = output_dir.resolve()
    _prepare_output_directory(output_dir)
    tools = _load_existing_tools()
    runtime_rules = _write_runtime_rules(output_dir)

    pipeline_report = tools["process_dataset"](PUBLIC_INPUT, runtime_rules)
    cleaned_data = output_dir / "cleaned_data.csv"
    issue_rows = output_dir / "issue_rows.csv"
    cleaning_log = output_dir / "cleaning_log.csv"
    cleaning_summary = output_dir / "cleaning_summary.json"
    pipeline_summary = json.loads(cleaning_summary.read_text(encoding="utf-8"))
    normalized_dir = output_dir / "normalized_reports"
    diff_dir = output_dir / "before_after_diff"
    docs_dir = output_dir / "documentation"
    metadata_dir = output_dir / "metadata"
    delivery_dir = output_dir / "delivery"

    issue_outputs = tools["generate_issue_list"]([issue_rows], normalized_dir)
    log_outputs = tools["generate_cleaning_log"]([cleaning_log], normalized_dir)
    # The public mock data intentionally repeats ``id`` to demonstrate deduplication.
    # The comparator requires unique keys on both sides, so use a stable composite
    # content key for the before/after report without changing the pipeline's id rule.
    diff_outputs = tools["compare_dataset_files"](PUBLIC_INPUT, cleaned_data, ["id", "title", "content"], diff_dir)
    documentation = tools["generate_dataset_documentation"](
        cleaned_data,
        docs_dir,
        dataset_name="recruiter_demo_news_dataset",
        reports=[cleaning_summary, issue_outputs["issue_rows"], diff_outputs["diff_summary"]],
    )
    metadata_config = output_dir / ".metadata_config.json"
    _write_metadata_config(metadata_config)
    metadata = tools["generate_catalog_metadata"](
        cleaned_data,
        metadata_dir,
        config_path=metadata_config,
        artifacts=[documentation["documentation_path"], issue_outputs["issue_rows"], log_outputs["cleaning_log"]],
    )
    package = tools["package_dataset"](
        cleaned_data,
        delivery_dir,
        artifacts=[
            cleaning_summary,
            issue_outputs["issue_rows"],
            log_outputs["cleaning_log"],
            diff_outputs["diff_summary"],
            documentation["documentation_path"],
            metadata["metadata_path"],
        ],
        dataset_name="recruiter_demo_news_dataset",
    )

    delivery_manifest = output_dir / "delivery_manifest.json"
    shutil.copy2(package["manifest_path"], delivery_manifest)
    summary = {
        "input_rows": pipeline_summary["input_rows"],
        "output_rows": pipeline_summary["output_rows"],
        "issue_rows": pipeline_summary["issue_rows"],
        "duplicate_rows": pipeline_summary["duplicate_rows"],
        "quarantined_rows": pipeline_summary["quarantined_rows"],
        "repaired_rows": pipeline_summary["repaired_rows"],
        "abnormal_rows": pipeline_summary["abnormal_rows"],
        "reused_modules": [
            "csv-json-data-cleaning-pipeline",
            "missing-value-checker",
            "format-standardizer",
            "abnormal-value-detector",
            "structured-issue-list-generator",
            "cleaning-operation-log-generator",
            "dataset-before-after-diff-comparator",
            "dataset-documentation-generator",
            "dataset-catalog-metadata-generator",
            "cleaned-dataset-delivery-packager",
        ],
        "artifacts": {
            "cleaned_data": str(cleaned_data.relative_to(output_dir)),
            "issues": str(issue_rows.relative_to(output_dir)),
            "cleaning_log": str(cleaning_log.relative_to(output_dir)),
            "delivery_manifest": str(delivery_manifest.relative_to(output_dir)),
            "delivery_package": str(Path(package["archive_path"]).relative_to(output_dir)),
        },
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_dir": output_dir, "summary_path": summary_path, "summary": summary}


def main() -> int:
    result = run_demo()
    print(json.dumps({"output_dir": str(result["output_dir"]), **result["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
