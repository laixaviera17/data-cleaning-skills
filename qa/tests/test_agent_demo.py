from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]


def test_agent_demo_routes_missing_required_field_to_review():
    completed = subprocess.run(
        [sys.executable, str(WORKSPACE / "scripts" / "run_agent_demo.py")],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["execution_plan"] == ["missing-value-checker"]
    assert payload["evaluation"]["decision"] == "reject"
    assert payload["review_status"] == "pending"
    assert payload["event_phases"][-1] == "human_review"
