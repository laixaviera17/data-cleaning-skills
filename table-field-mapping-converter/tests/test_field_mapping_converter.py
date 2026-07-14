import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from field_mapping_file_utils import load_dataset  # noqa: E402
from map_fields import map_dataset, normalize_mapping_rules, process_dataframe  # noqa: E402


def sample_mapping_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_field": "user_id",
                "target_field": "id",
                "target_type": "string",
                "required": "true",
                "default_value": "",
                "description": "用户编号",
            },
            {
                "source_field": "user_name",
                "target_field": "name",
                "target_type": "string",
                "required": "true",
                "default_value": "",
                "description": "用户名称",
            },
            {
                "source_field": "phone_no",
                "target_field": "phone",
                "target_type": "string",
                "required": "false",
                "default_value": "",
                "description": "手机号",
            },
        ]
    )


class FieldMappingConverterTest(unittest.TestCase):
    def test_process_dataframe_maps_fields_and_keeps_unmapped_fields(self):
        dataframe = pd.DataFrame(
            [
                {"user_id": "1", "user_name": "张三", "phone_no": "13800138000", "source": "site_a"},
                {"user_id": "2", "user_name": "李四", "phone_no": "13900139000", "source": "site_b"},
            ]
        )

        mapped, report = process_dataframe(dataframe, sample_mapping_dataframe())

        self.assertEqual(list(mapped.columns), ["id", "name", "phone", "source"])
        self.assertEqual(mapped.loc[0, "name"], "张三")
        self.assertEqual(report["mapped_fields"], 3)
        self.assertEqual(report["unmapped_fields"], 1)
        self.assertEqual(report["unmapped_field_records"][0]["field"], "source")

    def test_missing_required_source_field_can_fill_default(self):
        dataframe = pd.DataFrame([{"user_id": "1"}])
        mapping = pd.DataFrame(
            [
                {
                    "source_field": "country",
                    "target_field": "country_code",
                    "target_type": "string",
                    "required": "true",
                    "default_value": "CN",
                    "description": "国家代码",
                }
            ]
        )

        mapped, report = process_dataframe(dataframe, mapping)

        self.assertEqual(mapped.loc[0, "country_code"], "CN")
        self.assertEqual(report["missing_required_fields"], 1)
        self.assertEqual(report["issues"][0]["issue_type"], "missing_required_source_field")
        self.assertEqual(report["issues"][0]["action"], "fill_default")

    def test_duplicate_target_fields_are_reported_without_overwrite(self):
        dataframe = pd.DataFrame([{"a": "1", "b": "2"}])
        mapping = pd.DataFrame(
            [
                {
                    "source_field": "a",
                    "target_field": "same",
                    "target_type": "string",
                    "required": "false",
                    "default_value": "",
                    "description": "",
                },
                {
                    "source_field": "b",
                    "target_field": "same",
                    "target_type": "string",
                    "required": "false",
                    "default_value": "",
                    "description": "",
                },
            ]
        )

        mapped, report = process_dataframe(dataframe, mapping)

        self.assertEqual(list(mapped.columns), ["a", "b"])
        self.assertEqual(report["duplicate_target_fields"], 2)
        self.assertEqual({issue["issue_type"] for issue in report["issues"]}, {"duplicate_target_field"})

    def test_invalid_mapping_file_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "缺少必需列"):
            normalize_mapping_rules(pd.DataFrame([{"source_field": "a"}]))

        with self.assertRaisesRegex(ValueError, "不能为空"):
            normalize_mapping_rules(pd.DataFrame(columns=["source_field", "target_field", "target_type", "required", "default_value", "description"]))

    def test_map_dataset_supports_csv_json_and_jsonl_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            mapping_path = tmp_path / "mapping.csv"
            sample_mapping_dataframe().to_csv(mapping_path, index=False)

            csv_input = tmp_path / "input.csv"
            json_input = tmp_path / "input.json"
            jsonl_input = tmp_path / "input.jsonl"
            csv_input.write_text("user_id,user_name,phone_no,source\n1,张三,13800138000,site_a\n", encoding="utf-8")
            json_input.write_text(
                json.dumps([{"user_id": "1", "user_name": "张三", "phone_no": "13800138000", "source": "site_a"}], ensure_ascii=False),
                encoding="utf-8",
            )
            jsonl_input.write_text('{"user_id": "1", "user_name": "张三", "phone_no": "13800138000", "source": "site_a"}\n', encoding="utf-8")

            for input_file in [csv_input, json_input, jsonl_input]:
                output_dir = tmp_path / f"out_{input_file.suffix[1:]}"
                outputs = map_dataset(input_file, mapping_path, output_dir)
                self.assertTrue(outputs["mapped_data"].is_file())
                self.assertTrue(outputs["field_mapping_report"].is_file())
                self.assertTrue(outputs["unmapped_fields"].is_file())
                self.assertTrue(outputs["mapping_issues"].is_file())
                loaded = load_dataset(outputs["mapped_data"])
                self.assertEqual(list(loaded.columns), ["id", "name", "phone", "source"])

    def test_empty_input_and_empty_mapping_are_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            empty_input = tmp_path / "empty.csv"
            mapping_path = tmp_path / "mapping.csv"
            empty_mapping = tmp_path / "empty_mapping.csv"
            empty_input.write_text("", encoding="utf-8")
            sample_mapping_dataframe().to_csv(mapping_path, index=False)
            empty_mapping.write_text("", encoding="utf-8")
            valid_input = tmp_path / "valid.csv"
            valid_input.write_text("user_id,user_name\n1,张三\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "输入文件为空"):
                map_dataset(empty_input, mapping_path, tmp_path / "out")
            with self.assertRaisesRegex(RuntimeError, "字段映射文件为空"):
                map_dataset(valid_input, empty_mapping, tmp_path / "out")


if __name__ == "__main__":
    unittest.main()
