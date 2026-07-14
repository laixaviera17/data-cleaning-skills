from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
SCRIPT_DIRS = [
    WORKSPACE / "csv-json-data-cleaning-pipeline" / "scripts",
    WORKSPACE / "structured-issue-list-generator" / "scripts",
    WORKSPACE / "cleaning-operation-log-generator" / "scripts",
    WORKSPACE / "dataset-before-after-diff-comparator" / "scripts",
    WORKSPACE / "dataset-documentation-generator" / "scripts",
    WORKSPACE / "dataset-catalog-metadata-generator" / "scripts",
    WORKSPACE / "cleaned-dataset-delivery-packager" / "scripts",
]
for script_dir in reversed(SCRIPT_DIRS):
    sys.path.insert(0, str(script_dir))

from clean_dataset import process_dataset  # noqa: E402
from compare_datasets import compare_dataset_files  # noqa: E402
from generate_catalog_metadata import generate_catalog_metadata  # noqa: E402
from generate_cleaning_log import generate_cleaning_log  # noqa: E402
from generate_dataset_documentation import generate_dataset_documentation  # noqa: E402
from generate_issue_list import generate_issue_list  # noqa: E402
from package_cleaned_dataset import package_dataset  # noqa: E402


class WorkspaceEndToEndTest(unittest.TestCase):
    def test_raw_csv_to_delivery_package(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_data = root / "raw.csv"
            pipeline_output = root / "pipeline"
            normalized_output = root / "normalized"
            diff_output = root / "diff"
            docs_output = root / "docs"
            metadata_output = root / "metadata"
            package_output = root / "package"
            rules = root / "rules.yaml"
            metadata_config = root / "metadata_config.json"

            raw_data.write_text(
                "id,title,content,publish_date,source,phone,amount,status,score\n"
                "1,Alpha,hello world,2026/06/01,,13800138000,$12.30,valid,90\n"
                "2,Beta,second row,2026-06-02,portal,12345,abc,invalid,101\n",
                encoding="utf-8",
            )
            rules.write_text(
                f"""
output:
  output_dir: "{pipeline_output}"
  cleaned_data_name: "cleaned_data.csv"
  issue_rows_name: "issue_rows.csv"
  cleaning_summary_name: "cleaning_summary.json"
  cleaning_log_name: "cleaning_log.csv"
required_fields:
  - field: "id"
    allow_blank: false
    action: "mark"
  - field: "title"
    allow_blank: false
    action: "mark"
  - field: "content"
    allow_blank: false
    action: "mark"
unique_keys:
  keys:
    - ["id"]
null_handling:
  null_values:
    - ""
    - "N/A"
  strategies:
    - field: "source"
      action: "fill"
      fill_value: "unknown"
date_rules:
  enabled: true
  target_format: "YYYY-MM-DD"
  fields:
    - field: "publish_date"
      input_formats:
        - "YYYY-MM-DD"
        - "YYYY/MM/DD"
      invalid_action: "mark"
phone_rules:
  enabled: true
  phone_pattern: "^1[3-9][0-9]{{9}}$"
  fields:
    - field: "phone"
      invalid_action: "mark"
amount_rules:
  enabled: true
  amount_precision: 2
  fields:
    - field: "amount"
      decimal_places: 2
      remove_currency_symbol: true
      allow_negative: false
      invalid_action: "mark"
enum_rules:
  fields:
    - field: "status"
      allowed_values:
        - "valid"
        - "invalid"
      invalid_action: "mark"
""",
                encoding="utf-8",
            )
            metadata_config.write_text(
                json.dumps(
                    {
                        "dataset_name": "workspace_e2e_dataset",
                        "description": "End-to-end QA dataset.",
                        "version": "1.0.0",
                        "source": "qa",
                        "license": "internal-use",
                        "authorization_type": "controlled",
                        "tags": ["qa", "e2e"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            pipeline_report = process_dataset(raw_data, rules)
            cleaned_data = pipeline_output / "cleaned_data.csv"
            issue_rows = pipeline_output / "issue_rows.csv"
            cleaning_log = pipeline_output / "cleaning_log.csv"
            summary = pipeline_output / "cleaning_summary.json"

            issue_outputs = generate_issue_list([issue_rows], normalized_output)
            log_outputs = generate_cleaning_log([cleaning_log], normalized_output)
            diff_outputs = compare_dataset_files(raw_data, cleaned_data, ["id"], diff_output)
            doc_result = generate_dataset_documentation(
                cleaned_data,
                docs_output,
                dataset_name="workspace_e2e_dataset",
                reports=[summary, issue_outputs["issue_rows"], diff_outputs["diff_summary"]],
            )
            metadata_result = generate_catalog_metadata(
                cleaned_data,
                metadata_output,
                config_path=metadata_config,
                artifacts=[doc_result["documentation_path"], issue_outputs["issue_rows"], log_outputs["cleaning_log"]],
            )
            package_result = package_dataset(
                cleaned_data,
                package_output,
                artifacts=[
                    summary,
                    issue_outputs["issue_rows"],
                    log_outputs["cleaning_log"],
                    diff_outputs["diff_summary"],
                    doc_result["documentation_path"],
                    metadata_result["metadata_path"],
                ],
                dataset_name="workspace_e2e_dataset",
            )

            manifest = package_result["manifest"]
            archive_path = Path(package_result["archive_path"])

            self.assertEqual(pipeline_report["input_rows"], 2)
            self.assertTrue(cleaned_data.exists())
            self.assertTrue(Path(doc_result["documentation_path"]).exists())
            self.assertTrue(Path(metadata_result["metadata_path"]).exists())
            self.assertTrue(metadata_result["metadata"]["required_field_status"]["valid"])
            self.assertGreaterEqual(manifest["file_count"], 7)
            self.assertTrue(archive_path.exists())
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
            self.assertIn("data/cleaned_data.csv", names)
            self.assertIn("manifest.json", names)

    def test_release_schema_files_exist(self):
        schema_dir = WORKSPACE / "qa" / "schemas"
        for name in [
            "delivery_manifest.schema.json",
            "catalog_metadata.schema.json",
            "issue_rows.schema.json",
            "cleaning_log.schema.json",
        ]:
            self.assertTrue((schema_dir / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
