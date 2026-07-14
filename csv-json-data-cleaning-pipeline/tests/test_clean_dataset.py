from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from clean_dataset import load_rules, process_dataframe, process_dataset  # noqa: E402
from pipeline_file_utils import load_csv  # noqa: E402


def write_pipeline_rules(path: Path, output_dir: Path | None = None) -> None:
    output_block = ""
    if output_dir is not None:
        output_block = f"""
output:
  output_dir: "{output_dir}"
  cleaned_data_name: "cleaned_data_20260616.csv"
  issue_rows_name: "issue_rows_20260616.csv"
  cleaning_summary_name: "cleaning_summary_20260616.json"
  cleaning_log_name: "cleaning_log_20260616.csv"
  dedup_report_name: "dedup_report_20260616.json"
"""

    path.write_text(
        f"""
{output_block}
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
  enabled: true
  keys:
    - ["id"]
  keep: "first"
  issue_action: "export"
null_handling:
  null_values:
    - ""
    - "N/A"
  strategies:
    - field: "source"
      action: "fill_custom"
      fill_value: "unknown"
date_rules:
  enabled: true
  date_format: "YYYY-MM-DD"
  fields:
    - field: "publish_date"
      input_formats:
        - "YYYY-MM-DD"
        - "YYYY/MM/DD"
        - "DD-MM-YYYY"
        - "YYYY.MM.DD"
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
      allow_negative: false
      invalid_action: "mark"
enum_rules:
  enabled: true
  fields:
    - field: "status"
      allowed_values:
        - "active"
        - "inactive"
custom_rules:
  enabled: true
  rules:
    - field: "score"
      rule_type: "range"
      min: 0
      max: 100
""",
        encoding="utf-8",
    )


class CleanDatasetPipelineTest(unittest.TestCase):
    def test_orchestrates_atomic_skills(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_file = tmp_path / "input.csv"
            rules_file = tmp_path / "rules.yaml"
            input_file.write_text(
                "id,title,content,publish_date,phone,amount,source,status,score\n"
                "1,标题A,内容A,2026/06/16,+86-13800138000,\"¥1,200.3\",,active,90\n"
                "1,标题A重复,内容A重复,2026/06/16,13800138000,1200.30,site_a,active,90\n"
                "2,标题B,内容B,bad-date,13A00131000,abc,site_b,unknown,999\n",
                encoding="utf-8",
            )
            write_pipeline_rules(rules_file)

            dataframe = load_csv(input_file)
            rules = load_rules(rules_file)
            processed, result = process_dataframe(dataframe, rules)

        self.assertEqual(result["input_rows"], 3)
        self.assertEqual(result["after_deduplicate_rows"], 2)
        self.assertEqual(result["duplicate_rows"], 1)
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(processed.loc[0, "source"], "unknown")
        self.assertEqual(processed.loc[0, "publish_date"], "2026-06-16")
        self.assertEqual(processed.loc[0, "phone"], "13800138000")
        self.assertEqual(processed.loc[0, "amount"], "1200.30")
        self.assertIn("_source_file", processed.columns)
        self.assertIn("_source_row", processed.columns)
        self.assertIn("_record_hash", processed.columns)
        self.assertIn("_batch_id", processed.columns)
        self.assertIn("_rule_version", processed.columns)
        self.assertGreaterEqual(result["repaired_rows"], 4)
        self.assertGreaterEqual(result["abnormal_rows"], 3)
        self.assertIn("missing-value-checker", result["atomic_reports"])
        self.assertIn("format-standardizer", result["atomic_reports"])
        self.assertIn("abnormal-value-detector", result["atomic_reports"])

    def test_missing_required_field_is_reported_by_atomic_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_file = tmp_path / "input.csv"
            rules_file = tmp_path / "rules.yaml"
            input_file.write_text(
                "id,title,publish_date,phone,amount,source,status,score\n"
                "1,标题A,2026/06/16,13800138000,1200,,active,90\n",
                encoding="utf-8",
            )
            write_pipeline_rules(rules_file)

            result = process_dataset(input_file, rules_file)

        self.assertEqual(result["missing_fields"], ["content"])
        self.assertEqual(result["duplicate_rows"], 0)

    def test_anomaly_rules_are_applied_from_rule_template_section(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            rules_file = tmp_path / "rules.yaml"
            rules_file.write_text(
                """
required_fields:
  - field: "id"
    allow_blank: false
    action: "mark"
  - field: "content"
    allow_blank: false
    action: "mark"
unique_keys:
  enabled: true
  keys:
    - ["id"]
  keep: "first"
  issue_action: "export"
null_handling:
  null_values:
    - ""
  strategies: []
date_rules:
  enabled: false
  date_format: "YYYY-MM-DD"
  fields: []
phone_rules:
  enabled: false
  phone_pattern: "^1[3-9][0-9]{9}$"
  fields: []
amount_rules:
  enabled: false
  amount_precision: 2
  fields: []
anomaly_rules:
  enabled: true
  rules:
    - field: "content"
      rule_type: "min_length"
      value: 10
      invalid_action: "mark"
    - field: "score"
      rule_type: "range"
      min: 0
      max: 100
      invalid_action: "mark"
""",
                encoding="utf-8",
            )
            dataframe = pd.DataFrame(
                [
                    {"id": "1", "content": "短", "score": 120},
                    {"id": "2", "content": "长度足够的正文内容", "score": 90},
                ]
            )

            rules = load_rules(rules_file)
            _, result = process_dataframe(dataframe, rules)
            abnormal_records = result["atomic_reports"]["abnormal-value-detector"]["abnormal_records"]

        issue_pairs = {(record["field"], record["issue_type"]) for record in abnormal_records}
        self.assertIn(("content", "regex_not_match"), issue_pairs)
        self.assertIn(("score", "out_of_range"), issue_pairs)

    def test_process_dataset_writes_orchestration_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_dir = tmp_path / "expected_outputs"
            input_file = tmp_path / "input.csv"
            rules_file = tmp_path / "rules.yaml"
            input_file.write_text(
                "id,title,content,publish_date,phone,amount,source,status,score\n"
                "1,标题A,内容A,2026/06/16,+86-13800138000,\"¥1,200.3\",,active,90\n"
                "1,标题A重复,内容A重复,2026/06/16,13800138000,1200.30,site_a,active,90\n"
                "2,标题B,内容B,bad-date,13A00131000,abc,site_b,unknown,999\n",
                encoding="utf-8",
            )
            write_pipeline_rules(rules_file, output_dir=output_dir)

            result = process_dataset(input_file, rules_file)

            issue_path = output_dir / "issue_rows_20260616.csv"
            summary_path = output_dir / "cleaning_summary_20260616.json"
            log_path = output_dir / "cleaning_log_20260616.csv"
            cleaned_path = output_dir / "cleaned_data_20260616.csv"
            dedup_path = output_dir / "dedup_report_20260616.json"

            self.assertTrue(issue_path.is_file())
            self.assertTrue(summary_path.is_file())
            self.assertTrue(log_path.is_file())
            self.assertTrue(cleaned_path.is_file())
            self.assertTrue(dedup_path.is_file())

            issue_rows = pd.read_csv(issue_path)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            dedup_report = json.loads(dedup_path.read_text(encoding="utf-8"))
            cleaning_log = pd.read_csv(log_path)
            cleaned = pd.read_csv(cleaned_path)

        self.assertEqual(result["input_rows"], 3)
        self.assertEqual(summary["input_rows"], 3)
        self.assertEqual(summary["output_rows"], 1)
        self.assertEqual(summary["removed_rows"], 2)
        self.assertEqual(summary["duplicate_rows"], 1)
        self.assertEqual(summary["duplicate_exact_rows"], 1)
        self.assertEqual(summary["quarantined_rows"], 1)
        self.assertEqual(dedup_report["total_duplicate_rows"], 1)
        self.assertEqual(set(cleaned["id"]), {1})
        self.assertIn("_source_file", cleaned.columns)
        self.assertIn("_source_row", cleaned.columns)
        self.assertIn("_record_hash", cleaned.columns)
        self.assertIn("_batch_id", cleaned.columns)
        self.assertIn("_rule_version", cleaned.columns)
        self.assertEqual(
            list(issue_rows.columns),
            ["row", "field", "value", "issue_type", "reason", "source_skill", "action", "record_id", "process_result", "raw_record"],
        )
        self.assertIn("duplicate", set(issue_rows["issue_type"]))
        self.assertIn("missing_value", set(issue_rows["issue_type"]))
        self.assertIn("standardization_failed", set(issue_rows["issue_type"]))
        self.assertIn("not_allowed", set(issue_rows["issue_type"]))
        self.assertIn("out_of_range", set(issue_rows["issue_type"]))
        self.assertEqual(summary["issue_rows"], len(issue_rows))
        self.assertEqual(list(cleaning_log.columns), ["timestamp", "rule_name", "action", "affected_rows", "result"])

    def test_similarity_deduplication_removes_near_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_file = tmp_path / "input.csv"
            rules_file = tmp_path / "rules.yaml"
            input_file.write_text(
                "id,title,content,publish_date,phone,amount,source,status,score\n"
                "1,Breaking News,内容A,2026/06/16,13800138000,100,site_a,active,90\n"
                "2,Breaking Newz,内容B,2026/06/17,13900139000,120,site_b,active,80\n"
                "3,Completely Different,内容C,2026/06/18,13600136000,130,site_c,active,85\n",
                encoding="utf-8",
            )
            rules_file.write_text(
                """
required_fields:
  - field: "id"
    allow_blank: false
    action: "mark"
  - field: "content"
    allow_blank: false
    action: "mark"
unique_keys:
  enabled: true
  keys:
    - ["id"]
  keep: "first"
  issue_action: "export"
  similarity:
    enabled: true
    fields: ["title"]
    threshold: 0.85
null_handling:
  null_values: [""]
  strategies: []
date_rules:
  enabled: false
  date_format: "YYYY-MM-DD"
  fields: []
phone_rules:
  enabled: false
  phone_pattern: "^1[3-9][0-9]{9}$"
  fields: []
amount_rules:
  enabled: false
  amount_precision: 2
  fields: []
""",
                encoding="utf-8",
            )

            dataframe = load_csv(input_file)
            rules = load_rules(rules_file)
            processed, result = process_dataframe(dataframe, rules)

        self.assertEqual(result["duplicate_similarity_rows"], 1)
        self.assertEqual(result["duplicate_rows"], 1)
        self.assertEqual(len(processed), 2)

    def test_missing_cells_are_exported_to_issue_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_dir = tmp_path / "expected_outputs"
            input_file = tmp_path / "input.csv"
            rules_file = tmp_path / "rules.yaml"
            input_file.write_text(
                "id,title,content,publish_date,phone,amount,source,status,score\n"
                "1,,内容A,2026/06/16,13800138000,1200,,active,90\n"
                "2,标题B,,2026/06/17,13900139000,88,N/A,inactive,80\n",
                encoding="utf-8",
            )
            write_pipeline_rules(rules_file, output_dir=output_dir)

            process_dataset(input_file, rules_file)
            issue_rows = pd.read_csv(output_dir / "issue_rows_20260616.csv")
            cleaned = pd.read_csv(output_dir / "cleaned_data_20260616.csv")

        missing_rows = issue_rows[issue_rows["issue_type"] == "missing_value"]
        self.assertEqual(set(missing_rows["field"]), {"title", "content", "source"})
        self.assertEqual(len(missing_rows), 4)
        self.assertTrue(cleaned.empty)


if __name__ == "__main__":
    unittest.main()
