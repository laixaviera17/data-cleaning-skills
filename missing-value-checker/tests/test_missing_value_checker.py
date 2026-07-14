from __future__ import annotations

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
import sys

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from check_missing_values import build_quality_report, process_dataframe, process_dataset  # noqa: E402
from missing_file_utils import file_exists, load_csv, load_data, load_json, save_json  # noqa: E402


def write_basic_rules(path: Path, output_dir: Path | None = None) -> None:
    output_block = ""
    if output_dir is not None:
        output_block = f"""
output:
  output_dir: "{output_dir}"
  quality_report_name: "quality_report.json"
"""

    path.write_text(
        f"""
required_fields:
  - id
  - name
  - phone
  - email
null_values:
  - ""
  - "null"
  - "N/A"
  - "未知"
{output_block}
""",
        encoding="utf-8",
    )


def write_repair_rules(path: Path, output_dir: Path | None = None) -> None:
    output_block = ""
    if output_dir is not None:
        output_block = f"""
output:
  output_dir: "{output_dir}"
  quality_report_name: "quality_report.json"
"""

    path.write_text(
        f"""
required_fields:
  - id
  - name
  - phone
null_values:
  - ""
  - "N/A"
  - "未知"
field_rules:
  name:
    action: fill_default
    value: UNKNOWN
  phone:
    action: keep_null
{output_block}
""",
        encoding="utf-8",
    )


class FileUtilsTest(unittest.TestCase):
    def test_load_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sample.csv"
            csv_path.write_text("id,name\n1,Tom\n2,Alice\n", encoding="utf-8")

            dataframe = load_csv(csv_path)

        self.assertEqual(list(dataframe.columns), ["id", "name"])
        self.assertEqual(len(dataframe), 2)
        self.assertEqual(dataframe.loc[0, "name"], "Tom")

    def test_load_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "sample.json"
            json_path.write_text(
                json.dumps([{"id": 1, "name": "Tom"}, {"id": 2, "name": "Alice"}]),
                encoding="utf-8",
            )

            dataframe = load_json(json_path)

        self.assertEqual(list(dataframe.columns), ["id", "name"])
        self.assertEqual(len(dataframe), 2)
        self.assertEqual(dataframe.loc[1, "name"], "Alice")

    def test_load_data_rejects_unknown_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = Path(tmpdir) / "sample.txt"
            txt_path.write_text("id,name\n1,Tom\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_data(txt_path)

    def test_load_json_rejects_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "bad.json"
            json_path.write_text("{bad json", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                load_json(json_path)

    def test_load_csv_rejects_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "bad_encoding.csv"
            csv_path.write_bytes(b"id,name\n1,\xff\n")

            with self.assertRaises(RuntimeError):
                load_csv(csv_path)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "missing.csv"

            self.assertFalse(file_exists(missing_path))
            with self.assertRaises(FileNotFoundError):
                load_csv(missing_path)

    def test_save_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "quality_report.json"

            save_json({"total_rows": 2}, output_path)

            self.assertTrue(output_path.is_file())
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["total_rows"], 2)


class MissingCheckerTest(unittest.TestCase):
    def test_field_and_null_statistics(self):
        dataframe = pd.DataFrame(
            [
                {"id": 1, "name": "Tom", "phone": "13800138000"},
                {"id": 2, "name": "", "phone": "N/A"},
                {"id": 3, "name": "未知", "phone": "13900139000"},
            ]
        )
        rules = {
            "required_fields": ["id", "name", "phone", "email"],
            "null_values": ["", "N/A", "未知"],
        }

        report = build_quality_report(dataframe, rules)

        self.assertEqual(report["total_rows"], 3)
        self.assertEqual(report["total_fields"], 3)
        self.assertEqual(report["missing_cells"], 3)
        self.assertEqual(report["repaired_cells"], 0)
        self.assertEqual(report["unrepaired_cells"], 3)
        self.assertEqual(report["missing_fields"], ["email"])
        self.assertEqual(report["field_stats"]["name"]["missing_cells"], 2)
        self.assertEqual(report["field_stats"]["phone"]["missing_cells"], 1)

    def test_process_csv_generates_quality_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text(
                "id,name,phone\n"
                "1,Tom,13800138000\n"
                "2,,N/A\n",
                encoding="utf-8",
            )
            write_basic_rules(rules_path, output_dir)

            report = process_dataset(input_path, rules_path)
            report_path = output_dir / "quality_report.json"

            saved_report = json.loads(report_path.read_text(encoding="utf-8"))
            file_generated = report_path.is_file()

        self.assertTrue(file_generated)
        self.assertEqual(report["total_rows"], 2)
        self.assertEqual(report["missing_cells"], 2)
        self.assertEqual(report["repaired_cells"], 0)
        self.assertEqual(report["unrepaired_cells"], 2)
        self.assertEqual(report["missing_fields"], ["email"])
        self.assertEqual(saved_report["total_rows"], 2)

    def test_process_json_generates_quality_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.json"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text(
                json.dumps(
                    [
                        {"id": 1, "name": "Tom", "phone": "13800138000"},
                        {"id": 2, "name": None, "phone": "未知"},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            write_basic_rules(rules_path, output_dir)

            report = process_dataset(input_path, rules_path)

        self.assertEqual(report["total_rows"], 2)
        self.assertEqual(report["missing_cells"], 2)
        self.assertEqual(report["repaired_cells"], 0)
        self.assertEqual(report["unrepaired_cells"], 2)
        self.assertEqual(report["missing_fields"], ["email"])

    def test_missing_required_fields_with_no_missing_cells(self):
        dataframe = pd.DataFrame([{"id": 1, "name": "Tom"}])
        rules = {"required_fields": ["id", "name", "phone"], "null_values": [""]}

        report = build_quality_report(dataframe, rules)

        self.assertEqual(report["missing_cells"], 0)
        self.assertEqual(report["repaired_cells"], 0)
        self.assertEqual(report["unrepaired_cells"], 0)
        self.assertEqual(report["missing_fields"], ["phone"])

    def test_fill_default_repairs_missing_cells(self):
        dataframe = pd.DataFrame(
            [
                {"id": 1, "name": "", "phone": "13800138000"},
                {"id": 2, "name": "N/A", "phone": "13900139000"},
            ]
        )
        rules = {
            "required_fields": ["id", "name", "phone"],
            "null_values": ["", "N/A"],
            "field_rules": {
                "name": {
                    "action": "fill_default",
                    "value": "UNKNOWN",
                }
            },
        }

        repaired, report = process_dataframe(dataframe, rules)

        self.assertEqual(repaired.loc[0, "name"], "UNKNOWN")
        self.assertEqual(repaired.loc[1, "name"], "UNKNOWN")
        self.assertEqual(report["missing_cells"], 2)
        self.assertEqual(report["repaired_cells"], 2)
        self.assertEqual(report["unrepaired_cells"], 0)

    def test_fill_custom_repairs_configured_field(self):
        dataframe = pd.DataFrame(
            [
                {"id": 1, "country": ""},
                {"id": 2, "country": "N/A"},
                {"id": 3, "country": "Japan"},
            ]
        )
        rules = {
            "required_fields": ["id", "country"],
            "null_values": ["", "N/A"],
            "field_rules": {
                "country": {
                    "action": "fill_custom",
                    "value": "CHINA",
                }
            },
        }

        repaired, report = process_dataframe(dataframe, rules)

        self.assertEqual(repaired.loc[0, "country"], "CHINA")
        self.assertEqual(repaired.loc[1, "country"], "CHINA")
        self.assertEqual(repaired.loc[2, "country"], "Japan")
        self.assertEqual(report["repaired_cells"], 2)
        self.assertEqual(report["unrepaired_cells"], 0)

    def test_drop_strategy_removes_rows_with_missing_values(self):
        dataframe = pd.DataFrame(
            [
                {"id": 1, "content": ""},
                {"id": 2, "content": "ok"},
                {"id": 3, "content": "N/A"},
            ]
        )
        rules = {
            "required_fields": ["id", "content"],
            "null_values": ["", "N/A"],
            "field_rules": {"content": {"action": "drop"}},
        }

        repaired, report = process_dataframe(dataframe, rules)

        self.assertEqual(list(repaired["id"]), [2])
        self.assertEqual(report["dropped_rows"], 2)
        self.assertEqual(report["dropped_cells"], 2)
        self.assertEqual(report["unrepaired_cells"], 0)

    def test_statistical_fill_strategies(self):
        dataframe = pd.DataFrame(
            [
                {"id": 1, "score_mean": "10", "score_median": "1", "score_mode": "9"},
                {"id": 2, "score_mean": "", "score_median": "", "score_mode": "9"},
                {"id": 3, "score_mean": "20", "score_median": "100", "score_mode": ""},
                {"id": 4, "score_mean": "30", "score_median": "2", "score_mode": "3"},
            ]
        )
        rules = {
            "required_fields": ["id"],
            "null_values": [""],
            "field_rules": {
                "score_mean": {"action": "mean"},
                "score_median": {"action": "median"},
                "score_mode": {"action": "mode"},
            },
        }

        repaired, report = process_dataframe(dataframe, rules)

        self.assertAlmostEqual(float(repaired.loc[1, "score_mean"]), 20.0)
        self.assertAlmostEqual(float(repaired.loc[1, "score_median"]), 2.0)
        self.assertEqual(str(repaired.loc[2, "score_mode"]), "9")
        self.assertEqual(report["repaired_cells"], 3)
        self.assertEqual(report["unrepaired_cells"], 0)

    def test_ffill_and_bfill_strategies(self):
        dataframe = pd.DataFrame(
            [
                {"id": 1, "city_ffill": "Beijing", "city_bfill": ""},
                {"id": 2, "city_ffill": "", "city_bfill": ""},
                {"id": 3, "city_ffill": "", "city_bfill": "Shanghai"},
            ]
        )
        rules = {
            "required_fields": ["id"],
            "null_values": [""],
            "field_rules": {
                "city_ffill": {"action": "ffill"},
                "city_bfill": {"action": "bfill"},
            },
        }

        repaired, report = process_dataframe(dataframe, rules)

        self.assertEqual(repaired.loc[1, "city_ffill"], "Beijing")
        self.assertEqual(repaired.loc[1, "city_bfill"], "Shanghai")
        self.assertEqual(report["repaired_cells"], 4)

    def test_keep_null_does_not_repair_cells(self):
        dataframe = pd.DataFrame(
            [
                {"id": 1, "phone": ""},
                {"id": 2, "phone": "N/A"},
            ]
        )
        rules = {
            "required_fields": ["id", "phone"],
            "null_values": ["", "N/A"],
            "field_rules": {
                "phone": {
                    "action": "keep_null",
                }
            },
        }

        repaired, report = process_dataframe(dataframe, rules)

        self.assertEqual(repaired.loc[0, "phone"], "")
        self.assertEqual(repaired.loc[1, "phone"], "N/A")
        self.assertEqual(report["missing_cells"], 2)
        self.assertEqual(report["repaired_cells"], 0)
        self.assertEqual(report["unrepaired_cells"], 2)

    def test_yaml_field_rules_drive_repairs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "rules.yaml"
            output_dir = tmp_path / "outputs"

            input_path.write_text(
                "id,name,country,phone\n"
                "1,,N/A,\n"
                "2,Alice,,13900139000\n",
                encoding="utf-8",
            )
            rules_path.write_text(
                f"""
required_fields:
  - id
  - name
  - country
  - phone
null_values:
  - ""
  - "N/A"
field_rules:
  name:
    action: fill_default
    value: UNKNOWN
  country:
    action: fill_custom
    value: CHINA
  phone:
    action: keep_null
output:
  output_dir: "{output_dir}"
  quality_report_name: "quality_report.json"
""",
                encoding="utf-8",
            )

            report = process_dataset(input_path, rules_path)
            saved_report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report["missing_cells"], 4)
        self.assertEqual(report["repaired_cells"], 3)
        self.assertEqual(report["unrepaired_cells"], 1)
        self.assertEqual(saved_report["repaired_cells"], 3)


class BoundaryCasesTest(unittest.TestCase):
    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "empty.csv"
            rules_path = tmp_path / "rules.yaml"
            input_path.write_text("", encoding="utf-8")
            write_repair_rules(rules_path)

            report = process_dataset(input_path, rules_path, tmp_path / "outputs")

        self.assertEqual(report["total_rows"], 0)
        self.assertEqual(report["total_fields"], 0)
        self.assertEqual(report["missing_cells"], 0)
        self.assertEqual(report["missing_fields"], ["id", "name", "phone"])

    def test_single_row_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "single_row.csv"
            rules_path = tmp_path / "rules.yaml"
            input_path.write_text("id,name,phone\n1,Tom,13800138000\n", encoding="utf-8")
            write_repair_rules(rules_path)

            report = process_dataset(input_path, rules_path, tmp_path / "outputs")

        self.assertEqual(report["total_rows"], 1)
        self.assertEqual(report["missing_cells"], 0)
        self.assertEqual(report["missing_fields"], [])

    def test_all_null_column(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "all_null_column.csv"
            rules_path = tmp_path / "rules.yaml"
            input_path.write_text(
                "id,name,phone\n"
                "1,Tom,\n"
                "2,Alice,N/A\n"
                "3,Chen,未知\n",
                encoding="utf-8",
            )
            write_repair_rules(rules_path)

            report = process_dataset(input_path, rules_path, tmp_path / "outputs")

        self.assertEqual(report["field_stats"]["phone"]["missing_cells"], 3)
        self.assertEqual(report["missing_cells"], 3)
        self.assertEqual(report["repaired_cells"], 0)
        self.assertEqual(report["unrepaired_cells"], 3)

    def test_all_null_file_with_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "all_null_file.csv"
            rules_path = tmp_path / "rules.yaml"
            input_path.write_text(
                "id,name,phone\n"
                ",,\n"
                "N/A,N/A,N/A\n",
                encoding="utf-8",
            )
            write_repair_rules(rules_path)

            report = process_dataset(input_path, rules_path, tmp_path / "outputs")

        self.assertEqual(report["total_rows"], 2)
        self.assertEqual(report["total_fields"], 3)
        self.assertEqual(report["missing_cells"], 6)
        self.assertEqual(report["repaired_cells"], 2)
        self.assertEqual(report["unrepaired_cells"], 4)

    def test_missing_all_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "missing_all_required.csv"
            rules_path = tmp_path / "rules.yaml"
            input_path.write_text("title,content\nA,hello\n", encoding="utf-8")
            write_repair_rules(rules_path)

            report = process_dataset(input_path, rules_path, tmp_path / "outputs")

        self.assertEqual(report["missing_fields"], ["id", "name", "phone"])
        self.assertEqual(report["total_rows"], 1)

    def test_invalid_rules_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "invalid_rules.yaml"
            input_path.write_text("id,name\n1,Tom\n", encoding="utf-8")
            rules_path.write_text(
                """
required_fields: id
null_values:
  - ""
""",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                process_dataset(input_path, rules_path, tmp_path / "outputs")

    def test_cli_invalid_rules_returns_json_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "input.csv"
            rules_path = tmp_path / "invalid_rules.yaml"
            input_path.write_text("id,name\n1,Tom\n", encoding="utf-8")
            rules_path.write_text(
                """
required_fields: id
null_values:
  - ""
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_DIR / "scripts" / "check_missing_values.py"),
                    str(input_path),
                    str(rules_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        error_payload = json.loads(result.stdout)
        self.assertFalse(error_payload["valid"])
        self.assertIn("required_fields 必须是列表", error_payload["error"])

    def test_large_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "large_input.csv"
            rules_path = tmp_path / "rules.yaml"
            rows = ["id,name,phone"]
            for index in range(1, 10001):
                name = "" if index % 10 == 0 else f"name_{index}"
                phone = "N/A" if index % 15 == 0 else f"138{index:08d}"
                rows.append(f"{index},{name},{phone}")
            input_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            write_repair_rules(rules_path)

            started = time.perf_counter()
            report = process_dataset(input_path, rules_path, tmp_path / "outputs")
            elapsed = time.perf_counter() - started
            saved_report = json.loads((tmp_path / "outputs" / "quality_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report["total_rows"], 10000)
        self.assertEqual(report["missing_cells"], 1666)
        self.assertEqual(report["repaired_cells"], 1000)
        self.assertEqual(report["unrepaired_cells"], 666)
        self.assertEqual(saved_report["total_rows"], 10000)
        self.assertLess(elapsed, 15.0)


if __name__ == "__main__":
    unittest.main()
