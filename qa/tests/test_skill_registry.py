from __future__ import annotations

import pandas as pd

from data_cleaning_skills import SkillResult, UnknownSkillError, build_execution_plan, get_default_registry


def test_default_registry_exposes_all_atomic_cleaning_skills():
    registry = get_default_registry()

    assert registry.names() == (
        "abnormal-value-detector",
        "field-dictionary-value-validator",
        "format-standardizer",
        "missing-value-checker",
        "table-field-mapping-converter",
    )


def test_registry_returns_normalized_skill_result():
    registry = get_default_registry()
    result = registry.get("missing-value-checker").execute(
        pd.DataFrame([{"id": "1", "source": ""}]),
        {
            "required_fields": ["id"],
            "null_values": [""],
            "field_rules": {"source": {"action": "fill", "value": "unknown"}},
        },
    )

    assert isinstance(result, SkillResult)
    assert result.dataframe.loc[0, "source"] == "unknown"


def test_registry_rejects_unknown_skill():
    registry = get_default_registry()

    try:
        registry.get("not-a-skill")
    except UnknownSkillError:
        pass
    else:
        raise AssertionError("UnknownSkillError was not raised")


def test_execution_plan_topologically_orders_selected_skills():
    registry = get_default_registry()

    plan = build_execution_plan(
        ["abnormal-value-detector", "missing-value-checker", "format-standardizer"],
        registry.names(),
    )

    assert plan.steps == (
        "missing-value-checker",
        "format-standardizer",
        "abnormal-value-detector",
    )
