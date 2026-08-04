from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from data_cleaning_skills import (
    DataCleaningAgent,
    EvaluationDecision,
    EvaluationPolicy,
    QualityEvaluator,
    ReviewStatus,
    SessionMemory,
    SkillConfigurationError,
    atomic_tool_catalog,
    execute_atomic_tool,
    resolve_review,
)


def _rules() -> dict[str, Any]:
    return {
        "pipeline": {"steps": ["missing-value-checker"]},
        "required_fields": [{"field": "id", "action": "mark"}],
        "unique_keys": {"keys": [["id"]]},
        "null_handling": {
            "null_values": [""],
            "strategies": [{"field": "source", "action": "fill", "fill_value": "unknown"}],
        },
        "date_rules": {"enabled": False, "fields": []},
        "phone_rules": {"enabled": False, "fields": []},
        "amount_rules": {"enabled": False, "fields": []},
    }


def test_atomic_tool_catalog_has_machine_readable_contracts():
    tools = atomic_tool_catalog()

    assert len(tools) == 5
    assert tools[0].input_schema["required"] == ["records", "rules"]
    assert tools[-1].output_schema["required"] == ["records", "report"]


def test_atomic_tool_boundary_accepts_and_returns_json_safe_records():
    payload = {
        "records": [{"id": "1", "source": ""}],
        "rules": {
            "required_fields": ["id"],
            "null_values": [""],
            "field_rules": {"source": {"action": "fill", "value": "unknown"}},
        },
    }
    tool = next(item for item in atomic_tool_catalog() if item.name == "missing-value-checker")
    Draft202012Validator(tool.input_schema).validate(payload)

    output = execute_atomic_tool("missing-value-checker", payload)

    Draft202012Validator(tool.output_schema).validate(output)
    assert output["records"] == [{"id": "1", "source": "unknown"}]
    assert isinstance(output["report"], dict)


def test_agent_coordinates_plan_execution_memory_and_passing_evaluation():
    agent = DataCleaningAgent(
        evaluator=QualityEvaluator(EvaluationPolicy(max_quarantine_rate=0, max_abnormal_rate=0))
    )
    dataframe = pd.DataFrame([{"id": "1", "source": ""}])

    result = agent.run(dataframe, _rules())

    assert result.plan.steps == ("missing-value-checker",)
    assert result.dataframe.loc[0, "source"] == "unknown"
    assert result.evaluation.decision is EvaluationDecision.PASS
    assert result.review is None
    assert [event.phase for event in result.events] == ["validation", "planner", "executor", "evaluation"]


def test_agent_routes_threshold_failure_to_human_review():
    agent = DataCleaningAgent()
    dataframe = pd.DataFrame([{"id": "1", "source": ""}])
    rules = _rules()
    rules["required_fields"] = [{"field": "missing_column", "action": "mark"}]

    result = agent.run(dataframe, rules)

    assert result.evaluation.decision is EvaluationDecision.REJECT
    assert result.review is not None
    resolved = resolve_review(result.review, ReviewStatus.CHANGES_REQUESTED, "reviewer-01", "Fix schema")
    assert resolved.status is ReviewStatus.CHANGES_REQUESTED
    assert resolved.reviewer == "reviewer-01"
    with pytest.raises(ValueError, match="already been resolved"):
        resolve_review(resolved, ReviewStatus.APPROVED, "reviewer-02", "")


def test_session_memory_is_bounded():
    memory = SessionMemory(max_events=2)
    memory.record("one", "first")
    memory.record("two", "second")
    memory.record("three", "third")

    assert [event.phase for event in memory.snapshot()] == ["two", "three"]


def test_agent_rejects_invalid_rules_before_planning_or_execution():
    agent = DataCleaningAgent()
    invalid_rules = _rules()
    invalid_rules["field_mappng"] = {"enabled": True}

    with pytest.raises(SkillConfigurationError, match="field_mappng"):
        agent.run(pd.DataFrame([{"id": "1", "source": "portal"}]), invalid_rules)

    assert agent.memory.snapshot() == ()
