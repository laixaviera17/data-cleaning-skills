import json
import tempfile
import unittest
from pathlib import Path
import sys

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from pipeline_file_utils import (  # noqa: E402
    file_exists,
    load_csv,
    load_json,
    load_jsonl,
    save_csv,
    save_json,
    save_jsonl,
)


class FileUtilsTest(unittest.TestCase):
    def test_load_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sample.csv"
            csv_path.write_text("id,name\n1,张三\n2,李四\n", encoding="utf-8")

            dataframe = load_csv(csv_path)

        self.assertEqual(list(dataframe.columns), ["id", "name"])
        self.assertEqual(len(dataframe), 2)
        self.assertEqual(dataframe.loc[0, "name"], "张三")

    def test_load_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "sample.json"
            json_path.write_text(
                json.dumps(
                    [{"id": 1, "name": "张三"}, {"id": 2, "name": "李四"}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            dataframe = load_json(json_path)

        self.assertEqual(list(dataframe.columns), ["id", "name"])
        self.assertEqual(len(dataframe), 2)
        self.assertEqual(dataframe.loc[1, "name"], "李四")

    def test_load_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "sample.jsonl"
            jsonl_path.write_text(
                '{"id": 1, "name": "张三"}\n{"id": 2, "name": "李四"}\n',
                encoding="utf-8",
            )

            dataframe = load_jsonl(jsonl_path)

        self.assertEqual(list(dataframe.columns), ["id", "name"])
        self.assertEqual(len(dataframe), 2)
        self.assertEqual(dataframe.loc[0, "id"], 1)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "missing.csv"

            self.assertFalse(file_exists(missing_path))
            with self.assertRaises(FileNotFoundError):
                load_csv(missing_path)

    def test_save_exports_successfully(self):
        dataframe = pd.DataFrame(
            [
                {"id": 1, "name": "张三"},
                {"id": 2, "name": "李四"},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "nested" / "outputs"
            csv_path = output_dir / "out.csv"
            json_path = output_dir / "out.json"
            jsonl_path = output_dir / "out.jsonl"

            save_csv(dataframe, csv_path)
            save_json(dataframe, json_path)
            save_jsonl(dataframe, jsonl_path)

            self.assertTrue(csv_path.is_file())
            self.assertTrue(json_path.is_file())
            self.assertTrue(jsonl_path.is_file())

            csv_loaded = load_csv(csv_path)
            json_loaded = load_json(json_path)
            jsonl_loaded = load_jsonl(jsonl_path)

        self.assertEqual(len(csv_loaded), 2)
        self.assertEqual(len(json_loaded), 2)
        self.assertEqual(len(jsonl_loaded), 2)


if __name__ == "__main__":
    unittest.main()
