from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from package_cleaned_dataset import classify_artifact, package_dataset  # noqa: E402


class DeliveryPackagerTest(unittest.TestCase):
    def test_classifies_known_artifacts(self):
        self.assertEqual(classify_artifact(Path("cleaning_log.csv")), "logs")
        self.assertEqual(classify_artifact(Path("catalog_metadata.json")), "metadata")
        self.assertEqual(classify_artifact(Path("dataset_readme.md")), "docs")
        self.assertEqual(classify_artifact(Path("quality_report.json")), "reports")

    def test_package_dataset_writes_manifest_checksums_and_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "out"
            result = package_dataset(
                ROOT / "examples" / "cleaned_data.csv",
                output_dir,
                artifacts=[
                    ROOT / "examples" / "cleaning_summary.json",
                    ROOT / "examples" / "cleaning_log.csv",
                    ROOT / "examples" / "dataset_readme.md",
                    ROOT / "examples" / "catalog_metadata.json",
                ],
                dataset_name="demo_dataset",
            )

            manifest_path = Path(result["manifest_path"])
            checksums_path = Path(result["checksums_path"])
            archive_path = Path(result["archive_path"])

            self.assertTrue(manifest_path.exists())
            self.assertTrue(checksums_path.exists())
            self.assertTrue(archive_path.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_name"], "demo_dataset")
            self.assertEqual(manifest["file_count"], 5)

            with checksums_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 5)

            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
            self.assertIn("data/cleaned_data.csv", names)
            self.assertIn("manifest.json", names)

    def test_duplicate_artifact_names_are_preserved_with_unique_targets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            artifact_a = tmp_path / "a" / "quality_report.json"
            artifact_b = tmp_path / "b" / "quality_report.json"
            artifact_a.parent.mkdir()
            artifact_b.parent.mkdir()
            artifact_a.write_text('{"source": "a"}', encoding="utf-8")
            artifact_b.write_text('{"source": "b"}', encoding="utf-8")

            result = package_dataset(
                ROOT / "examples" / "cleaned_data.csv",
                tmp_path / "out",
                artifacts=[artifact_a, artifact_b],
            )
            paths = [record["path"] for record in result["manifest"]["files"]]

        self.assertIn("reports/quality_report.json", paths)
        self.assertIn("reports/quality_report_2.json", paths)

    def test_artifact_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "artifact_dir"
            artifact_dir.mkdir()

            with self.assertRaises(ValueError):
                package_dataset(ROOT / "examples" / "cleaned_data.csv", tmpdir, artifacts=[artifact_dir])

    def test_manifest_file_records_have_required_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = package_dataset(ROOT / "examples" / "cleaned_data.csv", tmpdir)
            record = result["manifest"]["files"][0]

        self.assertEqual(set(record), {"path", "role", "size_bytes", "sha256", "source_path"})
        self.assertEqual(record["role"], "data")
        self.assertEqual(len(record["sha256"]), 64)

    def test_missing_cleaned_data_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                package_dataset(ROOT / "examples" / "missing.csv", tmpdir)


if __name__ == "__main__":
    unittest.main()
