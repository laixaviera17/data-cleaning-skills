from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[2]
DEMO_SCRIPT = WORKSPACE / "scripts" / "run_recruiter_demo.py"


def load_demo_module():
    spec = importlib.util.spec_from_file_location("recruiter_demo", DEMO_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError("无法加载招聘方演示脚本")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecruiterDemoTest(unittest.TestCase):
    def test_demo_generates_required_artifacts_from_public_mock_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "demo-output"
            result = load_demo_module().run_demo(output_dir)

            for name in [
                "cleaned_data.csv",
                "issue_rows.csv",
                "cleaning_log.csv",
                "delivery_manifest.json",
                "summary.json",
            ]:
                self.assertTrue((output_dir / name).is_file(), name)
            self.assertTrue((output_dir / "delivery" / "delivery_package.zip").is_file())

            summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
            self.assertEqual(summary["input_rows"], 16)
            self.assertGreater(summary["issue_rows"], 0)
            self.assertEqual(summary["artifacts"]["cleaned_data"], "cleaned_data.csv")
            self.assertIn("cleaned-dataset-delivery-packager", summary["reused_modules"])
