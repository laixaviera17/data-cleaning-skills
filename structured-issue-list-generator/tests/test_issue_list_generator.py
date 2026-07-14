import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from generate_issue_list import generate_issue_list, normalize_issue_records  # noqa: E402


class StructuredIssueListGeneratorTest(unittest.TestCase):
    def test_standard_issue_rows_are_preserved_with_missing_columns_filled(self):
        records = [
            {
                "row": 1,
                "field": "age",
                "value": 999,
                "issue_type": "out_of_range",
                "reason": "age out of range",
                "source_skill": "abnormal-value-detector",
                "action": "detect",
            }
        ]

        normalized = normalize_issue_records(records, "fallback")

        self.assertEqual(normalized[0]["field"], "age")
        self.assertEqual(normalized[0]["record_id"], "")
        self.assertEqual(normalized[0]["source_skill"], "abnormal-value-detector")

    def test_mapping_dictionary_and_abnormal_records_are_normalized(self):
        records = [
            {"source_field": "country", "target_field": "country_code", "issue_type": "missing_required_source_field", "reason": "missing", "action": "fill_default"},
            {"field_name": "status", "value": "禁用", "issue_type": "disallowed_dictionary_value", "reason": "not allowed", "action": "report"},
            {"row": 3, "field": "score", "value": 120, "issue_type": "out_of_range", "reason": "out_of_range", "action": "detect"},
        ]

        normalized = normalize_issue_records(records, "mixed-source")

        self.assertEqual(normalized[0]["field"], "country")
        self.assertIn("target_field", normalized[0]["raw_record"])
        self.assertEqual(normalized[1]["field"], "status")
        self.assertEqual(normalized[2]["field"], "score")

    def test_generate_issue_list_merges_multiple_inputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            issue_rows = tmp_path / "issue_rows.csv"
            mapping_issues = tmp_path / "mapping_issues.csv"
            dictionary_issues = tmp_path / "dictionary_issues.csv"
            abnormal_json = tmp_path / "abnormal_records.json"
            output_dir = tmp_path / "out"

            issue_rows.write_text(
                "row,field,value,issue_type,reason,source_skill,action,record_id,process_result,raw_record\n"
                "1,age,999,out_of_range,out_of_range,abnormal-value-detector,detect,,,\n",
                encoding="utf-8",
            )
            mapping_issues.write_text(
                "source_field,target_field,issue_type,reason,action\n"
                "country,country_code,missing_required_source_field,源字段不存在,fill_default\n",
                encoding="utf-8",
            )
            dictionary_issues.write_text(
                "row,field_name,value,issue_type,reason,action,remark\n"
                "2,status,禁用,disallowed_dictionary_value,不允许,report,不允许状态\n",
                encoding="utf-8",
            )
            abnormal_json.write_text(
                json.dumps(
                    {
                        "abnormal_records": [
                            {
                                "row": 3,
                                "field": "score",
                                "value": 120,
                                "issue_type": "out_of_range",
                                "reason": "out_of_range",
                                "source_skill": "abnormal-value-detector",
                                "action": "detect",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            outputs = generate_issue_list([issue_rows, mapping_issues, dictionary_issues, abnormal_json], output_dir)
            issue_frame = pd.read_csv(outputs["issue_rows"], keep_default_na=False)
            summary = json.loads(outputs["issue_summary"].read_text(encoding="utf-8"))
            type_summary = pd.read_csv(outputs["issue_type_summary"])
            field_summary = pd.read_csv(outputs["field_issue_summary"])

        self.assertEqual(len(issue_frame), 4)
        self.assertEqual(summary["total_issues"], 4)
        self.assertGreaterEqual(summary["issue_type_count"], 3)
        self.assertIn("missing_required_source_field", set(type_summary["issue_type"]))
        self.assertIn("country", set(field_summary["field"]))

    def test_empty_issue_file_writes_header_only_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            empty_issue = tmp_path / "issue_rows.csv"
            output_dir = tmp_path / "out"
            empty_issue.write_text(
                "row,field,value,issue_type,reason,source_skill,action,record_id,process_result,raw_record\n",
                encoding="utf-8",
            )

            outputs = generate_issue_list([empty_issue], output_dir)
            issue_frame = pd.read_csv(outputs["issue_rows"], keep_default_na=False)
            summary = json.loads(outputs["issue_summary"].read_text(encoding="utf-8"))

        self.assertEqual(list(issue_frame.columns), ["row", "field", "value", "issue_type", "reason", "source_skill", "action", "record_id", "process_result", "raw_record"])
        self.assertEqual(len(issue_frame), 0)
        self.assertEqual(summary["total_issues"], 0)


if __name__ == "__main__":
    unittest.main()
