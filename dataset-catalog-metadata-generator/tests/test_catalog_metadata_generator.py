from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_catalog_metadata import generate_catalog_metadata, load_records, validate_required_metadata  # noqa: E402


class CatalogMetadataGeneratorTest(unittest.TestCase):
    def test_load_records_reads_csv(self):
        records = load_records(ROOT / "examples" / "cleaned_data.csv")
        self.assertEqual(len(records), 3)
        self.assertEqual(records[1]["category"], "B")

    def test_generate_catalog_metadata_writes_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_catalog_metadata(
                ROOT / "examples" / "cleaned_data.csv",
                tmpdir,
                config_path=ROOT / "examples" / "metadata_config.json",
                artifacts=[ROOT / "examples" / "quality_report.json"],
            )
            metadata_path = Path(result["metadata_path"])
            self.assertTrue(metadata_path.exists())
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["dataset_name"], "demo_dataset")
            self.assertEqual(metadata["record_count"], 3)
            self.assertEqual(metadata["field_count"], 4)
            self.assertEqual(metadata["authorization_type"], "controlled")
            self.assertEqual(metadata["schema"][3]["missing_cells"], 1)
            self.assertEqual(len(metadata["artifacts"]), 1)
            self.assertEqual(metadata["catalog_standard"], "NDI-TR-2025-06")
            self.assertEqual(metadata["standard_field_mapping"]["dataset_title"], "dataset_name")
            self.assertTrue(metadata["required_field_status"]["valid"])

    def test_default_metadata_reports_missing_required_descriptive_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_catalog_metadata(ROOT / "examples" / "cleaned_data.csv", tmpdir)
            status = result["metadata"]["required_field_status"]

        self.assertFalse(status["valid"])
        self.assertIn("description", status["missing_fields"])
        self.assertIn("source", status["missing_fields"])
        self.assertIn("license", status["missing_fields"])

    def test_validate_required_metadata_flags_empty_inventory(self):
        status = validate_required_metadata(
            {
                "dataset_id": "demo",
                "dataset_name": "demo",
                "description": "desc",
                "version": "1.0.0",
                "source": "sample",
                "license": "internal",
                "authorization_type": "controlled",
                "generated_at": "2026-06-17T00:00:00Z",
                "format": "csv",
                "record_count": 0,
                "field_count": 0,
                "schema": [],
                "files": [],
            }
        )

        self.assertFalse(status["valid"])
        self.assertIn("schema", status["missing_fields"])
        self.assertIn("files", status["missing_fields"])

    def test_bad_json_config_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "metadata_config.json"
            config_path.write_text("[not-object]", encoding="utf-8")

            with self.assertRaises(json.JSONDecodeError):
                generate_catalog_metadata(ROOT / "examples" / "cleaned_data.csv", tmpdir, config_path=config_path)

    def test_jsonl_input_is_supported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir) / "input.jsonl"
            data_path.write_text('{"id": 1, "name": "A"}\n{"id": 2, "name": ""}\n', encoding="utf-8")
            result = generate_catalog_metadata(data_path, tmpdir, dataset_name="jsonl_demo")

        self.assertEqual(result["metadata"]["format"], "jsonl")
        self.assertEqual(result["metadata"]["record_count"], 2)
        self.assertEqual(result["metadata"]["schema"][1]["missing_cells"], 1)

    def test_missing_input_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                generate_catalog_metadata(ROOT / "examples" / "missing.csv", tmpdir)


if __name__ == "__main__":
    unittest.main()
