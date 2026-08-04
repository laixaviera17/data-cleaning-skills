#!/usr/bin/env python3
"""Run a synthetic deterministic Agent session and print its review routing."""

from __future__ import annotations

import json

import pandas as pd

from data_cleaning_skills import DataCleaningAgent


def main() -> int:
    dataframe = pd.DataFrame([{"id": "1", "source": ""}, {"id": "2", "source": "portal"}])
    rules = {
        "pipeline": {"steps": ["missing-value-checker"]},
        "required_fields": [{"field": "business_owner", "action": "mark"}],
        "unique_keys": {"keys": [["id"]]},
        "null_handling": {
            "null_values": [""],
            "strategies": [{"field": "source", "action": "fill", "fill_value": "unknown"}],
        },
        "date_rules": {"enabled": False, "fields": []},
        "phone_rules": {"enabled": False, "fields": []},
        "amount_rules": {"enabled": False, "fields": []},
    }

    run = DataCleaningAgent().run(dataframe, rules)
    payload = {
        "run_id": run.pipeline_result["run_id"],
        "execution_plan": list(run.plan.steps),
        "output_rows": len(run.dataframe),
        "evaluation": {
            "decision": run.evaluation.decision.value,
            "reasons": list(run.evaluation.reasons),
            "metrics": dict(run.evaluation.metrics),
        },
        "review_status": run.review.status.value if run.review else None,
        "event_phases": [event.phase for event in run.events],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
