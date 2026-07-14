import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from compare_datasets import compare_dataframes, compare_dataset_files  # noqa: E402


class DatasetDiffComparatorTest(unittest.TestCase):
    def test_compare_dataframes_detects_added_removed_and_changed(self):
        before = pd.DataFrame(
            [
                {"id": "1", "name": "张三", "status": "有效", "score": "80"},
                {"id": "2", "name": "李四", "status": "无效", "score": "70"},
                {"id": "3", "name": "王五", "status": "有效", "score": "60"},
            ]
        )
        after = pd.DataFrame(
            [
                {"id": "1", "name": "张三", "status": "valid", "score": "80"},
                {"id": "2", "name": "李四", "status": "invalid", "score": "75"},
                {"id": "4", "name": "赵六", "status": "valid", "score": "90"},
            ]
        )

        diff = compare_dataframes(before, after, ["id"])

        self.assertEqual(diff["summary"]["before_rows"], 3)
        self.assertEqual(diff["summary"]["after_rows"], 3)
        self.assertEqual(diff["summary"]["added_rows"], 1)
        self.assertEqual(diff["summary"]["removed_rows"], 1)
        self.assertEqual(diff["summary"]["changed_records"], 2)
        self.assertEqual(diff["summary"]["changed_cells"], 3)
        self.assertEqual(diff["added_rows"].loc[0, "record_key"], "4")
        self.assertEqual(diff["removed_rows"].loc[0, "record_key"], "3")
        self.assertIn("status", set(diff["field_change_summary"]["field"]))
        self.assertIn("lineage_fields", diff["summary"])

    def test_compare_dataset_files_supports_csv_json_and_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            before_records = [
                {"id": "1", "status": "有效"},
                {"id": "2", "status": "无效"},
            ]
            after_records = [
                {"id": "1", "status": "valid"},
                {"id": "3", "status": "valid"},
            ]

            for suffix in ["csv", "json", "jsonl"]:
                before_path = tmp_path / f"before.{suffix}"
                after_path = tmp_path / f"after.{suffix}"
                if suffix == "csv":
                    pd.DataFrame(before_records).to_csv(before_path, index=False)
                    pd.DataFrame(after_records).to_csv(after_path, index=False)
                elif suffix == "json":
                    before_path.write_text(json.dumps(before_records, ensure_ascii=False), encoding="utf-8")
                    after_path.write_text(json.dumps(after_records, ensure_ascii=False), encoding="utf-8")
                else:
                    before_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in before_records) + "\n", encoding="utf-8")
                    after_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in after_records) + "\n", encoding="utf-8")

                outputs = compare_dataset_files(before_path, after_path, "id", tmp_path / f"out_{suffix}")
                self.assertTrue(outputs["diff_summary"].is_file())
                self.assertTrue(outputs["added_rows"].is_file())
                self.assertTrue(outputs["removed_rows"].is_file())
                self.assertTrue(outputs["changed_rows"].is_file())
                self.assertTrue(outputs["field_change_summary"].is_file())

    def test_missing_or_duplicate_key_fields_raise_clear_errors(self):
        before = pd.DataFrame([{"id": "1", "name": "张三"}])
        after_missing = pd.DataFrame([{"name": "张三"}])
        after_duplicate = pd.DataFrame([{"id": "1"}, {"id": "1"}])

        with self.assertRaisesRegex(ValueError, "清洗后数据缺少主键字段"):
            compare_dataframes(before, after_missing, ["id"])
        with self.assertRaisesRegex(ValueError, "清洗后数据主键重复"):
            compare_dataframes(before, after_duplicate, ["id"])

    def test_no_differences_outputs_empty_diff_tables(self):
        before = pd.DataFrame([{"id": "1", "name": "张三"}])
        after = pd.DataFrame([{"id": "1", "name": "张三"}])

        diff = compare_dataframes(before, after, ["id"])

        self.assertEqual(diff["summary"]["added_rows"], 0)
        self.assertEqual(diff["summary"]["removed_rows"], 0)
        self.assertEqual(diff["summary"]["changed_cells"], 0)
        self.assertEqual(
            list(diff["changed_rows"].columns),
            [
                "record_key",
                "field",
                "before_value",
                "after_value",
                "before_source_row",
                "after_source_row",
                "before_record_hash",
                "after_record_hash",
            ],
        )


if __name__ == "__main__":
    unittest.main()
