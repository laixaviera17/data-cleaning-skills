import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from dictionary_file_utils import load_dataset  # noqa: E402
from validate_dictionary_values import normalize_dictionary_rules, process_dataframe, validate_dataset  # noqa: E402


def sample_dictionary_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"field_name": "status", "raw_value": "有效", "standard_value": "valid", "allowed": "true", "remark": "状态标准化"},
            {"field_name": "status", "raw_value": "无效", "standard_value": "invalid", "allowed": "true", "remark": "状态标准化"},
            {"field_name": "status", "raw_value": "禁用", "standard_value": "disabled", "allowed": "false", "remark": "不允许状态"},
            {"field_name": "category", "raw_value": "新闻", "standard_value": "news", "allowed": "true", "remark": "类别标准化"},
            {"field_name": "category", "raw_value": "财经", "standard_value": "finance", "allowed": "true", "remark": "类别标准化"},
        ]
    )


class DictionaryValueValidatorTest(unittest.TestCase):
    def test_process_dataframe_standardizes_values(self):
        dataframe = pd.DataFrame(
            [
                {"id": "1", "status": "有效", "category": "新闻"},
                {"id": "2", "status": "无效", "category": "财经"},
            ]
        )

        processed, report = process_dataframe(dataframe, sample_dictionary_dataframe())

        self.assertEqual(processed.loc[0, "status"], "valid")
        self.assertEqual(processed.loc[1, "category"], "finance")
        self.assertEqual(report["changed_values"], 4)
        self.assertEqual(len(report["changes"]), 4)

    def test_disallowed_unknown_and_missing_field_are_reported(self):
        dataframe = pd.DataFrame(
            [
                {"id": "1", "status": "禁用", "category": "未知类别"},
            ]
        )
        dictionary = pd.concat(
            [
                sample_dictionary_dataframe(),
                pd.DataFrame(
                    [
                        {
                            "field_name": "missing_column",
                            "raw_value": "x",
                            "standard_value": "x",
                            "allowed": "true",
                            "remark": "缺失字段测试",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

        processed, report = process_dataframe(dataframe, dictionary)

        self.assertEqual(processed.loc[0, "status"], "禁用")
        issue_types = {issue["issue_type"] for issue in report["issues"]}
        self.assertIn("disallowed_dictionary_value", issue_types)
        self.assertIn("unknown_dictionary_value", issue_types)
        self.assertIn("missing_field", issue_types)
        self.assertEqual(report["illegal_values"], 1)
        self.assertEqual(report["unknown_values"], 1)
        self.assertEqual(report["missing_fields"], 1)

    def test_invalid_dictionary_file_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "缺少必需列"):
            normalize_dictionary_rules(pd.DataFrame([{"field_name": "status"}]))

        with self.assertRaisesRegex(ValueError, "不能为空"):
            normalize_dictionary_rules(
                pd.DataFrame(columns=["field_name", "raw_value", "standard_value", "allowed", "remark"])
            )

        duplicate = pd.DataFrame(
            [
                {"field_name": "status", "raw_value": "有效", "standard_value": "valid", "allowed": "true", "remark": ""},
                {"field_name": "status", "raw_value": "有效", "standard_value": "valid2", "allowed": "true", "remark": ""},
            ]
        )
        with self.assertRaisesRegex(ValueError, "重复配置"):
            normalize_dictionary_rules(duplicate)

    def test_validate_dataset_supports_csv_json_and_jsonl_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dictionary_path = tmp_path / "dictionary.csv"
            sample_dictionary_dataframe().to_csv(dictionary_path, index=False)

            csv_input = tmp_path / "input.csv"
            json_input = tmp_path / "input.json"
            jsonl_input = tmp_path / "input.jsonl"
            csv_input.write_text("id,status,category\n1,有效,新闻\n", encoding="utf-8")
            json_input.write_text(
                json.dumps([{"id": "1", "status": "有效", "category": "新闻"}], ensure_ascii=False),
                encoding="utf-8",
            )
            jsonl_input.write_text('{"id": "1", "status": "有效", "category": "新闻"}\n', encoding="utf-8")

            for input_file in [csv_input, json_input, jsonl_input]:
                output_dir = tmp_path / f"out_{input_file.suffix[1:]}"
                outputs = validate_dataset(input_file, dictionary_path, output_dir)
                self.assertTrue(outputs["standardized_data"].is_file())
                self.assertTrue(outputs["dictionary_validation_report"].is_file())
                self.assertTrue(outputs["dictionary_issues"].is_file())
                self.assertTrue(outputs["dictionary_changes"].is_file())
                loaded = load_dataset(outputs["standardized_data"])
                self.assertEqual(loaded.loc[0, "status"], "valid")

    def test_empty_input_and_empty_dictionary_are_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            empty_input = tmp_path / "empty.csv"
            dictionary_path = tmp_path / "dictionary.csv"
            empty_dictionary = tmp_path / "empty_dictionary.csv"
            valid_input = tmp_path / "valid.csv"
            empty_input.write_text("", encoding="utf-8")
            sample_dictionary_dataframe().to_csv(dictionary_path, index=False)
            empty_dictionary.write_text("", encoding="utf-8")
            valid_input.write_text("id,status\n1,有效\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "输入文件为空"):
                validate_dataset(empty_input, dictionary_path, tmp_path / "out")
            with self.assertRaisesRegex(RuntimeError, "字典文件为空"):
                validate_dataset(valid_input, empty_dictionary, tmp_path / "out")


if __name__ == "__main__":
    unittest.main()
