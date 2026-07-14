from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from detect_abnormal_values import detect_dataframe, detect_dataset, load_rules, process_dataframe, validate_rules  # noqa: E402
from abnormal_file_utils import load_csv, load_data, load_json  # noqa: E402


def sample_rules() -> dict:
    return {
        "strict": False,
        "range_rules": {
            "age": {"min": 0, "max": 120},
            "salary": {"min": 0, "max": 1000000},
        },
        "enum_rules": {
            "gender": {"allowed": ["male", "female"]},
        },
        "regex_rules": {
            "email": {"pattern": r"^[^@]+@[^@]+\.[^@]+$"},
        },
    }


def write_rules(path: Path, output_dir: Path | None = None) -> None:
    output_block = ""
    if output_dir is not None:
        output_block = f"""
output:
  output_dir: "{output_dir}"
  abnormal_records_name: "abnormal_records.json"
"""

    path.write_text(
        f"""
strict: false

range_rules:
  age:
    min: 0
    max: 120
  salary:
    min: 0
    max: 1000000

enum_rules:
  gender:
    allowed:
      - male
      - female

regex_rules:
  email:
    pattern: '^[^@]+@[^@]+\\.[^@]+$'
{output_block}
""",
        encoding="utf-8",
    )


def write_strict_rules(path: Path, output_dir: Path | None = None, strict: bool = False) -> None:
    output_block = ""
    if output_dir is not None:
        output_block = f"""
output:
  output_dir: "{output_dir}"
  abnormal_records_name: "abnormal_records.json"
  rule_validation_report_name: "rule_validation_report.json"
"""

    path.write_text(
        f"""
strict: {"true" if strict else "false"}

range_rules:
  age:
    min: 0
    max: 120
  salary:
    min: 0
    max: 1000000

enum_rules:
  gender:
    allowed:
      - male
      - female

regex_rules:
  email:
    pattern: '^[^@]+@[^@]+\\.[^@]+$'
{output_block}
""",
        encoding="utf-8",
    )


def write_invalid_rules(path: Path, output_dir: Path | None = None, strict: bool = False) -> None:
    output_block = ""
    if output_dir is not None:
        output_block = f"""
output:
  output_dir: "{output_dir}"
  abnormal_records_name: "abnormal_records.json"
  rule_validation_report_name: "rule_validation_report.json"
"""

    path.write_text(
        f"""
strict: {"true" if strict else "false"}

range_rules:
  age:
    min: abc
    max: 120

enum_rules:
  gender:
    allowed: male

regex_rules:
  email:
    pattern: '['
{output_block}
""",
        encoding="utf-8",
    )


class FileUtilsTest(unittest.TestCase):
    def test_load_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sample.csv"
            csv_path.write_text("id,name\n1,Tom\n", encoding="utf-8")

            dataframe = load_csv(csv_path)

        self.assertEqual(len(dataframe), 1)
        self.assertEqual(dataframe.loc[0, "name"], "Tom")

    def test_load_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "sample.json"
            json_path.write_text(json.dumps([{"id": 1, "name": "Tom"}]), encoding="utf-8")

            dataframe = load_json(json_path)

        self.assertEqual(len(dataframe), 1)
        self.assertEqual(dataframe.loc[0, "name"], "Tom")

    def test_load_data_rejects_unknown_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = Path(tmpdir) / "sample.txt"
            txt_path.write_text("id,name\n1,Tom\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_data(txt_path)


class AbnormalValueDetectorTest(unittest.TestCase):
    def test_normal_data_has_no_abnormal_records(self):
        dataframe = pd.DataFrame(
            [{"age": 20, "salary": 12000, "gender": "male", "email": "tom@example.com"}]
        )

        report = detect_dataframe(dataframe, sample_rules())

        self.assertEqual(report["total_rows"], 1)
        self.assertEqual(report["abnormal_count"], 0)
        self.assertEqual(report["abnormal_summary"], {})
        self.assertEqual(report["field_summary"], {})
        self.assertEqual(report["abnormal_records"], [])

    def test_range_detection_supports_min_and_max(self):
        dataframe = pd.DataFrame(
            [
                {"age": -1, "salary": 12000},
                {"age": 999, "salary": 2000000},
            ]
        )
        rules = {"range_rules": {"age": {"min": 0, "max": 120}, "salary": {"min": 0, "max": 1000000}}}

        report = detect_dataframe(dataframe, rules)

        self.assertEqual(report["abnormal_count"], 3)
        self.assertEqual([item["reason"] for item in report["abnormal_records"]], ["out_of_range"] * 3)

    def test_enum_detection_finds_invalid_values(self):
        dataframe = pd.DataFrame([{"gender": "unknown"}, {"gender": "female"}])
        rules = {"enum_rules": {"gender": {"allowed": ["male", "female"]}}}

        report = detect_dataframe(dataframe, rules)

        self.assertEqual(report["abnormal_count"], 1)
        self.assertEqual(report["abnormal_records"][0]["field"], "gender")
        self.assertEqual(report["abnormal_records"][0]["reason"], "not_allowed")

    def test_regex_detection_finds_invalid_email(self):
        dataframe = pd.DataFrame([{"email": "bad-email"}, {"email": "tom@example.com"}])
        rules = {"regex_rules": {"email": {"pattern": r"^[^@]+@[^@]+\.[^@]+$"}}}

        report = detect_dataframe(dataframe, rules)

        self.assertEqual(report["abnormal_count"], 1)
        self.assertEqual(report["abnormal_records"][0]["value"], "bad-email")
        self.assertEqual(report["abnormal_records"][0]["reason"], "regex_not_match")

    def test_empty_rules_are_skipped(self):
        dataframe = pd.DataFrame([{"age": 999, "gender": "unknown", "email": "bad-email"}])
        rules = {
            "range_rules": {"age": {}},
            "enum_rules": {"gender": {"allowed": []}},
            "regex_rules": {"email": {"pattern": ""}},
        }

        report = detect_dataframe(dataframe, rules)

        self.assertEqual(report["abnormal_count"], 0)
        self.assertEqual(report["abnormal_records"], [])

    def test_unconfigured_field_is_not_detected(self):
        dataframe = pd.DataFrame([{"status": "unexpected"}])

        report = detect_dataframe(dataframe, sample_rules())

        self.assertEqual(report["abnormal_count"], 0)

    def test_output_record_fields_are_fixed(self):
        dataframe = pd.DataFrame([{"age": 999}])
        rules = {"range_rules": {"age": {"min": 0, "max": 120}}}

        report = detect_dataframe(dataframe, rules)
        record = report["abnormal_records"][0]

        self.assertEqual(
            set(report.keys()),
            {"total_rows", "abnormal_count", "abnormal_summary", "field_summary", "abnormal_records"},
        )
        self.assertEqual(
            list(record.keys()),
            ["row", "field", "value", "issue_type", "reason", "source_skill", "action"],
        )
        self.assertEqual(record["row"], 1)
        self.assertEqual(record["field"], "age")
        self.assertEqual(record["value"], 999)
        self.assertEqual(record["issue_type"], "out_of_range")
        self.assertEqual(record["reason"], "out_of_range")
        self.assertEqual(record["source_skill"], "abnormal-value-detector")
        self.assertEqual(record["action"], "detect")

    def test_process_dataframe_returns_unchanged_dataframe_and_report(self):
        dataframe = pd.DataFrame([{"age": 999}])
        rules = {"range_rules": {"age": {"min": 0, "max": 120}}}

        processed, report = process_dataframe(dataframe, rules)

        pd.testing.assert_frame_equal(processed, dataframe)
        self.assertEqual(report["abnormal_count"], 1)

    def test_abnormal_and_field_summary_are_generated(self):
        dataframe = pd.DataFrame(
            [
                {"age": -1, "salary": 100, "gender": "unknown", "email": "bad-email"},
                {"age": 999, "salary": 2000000, "gender": "female", "email": "ok@example.com"},
            ]
        )

        report = detect_dataframe(dataframe, sample_rules())

        self.assertEqual(report["abnormal_count"], 5)
        self.assertEqual(report["abnormal_summary"], {"out_of_range": 3, "not_allowed": 1, "regex_not_match": 1})
        self.assertEqual(report["field_summary"], {"age": 2, "salary": 1, "gender": 1, "email": 1})

    def test_rule_validation_accepts_valid_rules(self):
        dataframe = pd.DataFrame([{"age": 20, "salary": 12000, "gender": "male", "email": "tom@example.com"}])

        report = validate_rules(dataframe, sample_rules())

        self.assertTrue(report["valid"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])

    def test_strict_true_rejects_missing_field(self):
        dataframe = pd.DataFrame([{"age": 20}])
        rules = {"strict": True, "range_rules": {"missing_age": {"min": 0, "max": 120}}}

        report = validate_rules(dataframe, rules)

        self.assertFalse(report["valid"])
        self.assertTrue(report["strict"])
        self.assertIn("missing_field", report["errors"][0])
        self.assertEqual(report["warnings"], [])

    def test_strict_false_warns_and_skips_invalid_rules(self):
        dataframe = pd.DataFrame([{"age": 999, "gender": "unknown", "email": "bad-email"}])
        rules = {
            "strict": False,
            "range_rules": {"age": {"min": "abc", "max": 120}},
            "enum_rules": {"gender": {"allowed": "male"}},
            "regex_rules": {"email": {"pattern": "["}},
        }

        validation_report = validate_rules(dataframe, rules)
        detection_report = detect_dataframe(dataframe, rules)

        self.assertFalse(validation_report["valid"])
        self.assertEqual(validation_report["errors"], [])
        self.assertEqual(len(validation_report["warnings"]), 3)
        self.assertEqual(detection_report["abnormal_count"], 0)

    def test_strict_true_process_returns_error_for_invalid_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("id,age\n1,20\n", encoding="utf-8")
            rules_path.write_text(
                f"""
strict: true
range_rules:
  missing_age:
    min: 0
    max: 120
output:
  output_dir: "{output_dir}"
  abnormal_records_name: "abnormal_records.json"
  rule_validation_report_name: "rule_validation_report.json"
""",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                detect_dataset(input_path, rules_path)
            validation_payload = json.loads((output_dir / "rule_validation_report.json").read_text(encoding="utf-8"))

        self.assertFalse(validation_payload["valid"])
        self.assertIn("missing_field", validation_payload["errors"][0])

    def test_process_dataset_generates_abnormal_records_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text(
                "id,age,salary,gender,email,status\n"
                "1,20,12000,male,tom@example.com,active\n"
                "2,999,2000000,unknown,bad-email,inactive\n",
                encoding="utf-8",
            )
            write_rules(rules_path, output_dir)

            report = detect_dataset(input_path, rules_path)
            output_path = output_dir / "abnormal_records.json"
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            validation_path = output_dir / "rule_validation_report.json"
            file_generated = output_path.is_file()
            validation_generated = validation_path.is_file()

        self.assertTrue(file_generated)
        self.assertTrue(validation_generated)
        self.assertEqual(report["abnormal_count"], 4)
        self.assertEqual(payload["abnormal_count"], 4)

    def test_load_rules_supports_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.yaml"
            write_rules(rules_path)

            rules = load_rules(rules_path)

        self.assertIn("range_rules", rules)
        self.assertIn("enum_rules", rules)
        self.assertIn("regex_rules", rules)


class BoundaryAndAcceptanceTest(unittest.TestCase):
    def test_empty_file_strict_false_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "empty.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("", encoding="utf-8")
            write_strict_rules(rules_path, output_dir, strict=False)

            report = detect_dataset(input_path, rules_path)
            validation_payload = json.loads((output_dir / "rule_validation_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report["total_rows"], 0)
        self.assertEqual(report["abnormal_count"], 0)
        self.assertFalse(validation_payload["valid"])
        self.assertGreaterEqual(len(validation_payload["warnings"]), 1)

    def test_empty_file_strict_true_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "empty.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("", encoding="utf-8")
            write_strict_rules(rules_path, output_dir, strict=True)

            with self.assertRaises(ValueError):
                detect_dataset(input_path, rules_path)
            validation_generated = (output_dir / "rule_validation_report.json").is_file()

        self.assertTrue(validation_generated)

    def test_single_row_file(self):
        dataframe = pd.DataFrame([{"age": 20, "salary": 12000, "gender": "male", "email": "tom@example.com"}])

        report = detect_dataframe(dataframe, sample_rules())

        self.assertEqual(report["total_rows"], 1)
        self.assertEqual(report["abnormal_count"], 0)

    def test_all_legal_data(self):
        dataframe = pd.DataFrame(
            [
                {"age": 20, "salary": 12000, "gender": "male", "email": "tom@example.com"},
                {"age": 30, "salary": 15000, "gender": "female", "email": "alice@example.com"},
            ]
        )

        report = detect_dataframe(dataframe, sample_rules())

        self.assertEqual(report["abnormal_count"], 0)
        self.assertEqual(report["abnormal_summary"], {})

    def test_all_abnormal_data(self):
        dataframe = pd.DataFrame(
            [
                {"age": -1, "salary": -100, "gender": "unknown", "email": "bad-email"},
                {"age": 999, "salary": 2000000, "gender": "other", "email": "alice@site"},
            ]
        )

        report = detect_dataframe(dataframe, sample_rules())

        self.assertEqual(report["abnormal_count"], 8)
        self.assertEqual(report["abnormal_summary"], {"out_of_range": 4, "not_allowed": 2, "regex_not_match": 2})
        self.assertEqual(report["field_summary"], {"age": 2, "salary": 2, "gender": 2, "email": 2})

    def test_missing_detection_field_strict_false(self):
        dataframe = pd.DataFrame([{"id": 1, "name": "Tom"}])

        validation_report = validate_rules(dataframe, sample_rules())
        detection_report = detect_dataframe(dataframe, sample_rules())

        self.assertFalse(validation_report["valid"])
        self.assertEqual(validation_report["errors"], [])
        self.assertGreaterEqual(len(validation_report["warnings"]), 1)
        self.assertEqual(detection_report["abnormal_count"], 0)

    def test_missing_rules_file_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_rules_path = Path(tmpdir) / "missing_rules.yaml"

            with self.assertRaises(FileNotFoundError):
                load_rules(missing_rules_path)

    def test_empty_rules_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "empty_rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("id,age\n1,999\n", encoding="utf-8")
            rules_path.write_text("", encoding="utf-8")

            report = detect_dataset(input_path, rules_path, output_dir)
            validation_payload = json.loads((output_dir / "rule_validation_report.json").read_text(encoding="utf-8"))

        self.assertTrue(validation_payload["valid"])
        self.assertEqual(report["abnormal_count"], 0)

    def test_invalid_rules_strict_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "invalid_rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("id,age,gender,email\n1,999,unknown,bad-email\n", encoding="utf-8")
            write_invalid_rules(rules_path, output_dir, strict=False)

            report = detect_dataset(input_path, rules_path)
            validation_payload = json.loads((output_dir / "rule_validation_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report["abnormal_count"], 0)
        self.assertFalse(validation_payload["valid"])
        self.assertEqual(len(validation_payload["warnings"]), 3)

    def test_large_file_over_10000_rows(self):
        rows = []
        for index in range(1, 10002):
            rows.append(
                {
                    "age": 999 if index % 1000 == 0 else 30,
                    "salary": 2000000 if index % 1000 == 0 else 12000,
                    "gender": "unknown" if index % 1000 == 0 else "male",
                    "email": "bad-email" if index % 1000 == 0 else f"user{index}@example.com",
                }
            )
        dataframe = pd.DataFrame(rows)

        report = detect_dataframe(dataframe, sample_rules())

        self.assertEqual(report["total_rows"], 10001)
        self.assertEqual(report["abnormal_count"], 40)
        self.assertEqual(report["abnormal_summary"], {"out_of_range": 20, "not_allowed": 10, "regex_not_match": 10})

    def test_json_input_is_supported_for_legal_and_abnormal_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            json_path = tmp_path / "input.json"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            json_path.write_text(
                json.dumps(
                    [
                        {"age": 20, "salary": 12000, "gender": "male", "email": "tom@example.com"},
                        {"age": 999, "salary": 2000000, "gender": "unknown", "email": "bad-email"},
                    ]
                ),
                encoding="utf-8",
            )
            write_strict_rules(rules_path, output_dir, strict=False)

            report = detect_dataset(json_path, rules_path)

        self.assertEqual(report["total_rows"], 2)
        self.assertEqual(report["abnormal_count"], 4)

    def test_readme_acceptance_normal_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "normal.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("age,salary,gender,email\n20,12000,male,tom@example.com\n", encoding="utf-8")
            write_strict_rules(rules_path, output_dir, strict=False)

            report = detect_dataset(input_path, rules_path)

        self.assertEqual(report["abnormal_count"], 0)

    def test_readme_acceptance_abnormal_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "abnormal.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("age,salary,gender,email\n999,2000000,unknown,bad-email\n", encoding="utf-8")
            write_strict_rules(rules_path, output_dir, strict=False)

            report = detect_dataset(input_path, rules_path)

        self.assertEqual(report["abnormal_count"], 4)

    def test_readme_acceptance_wrong_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "invalid_rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("age,gender,email\n999,unknown,bad-email\n", encoding="utf-8")
            write_invalid_rules(rules_path, output_dir, strict=True)

            with self.assertRaises(ValueError):
                detect_dataset(input_path, rules_path)
            validation_payload = json.loads((output_dir / "rule_validation_report.json").read_text(encoding="utf-8"))

        self.assertFalse(validation_payload["valid"])
        self.assertGreaterEqual(len(validation_payload["errors"]), 1)

    def test_readme_acceptance_empty_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "empty.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("", encoding="utf-8")
            write_strict_rules(rules_path, output_dir, strict=False)

            report = detect_dataset(input_path, rules_path)

        self.assertEqual(report["total_rows"], 0)
        self.assertEqual(report["abnormal_count"], 0)


if __name__ == "__main__":
    unittest.main()
