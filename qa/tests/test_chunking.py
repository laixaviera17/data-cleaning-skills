from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from data_cleaning_skills import SkillConfigurationError, iter_clean_csv


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


def test_chunked_csv_preserves_global_exact_key_uniqueness(tmp_path: Path):
    input_path = tmp_path / "input.csv"
    pd.DataFrame(
        [
            {"id": "1", "source": ""},
            {"id": "2", "source": "portal"},
            {"id": "1", "source": "duplicate-in-next-chunk"},
            {"id": "3", "source": ""},
            {"id": "4", "source": "portal"},
        ]
    ).to_csv(input_path, index=False)

    chunks = list(iter_clean_csv(input_path, _rules(), chunksize=2))
    combined = pd.concat([chunk.dataframe for chunk in chunks], ignore_index=True)

    assert list(combined["id"]) == [1, 2, 3, 4]
    assert combined.loc[2, "source"] == "unknown"
    assert sum(chunk.metrics.cross_chunk_duplicate_rows for chunk in chunks) == 1
    assert chunks[1].report["duplicate_rows"] == 1


@pytest.mark.parametrize(
    "unsafe_config, message",
    [
        ({"field_mapping": {"enabled": True}}, "field_mapping"),
        ({"unique_keys": {"similarity": {"enabled": True}}}, "similarity"),
    ],
)
def test_chunked_csv_rejects_rules_without_equivalent_semantics(
    tmp_path: Path,
    unsafe_config: dict[str, Any],
    message: str,
):
    input_path = tmp_path / "input.csv"
    input_path.write_text("id,source\n1,portal\n", encoding="utf-8")
    rules = _rules()
    rules.update(unsafe_config)

    with pytest.raises(SkillConfigurationError, match=message):
        list(iter_clean_csv(input_path, rules, chunksize=1))


def test_chunked_csv_rejects_unknown_configuration(tmp_path: Path):
    input_path = tmp_path / "input.csv"
    input_path.write_text("id,source\n1,portal\n", encoding="utf-8")
    rules = _rules()
    rules["field_mappng"] = {"enabled": True}

    with pytest.raises(SkillConfigurationError, match="field_mappng"):
        list(iter_clean_csv(input_path, rules, chunksize=1))
