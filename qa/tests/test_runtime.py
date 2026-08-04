from __future__ import annotations

import json
import logging

from data_cleaning_skills import JsonLogFormatter, new_run_id


def test_new_run_id_preserves_explicit_correlation_id():
    assert new_run_id(" hiring-demo-01 ") == "hiring-demo-01"
    assert len(new_run_id()) == 32


def test_json_log_formatter_emits_machine_readable_context():
    record = logging.LogRecord(
        name="data_cleaning_skills.pipeline",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="skill finished",
        args=(),
        exc_info=None,
    )
    record.run_id = "run-01"
    record.skill = "missing-value-checker"
    record.result = "success"

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["run_id"] == "run-01"
    assert payload["skill"] == "missing-value-checker"
    assert payload["result"] == "success"
    assert payload["message"] == "skill finished"
