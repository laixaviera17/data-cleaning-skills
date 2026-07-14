from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_dataset_documentation import generate_dataset_documentation, load_records, summarize_report  # noqa: E402


class DatasetDocumentationGeneratorTest(unittest.TestCase):
    def test_load_records_reads_csv(self):
        records = load_records(ROOT / "examples" / "cleaned_data.csv")
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["name"], "Alice")

    def test_generate_documentation_writes_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_dataset_documentation(
                ROOT / "examples" / "cleaned_data.csv",
                tmpdir,
                dataset_name="demo_dataset",
                reports=[
                    ROOT / "examples" / "cleaning_summary.json",
                    ROOT / "examples" / "issue_rows.csv",
                ],
            )
            doc_path = Path(result["documentation_path"])
            self.assertTrue(doc_path.exists())
            text = doc_path.read_text(encoding="utf-8")
            self.assertIn("# demo_dataset 数据集说明文档", text)
            self.assertIn("记录数：3", text)
            self.assertIn("| amount | number | 1 |", text)
            self.assertIn("cleaning_summary.json", text)
            self.assertEqual(result["field_count"], 4)

    def test_generate_documentation_without_reports_mentions_missing_attachments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_dataset_documentation(ROOT / "examples" / "cleaned_data.csv", tmpdir)
            text = Path(result["documentation_path"]).read_text(encoding="utf-8")

        self.assertIn("未提供清洗日志", text)
        self.assertEqual(result["report_count"], 0)

    def test_summarize_csv_report_handles_empty_file_with_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "issue_rows.csv"
            report_path.write_text("row,field,value,issue_type,reason\n", encoding="utf-8")
            summary = summarize_report(report_path)

        self.assertEqual(summary["type"], "csv")
        self.assertEqual(summary["rows"], 0)
        self.assertEqual(summary["fields"], [])

    def test_jsonl_input_is_supported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir) / "input.jsonl"
            data_path.write_text('{"id": 1, "active": true}\n{"id": 2, "active": false}\n', encoding="utf-8")
            result = generate_dataset_documentation(data_path, tmpdir, dataset_name="jsonl_demo")
            text = Path(result["documentation_path"]).read_text(encoding="utf-8")

        self.assertIn("# jsonl_demo 数据集说明文档", text)
        self.assertIn("| active | boolean | 0 |", text)

    def test_bad_json_report_raises_decode_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "bad.json"
            report_path.write_text("{bad json", encoding="utf-8")

            with self.assertRaises(ValueError):
                summarize_report(report_path)

    def test_missing_input_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                generate_dataset_documentation(ROOT / "examples" / "missing.csv", tmpdir)


if __name__ == "__main__":
    unittest.main()
