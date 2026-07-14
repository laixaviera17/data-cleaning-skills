import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from generate_cleaning_log import generate_cleaning_log, normalize_log_records  # noqa: E402


class CleaningOperationLogGeneratorTest(unittest.TestCase):
    def test_normalize_existing_cleaning_log_records(self):
        records = [
            {
                "timestamp": "2026-06-16 10:00:00",
                "rule_name": "load_input",
                "action": "check",
                "affected_rows": 25,
                "result": "success",
            }
        ]

        normalized = normalize_log_records(records, "csv-json-data-cleaning-pipeline")

        self.assertEqual(normalized[0]["step"], "load_input")
        self.assertEqual(normalized[0]["rule_name"], "load_input")
        self.assertEqual(normalized[0]["message"], "")
        self.assertEqual(normalized[0]["source_skill"], "csv-json-data-cleaning-pipeline")

    def test_json_logs_are_normalized_with_extended_columns(self):
        records = [
            {
                "time": "2026-06-16 10:00:01",
                "step": "dictionary_validation",
                "operation": "standardize",
                "affected_count": "3",
                "status": "warning",
                "detail": "发现非法字典值",
                "input_rows": 10,
                "output_rows": 10,
            }
        ]

        normalized = normalize_log_records(records, "field-dictionary-value-validator")

        self.assertEqual(normalized[0]["rule_name"], "dictionary_validation")
        self.assertEqual(normalized[0]["affected_rows"], 3)
        self.assertEqual(normalized[0]["result"], "warning")
        self.assertEqual(normalized[0]["input_count"], 10)

    def test_generate_cleaning_log_merges_csv_and_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            csv_log = tmp_path / "cleaning_log.csv"
            json_log = tmp_path / "dictionary_log.json"
            output_dir = tmp_path / "out"

            csv_log.write_text(
                "timestamp,rule_name,action,affected_rows,result\n"
                "2026-06-16 10:00:00,load_input,check,25,success\n"
                "2026-06-16 10:00:01,format-standardizer,standardize,5,warning\n",
                encoding="utf-8",
            )
            json_log.write_text(
                json.dumps(
                    {
                        "cleaning_log": [
                            {
                                "timestamp": "2026-06-16 10:00:02",
                                "step": "dictionary_validation",
                                "action": "standardize",
                                "affected_rows": 3,
                                "result": "success",
                                "message": "标准化字典值",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            outputs = generate_cleaning_log([csv_log, json_log], output_dir)
            log_frame = pd.read_csv(outputs["cleaning_log"], keep_default_na=False)
            summary = json.loads(outputs["cleaning_log_summary"].read_text(encoding="utf-8"))
            step_summary = pd.read_csv(outputs["step_summary"], keep_default_na=False)
            result_summary = pd.read_csv(outputs["result_summary"], keep_default_na=False)

        self.assertEqual(len(log_frame), 3)
        self.assertEqual(summary["total_steps"], 3)
        self.assertEqual(summary["warning_steps"], 1)
        self.assertEqual(summary["total_affected_rows"], 33)
        self.assertIn("format-standardizer", set(step_summary["step"]))
        self.assertIn("success", set(result_summary["result"]))

    def test_empty_log_file_writes_header_only_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            empty_log = tmp_path / "cleaning_log.csv"
            output_dir = tmp_path / "out"
            empty_log.write_text("timestamp,rule_name,action,affected_rows,result\n", encoding="utf-8")

            outputs = generate_cleaning_log([empty_log], output_dir)
            log_frame = pd.read_csv(outputs["cleaning_log"], keep_default_na=False)
            summary = json.loads(outputs["cleaning_log_summary"].read_text(encoding="utf-8"))

        self.assertEqual(
            list(log_frame.columns),
            ["timestamp", "step", "rule_name", "action", "affected_rows", "result", "message", "source_skill", "input_count", "output_count"],
        )
        self.assertEqual(len(log_frame), 0)
        self.assertEqual(summary["total_steps"], 0)


if __name__ == "__main__":
    unittest.main()
