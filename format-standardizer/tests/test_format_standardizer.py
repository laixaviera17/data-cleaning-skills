from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from format_file_utils import load_csv, load_data, load_json, save_json  # noqa: E402
from standardize_format import (  # noqa: E402
    process_dataframe,
    process_dataset,
    standardize_amount,
    standardize_date,
    standardize_id_card,
    standardize_phone,
)


def write_rules(path: Path, output_dir: Path | None = None) -> None:
    output_block = ""
    if output_dir is not None:
        output_block = f"""
output:
  output_dir: "{output_dir}"
  standardization_report_name: "standardization_report.json"
"""

    path.write_text(
        f"""
standardize_fields:
  date:
    - field: publish_date
      output_format: "%Y-%m-%d"
  phone:
    - field: phone
      country_code: "86"
  amount:
    - field: amount
      decimal_places: 2
{output_block}
""",
        encoding="utf-8",
    )


def write_rule_driven_rules(path: Path, output_dir: Path | None = None, strict: bool = True) -> None:
    output_block = ""
    if output_dir is not None:
        output_block = f"""
output:
  output_dir: "{output_dir}"
  standardization_report_name: "standardization_report.json"
  abnormal_records_name: "abnormal_records.json"
"""

    path.write_text(
        f"""
date_rules:
  enable: true
  strict: {"true" if strict else "false"}
  fields:
    - publish_date
phone_rules:
  enable: true
  strict: {"true" if strict else "false"}
  country_code: "86"
  fields:
    - phone
amount_rules:
  enable: true
  strict: {"true" if strict else "false"}
  decimal_places: 2
  fields:
    - amount
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

    def test_save_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "report.json"

            save_json({"total_rows": 1}, output_path)

            self.assertTrue(output_path.is_file())


class FormatStandardizerTest(unittest.TestCase):
    def test_date_standardization(self):
        self.assertEqual(standardize_date("2025/01/01"), "2025-01-01")
        self.assertEqual(standardize_date("2025-1-1"), "2025-01-01")
        self.assertEqual(standardize_date("01-01-2025"), "2025-01-01")
        self.assertEqual(standardize_date("2025.01.01"), "2025-01-01")

    def test_phone_standardization(self):
        self.assertEqual(standardize_phone("138 0013 8000"), "13800138000")
        self.assertEqual(standardize_phone("138-0013-8000"), "13800138000")
        self.assertEqual(standardize_phone("+86-13800138000"), "13800138000")
        self.assertEqual(standardize_phone("0086 13800138000"), "13800138000")

    def test_amount_standardization(self):
        self.assertEqual(standardize_amount("￥1,200.00"), "1200.00")
        self.assertEqual(standardize_amount("$66.6"), "66.60")
        self.assertEqual(standardize_amount("1,200"), "1200.00")
        self.assertEqual(standardize_amount("1200"), "1200.00")
        self.assertEqual(standardize_amount("1200元"), "1200.00")
        self.assertEqual(standardize_amount("-10"), "-10.00")
        self.assertIsNone(standardize_amount("-10", allow_negative=False))

    def test_id_card_standardization(self):
        self.assertEqual(standardize_id_card("11010519491231002x"), "11010519491231002X")
        self.assertEqual(standardize_id_card("110105194912310021"), "110105194912310021")
        self.assertIsNone(standardize_id_card("12345"))

    def test_invalid_values_are_kept_and_counted(self):
        dataframe = pd.DataFrame(
            [
                {"publish_date": "bad-date", "phone": "12345", "amount": "abc"},
            ]
        )
        rules = {
            "standardize_fields": {
                "date": [{"field": "publish_date"}],
                "phone": [{"field": "phone"}],
                "amount": [{"field": "amount", "decimal_places": 2}],
            }
        }

        standardized, report = process_dataframe(dataframe, rules)

        self.assertEqual(standardized.loc[0, "publish_date"], "bad-date")
        self.assertEqual(standardized.loc[0, "phone"], "12345")
        self.assertEqual(standardized.loc[0, "amount"], "abc")
        self.assertEqual(report["failed_cells"], 3)

    def test_invalid_action_set_null_blanks_failed_value(self):
        dataframe = pd.DataFrame([{"amount": "-10"}])
        rules = {
            "amount_rules": {
                "enable": True,
                "strict": True,
                "fields": [
                    {
                        "field": "amount",
                        "decimal_places": 2,
                        "allow_negative": False,
                        "invalid_action": "set_null",
                    }
                ],
            }
        }

        standardized, report = process_dataframe(dataframe, rules)

        self.assertEqual(standardized.loc[0, "amount"], "")
        self.assertEqual(report["failed_cells"], 1)
        self.assertEqual(report["abnormal_records"][0]["value"], "-10")

    def test_process_dataframe_standardizes_configured_fields(self):
        dataframe = pd.DataFrame(
            [
                {
                    "publish_date": "2025/01/01",
                    "phone": "+86-13800138000",
                    "amount": "￥1,200.00",
                }
            ]
        )
        rules = {
            "standardize_fields": {
                "date": [{"field": "publish_date"}],
                "phone": [{"field": "phone", "country_code": "86"}],
                "amount": [{"field": "amount", "decimal_places": 2}],
            }
        }

        standardized, report = process_dataframe(dataframe, rules)

        self.assertEqual(standardized.loc[0, "publish_date"], "2025-01-01")
        self.assertEqual(standardized.loc[0, "phone"], "13800138000")
        self.assertEqual(standardized.loc[0, "amount"], "1200.00")
        self.assertEqual(report["standardized_cells"], 3)
        self.assertEqual(report["failed_cells"], 0)

    def test_process_dataframe_supports_unit_standardization(self):
        dataframe = pd.DataFrame([{"weight": "1.25kg", "distance": "300cm", "duration": "2h"}])
        rules = {
            "unit_rules": {
                "enable": True,
                "strict": True,
                "fields": [
                    {"field": "weight", "unit_type": "weight", "target_unit": "g", "decimal_places": 1},
                    {"field": "distance", "unit_type": "length", "target_unit": "m", "decimal_places": 2},
                    {"field": "duration", "unit_type": "time", "target_unit": "min", "decimal_places": 1},
                ],
            }
        }

        standardized, report = process_dataframe(dataframe, rules)

        self.assertEqual(standardized.loc[0, "weight"], "1250.0g")
        self.assertEqual(standardized.loc[0, "distance"], "3.00m")
        self.assertEqual(standardized.loc[0, "duration"], "120.0min")
        self.assertEqual(len(report["unit_conversion_records"]), 3)

    def test_process_dataset_generates_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text(
                "id,publish_date,phone,amount\n"
                '1,2025/01/01,+86-13800138000,"￥1,200.00"\n'
                "2,bad-date,12345,abc\n",
                encoding="utf-8",
            )
            write_rules(rules_path, output_dir)

            report = process_dataset(input_path, rules_path)
            report_path = output_dir / "standardization_report.json"
            saved_report = json.loads(report_path.read_text(encoding="utf-8"))
            file_generated = report_path.is_file()

        self.assertTrue(file_generated)
        self.assertEqual(report["total_rows"], 2)
        self.assertEqual(report["standardized_cells"], 3)
        self.assertEqual(report["failed_cells"], 3)
        self.assertEqual(saved_report["total_rows"], 2)

    def test_process_dataset_detects_gbk_and_writes_utf8_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input_gbk.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            content = "id,publish_date,phone,amount\n1,2025/01/01,13800138000,100元\n"
            input_path.write_bytes(content.encode("gbk"))
            write_rule_driven_rules(rules_path, output_dir=output_dir, strict=False)

            report = process_dataset(input_path, rules_path)

            encoding_report = report["encoding_report"]
            self.assertEqual(encoding_report["detected_encoding"], "gb18030")
            standardized_path = output_dir / "standardized_data.csv"
            raw_bytes = standardized_path.read_bytes()
            self.assertTrue(raw_bytes.decode("utf-8").startswith("id,publish_date"))

    def test_missing_configured_field_is_reported(self):
        dataframe = pd.DataFrame([{"id": 1}])
        rules = {"standardize_fields": {"date": [{"field": "publish_date"}]}}

        _, report = process_dataframe(dataframe, rules)

        self.assertEqual(report["missing_fields"], ["publish_date"])

    def test_rule_driven_standardization_with_strict_mode(self):
        dataframe = pd.DataFrame(
            [
                {
                    "publish_date": "2025/01/01",
                    "phone": "+86-13800138000",
                    "amount": "￥1,200.00",
                },
                {
                    "publish_date": "bad-date",
                    "phone": "12345",
                    "amount": "abc",
                },
            ]
        )
        rules = {
            "date_rules": {
                "enable": True,
                "strict": True,
                "fields": ["publish_date"],
            },
            "phone_rules": {
                "enable": True,
                "strict": True,
                "country_code": "86",
                "fields": ["phone"],
            },
            "amount_rules": {
                "enable": True,
                "strict": True,
                "decimal_places": 2,
                "fields": ["amount"],
            },
        }

        standardized, report = process_dataframe(dataframe, rules)

        self.assertEqual(standardized.loc[0, "publish_date"], "2025-01-01")
        self.assertEqual(standardized.loc[0, "phone"], "13800138000")
        self.assertEqual(standardized.loc[0, "amount"], "1200.00")
        self.assertEqual(report["standardized_cells"], 3)
        self.assertEqual(report["failed_cells"], 3)
        self.assertEqual(len(report["abnormal_records"]), 3)
        self.assertEqual(report["abnormal_records"][0]["field"], "publish_date")
        self.assertEqual(
            list(report["abnormal_records"][0].keys()),
            ["row", "field", "value", "issue_type", "reason", "source_skill", "action"],
        )

    def test_disabled_rule_is_skipped(self):
        dataframe = pd.DataFrame([{"publish_date": "2025/01/01"}])
        rules = {
            "date_rules": {
                "enable": False,
                "strict": True,
                "fields": ["publish_date"],
            }
        }

        standardized, report = process_dataframe(dataframe, rules)

        self.assertEqual(standardized.loc[0, "publish_date"], "2025/01/01")
        self.assertEqual(report["standardized_cells"], 0)
        self.assertEqual(report["failed_cells"], 0)
        self.assertEqual(report["abnormal_records"], [])

    def test_process_dataset_generates_abnormal_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text(
                "id,publish_date,phone,amount\n"
                '1,2025/01/01,+86-13800138000,"￥1,200.00"\n'
                "2,bad-date,12345,abc\n",
                encoding="utf-8",
            )
            rules_path.write_text(
                f"""
date_rules:
  enable: true
  strict: true
  fields:
    - publish_date
phone_rules:
  enable: true
  strict: true
  country_code: "86"
  fields:
    - phone
amount_rules:
  enable: true
  strict: true
  decimal_places: 2
  fields:
    - amount
output:
  output_dir: "{output_dir}"
  standardization_report_name: "standardization_report.json"
  abnormal_records_name: "abnormal_records.json"
""",
                encoding="utf-8",
            )

            report = process_dataset(input_path, rules_path)
            abnormal_path = output_dir / "abnormal_records.json"
            abnormal_payload = json.loads(abnormal_path.read_text(encoding="utf-8"))
            abnormal_generated = abnormal_path.is_file()

        self.assertTrue(abnormal_generated)
        self.assertEqual(report["failed_cells"], 3)
        self.assertEqual(len(abnormal_payload["abnormal_records"]), 3)


class BoundaryAndAcceptanceTest(unittest.TestCase):
    def test_empty_file_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "empty.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text("", encoding="utf-8")
            write_rule_driven_rules(rules_path, output_dir)

            report = process_dataset(input_path, rules_path)

        self.assertEqual(report["total_rows"], 0)
        self.assertEqual(report["standardized_cells"], 0)
        self.assertEqual(report["failed_cells"], 0)
        self.assertEqual(report["missing_fields"], ["publish_date", "phone", "amount"])

    def test_single_row_file_is_processed(self):
        dataframe = pd.DataFrame(
            [
                {
                    "publish_date": "2025/01/01",
                    "phone": "+86-13800138000",
                    "amount": "￥1,200.00",
                }
            ]
        )
        rules = {
            "date_rules": {"enable": True, "strict": True, "fields": ["publish_date"]},
            "phone_rules": {"enable": True, "strict": True, "country_code": "86", "fields": ["phone"]},
            "amount_rules": {"enable": True, "strict": True, "decimal_places": 2, "fields": ["amount"]},
        }

        standardized, report = process_dataframe(dataframe, rules)

        self.assertEqual(report["total_rows"], 1)
        self.assertEqual(report["standardized_cells"], 3)
        self.assertEqual(standardized.loc[0, "publish_date"], "2025-01-01")

    def test_empty_phone_is_recorded_as_abnormal(self):
        dataframe = pd.DataFrame([{"publish_date": "2025/01/01", "phone": "", "amount": "1200"}])
        rules = {"phone_rules": {"enable": True, "strict": True, "country_code": "86", "fields": ["phone"]}}

        _, report = process_dataframe(dataframe, rules)

        self.assertEqual(report["failed_cells"], 1)
        self.assertEqual(report["abnormal_records"][0]["field"], "phone")

    def test_invalid_phone_is_recorded_as_abnormal(self):
        dataframe = pd.DataFrame([{"phone": "12345"}])
        rules = {"phone_rules": {"enable": True, "strict": True, "country_code": "86", "fields": ["phone"]}}

        _, report = process_dataframe(dataframe, rules)

        self.assertEqual(report["failed_cells"], 1)
        self.assertEqual(report["abnormal_records"][0]["value"], "12345")

    def test_invalid_date_is_recorded_as_abnormal(self):
        dataframe = pd.DataFrame([{"publish_date": "2025/13/01"}])
        rules = {"date_rules": {"enable": True, "strict": True, "fields": ["publish_date"]}}

        _, report = process_dataframe(dataframe, rules)

        self.assertEqual(report["failed_cells"], 1)
        self.assertEqual(report["abnormal_records"][0]["field"], "publish_date")

    def test_invalid_amount_is_recorded_as_abnormal(self):
        dataframe = pd.DataFrame([{"amount": "12OO元"}])
        rules = {"amount_rules": {"enable": True, "strict": True, "decimal_places": 2, "fields": ["amount"]}}

        _, report = process_dataframe(dataframe, rules)

        self.assertEqual(report["failed_cells"], 1)
        self.assertEqual(report["abnormal_records"][0]["field"], "amount")

    def test_large_file_processing_stats_are_stable(self):
        rows = []
        for index in range(1, 10001):
            rows.append(
                {
                    "publish_date": "bad-date" if index % 20 == 0 else "2025/01/01",
                    "phone": "12345" if index % 25 == 0 else "+86-13800138000",
                    "amount": "abc" if index % 40 == 0 else "￥1,200.00",
                }
            )
        dataframe = pd.DataFrame(rows)
        rules = {
            "date_rules": {"enable": True, "strict": True, "fields": ["publish_date"]},
            "phone_rules": {"enable": True, "strict": True, "country_code": "86", "fields": ["phone"]},
            "amount_rules": {"enable": True, "strict": True, "decimal_places": 2, "fields": ["amount"]},
        }

        _, report = process_dataframe(dataframe, rules)

        self.assertEqual(report["total_rows"], 10000)
        self.assertEqual(report["standardized_cells"], 28850)
        self.assertEqual(report["failed_cells"], 1150)
        self.assertEqual(len(report["abnormal_records"]), 1150)

    def test_mixed_format_file_is_processed(self):
        dataframe = pd.DataFrame(
            [
                {"publish_date": "2025/01/01", "phone": "138 0013 8000", "amount": "￥1,200.00"},
                {"publish_date": "2025-1-1", "phone": "138-0013-8000", "amount": "1,200"},
                {"publish_date": "01-01-2025", "phone": "+86-13800138000", "amount": "1200"},
                {"publish_date": "2025.01.01", "phone": "0086 13800138000", "amount": "1200元"},
            ]
        )
        rules = {
            "date_rules": {"enable": True, "strict": True, "fields": ["publish_date"]},
            "phone_rules": {"enable": True, "strict": True, "country_code": "86", "fields": ["phone"]},
            "amount_rules": {"enable": True, "strict": True, "decimal_places": 2, "fields": ["amount"]},
        }

        standardized, report = process_dataframe(dataframe, rules)

        self.assertEqual(report["standardized_cells"], 12)
        self.assertEqual(report["failed_cells"], 0)
        self.assertEqual(standardized.loc[3, "phone"], "13800138000")

    def test_acceptance_outputs_are_generated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text(
                "id,publish_date,phone,amount\n"
                '1,2025/01/01,+86-13800138000,"￥1,200.00"\n'
                "2,bad-date,12345,abc\n",
                encoding="utf-8",
            )
            write_rule_driven_rules(rules_path, output_dir)

            report = process_dataset(input_path, rules_path)
            report_exists = (output_dir / "standardization_report.json").is_file()
            abnormal_exists = (output_dir / "abnormal_records.json").is_file()

        self.assertTrue(report_exists)
        self.assertTrue(abnormal_exists)
        self.assertEqual(report["total_rows"], 2)
        self.assertEqual(report["failed_cells"], 3)


if __name__ == "__main__":
    unittest.main()
