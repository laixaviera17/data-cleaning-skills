import tempfile
import unittest
from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from validate_rules import validate_file, validate_rules  # noqa: E402


VALID_RULES = {
    "required_fields": [
        {"field": "id", "allow_blank": False, "action": "mark"},
        {"field": "content", "allow_blank": False, "action": "drop"},
    ],
    "unique_keys": {
        "enabled": True,
        "keys": [["id"], ["title", "source"]],
        "keep": "first",
        "issue_action": "export",
    },
    "null_handling": {
        "null_values": ["", "null", "N/A", "未知"],
        "strategies": [
            {"field": "content", "action": "drop"},
            {"field": "source", "action": "fill", "fill_value": "unknown"},
        ],
    },
    "date_rules": {
        "enabled": True,
        "date_format": "YYYY-MM-DD",
        "fields": [
            {
                "field": "publish_date",
                "input_formats": ["YYYY-MM-DD", "YYYY/MM/DD"],
                "invalid_action": "mark",
            }
        ],
    },
    "phone_rules": {
        "enabled": True,
        "phone_pattern": "^1[3-9][0-9]{9}$",
        "fields": [{"field": "phone", "invalid_action": "mark"}],
    },
    "amount_rules": {
        "enabled": True,
        "amount_precision": 2,
        "fields": [{"field": "amount", "invalid_action": "mark"}],
    },
}


class ValidateRulesTest(unittest.TestCase):
    def test_valid_rules(self):
        result = validate_rules(VALID_RULES)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])

    def test_set_null_action_is_supported_for_invalid_format_values(self):
        config = dict(VALID_RULES)
        config["amount_rules"] = {
            "enabled": True,
            "amount_precision": 2,
            "fields": [{"field": "amount", "invalid_action": "set_null"}],
        }

        result = validate_rules(config)

        self.assertTrue(result["valid"], result["errors"])

    def test_similarity_dedup_config_is_supported(self):
        config = dict(VALID_RULES)
        config["unique_keys"] = {
            "enabled": True,
            "keys": [["id"]],
            "keep": "first",
            "issue_action": "export",
            "similarity": {
                "enabled": True,
                "fields": ["title"],
                "threshold": 0.9,
            },
        }
        config["null_handling"] = {
            "null_values": ["", "N/A"],
            "strategies": [
                {"field": "content", "action": "drop"},
                {"field": "score", "action": "mean"},
                {"field": "source", "action": "ffill"},
            ],
        }

        result = validate_rules(config)

        self.assertTrue(result["valid"], result["errors"])

    def test_missing_required_section(self):
        config = dict(VALID_RULES)
        del config["required_fields"]

        result = validate_rules(config)

        self.assertFalse(result["valid"])
        self.assertIn("缺少必需配置项: required_fields", result["errors"])

    def test_type_error(self):
        config = dict(VALID_RULES)
        config["required_fields"] = {"field": "id"}
        config["unique_keys"] = "id"
        config["null_handling"] = []

        result = validate_rules(config)

        self.assertFalse(result["valid"])
        self.assertIn("required_fields 必须为 list 类型", result["errors"])
        self.assertIn("unique_keys 必须为 list 类型，或包含 keys 列表的 dict 类型", result["errors"])
        self.assertIn("null_handling 必须为 dict 类型", result["errors"])

    def test_empty_config(self):
        result = validate_rules({})

        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["配置文件不能为空"])

    def test_empty_rule_values(self):
        config = dict(VALID_RULES)
        config["date_rules"] = {"enabled": True, "date_format": "", "fields": []}
        config["phone_rules"] = {"enabled": True, "phone_pattern": "", "fields": []}
        config["amount_rules"] = {"enabled": True, "amount_precision": "2", "fields": []}

        result = validate_rules(config)

        self.assertFalse(result["valid"])
        self.assertIn("date_rules.date_format 或 date_rules.target_format 不能为空", result["errors"])
        self.assertIn("phone_rules.phone_pattern 不能为空", result["errors"])
        self.assertIn("amount_rules.amount_precision 必须为整数", result["errors"])

    def test_validate_yaml_file(self):
        yaml_text = """
required_fields:
  - field: "id"
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
      action: "fill"
      fill_value: "unknown"
date_rules:
  enabled: true
  date_format: "YYYY-MM-DD"
  fields:
    - field: "publish_date"
      input_formats:
        - "YYYY-MM-DD"
      invalid_action: "mark"
phone_rules:
  enabled: true
  phone_pattern: "^1[3-9][0-9]{9}$"
  fields:
    - field: "phone"
      invalid_action: "mark"
amount_rules:
  enabled: true
  amount_precision: 2
  fields:
    - field: "amount"
      invalid_action: "mark"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            rule_file = Path(tmpdir) / "rules.yaml"
            rule_file.write_text(yaml_text, encoding="utf-8")

            result = validate_file(rule_file)

        self.assertTrue(result["valid"], result["errors"])


if __name__ == "__main__":
    unittest.main()
