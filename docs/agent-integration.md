# Agent integration

## Trusted boundary

The runtime is deterministic. An LLM may translate a user's intent into candidate rules, but it must not execute arbitrary code, invent unregistered Skill names, override validation failures, or make the final quality decision.

```text
User intent
  → optional LLM rule proposal
  → deterministic rule validation
  → Planner / Registry / Executor
  → threshold Evaluation
  → pass or Human Review Packet
```

## Tool contract

`atomic_tool_catalog()` exposes five atomic tools with JSON Schema-compatible payloads. Inputs use JSON-safe `records` plus `rules`; outputs use processed `records` plus a structured `report`. `execute_atomic_tool()` performs the DataFrame conversion inside the trusted boundary and rejects malformed payloads or unknown tools.

```python
from data_cleaning_skills import execute_atomic_tool

output = execute_atomic_tool(
    "missing-value-checker",
    {
        "records": [{"id": "1", "source": ""}],
        "rules": {
            "required_fields": ["id"],
            "null_values": [""],
            "field_rules": {"source": {"action": "fill", "value": "unknown"}},
        },
    },
)
```

For large data, an application should pass artifact references to a file-level Pipeline tool rather than embedding records in a model request.

## Optional rule-planner prompt

If an application adds an LLM, keep the prompt narrow:

```text
You translate a data-quality request into candidate YAML rules.
Use only the registered Skill names supplied by the application.
Do not claim execution or successful validation.
Do not include credentials, raw personal data, executable code, or file paths outside the allowed workspace.
When requirements are ambiguous, return questions instead of guessing destructive actions.
Return only a rule object and a short assumptions list.
```

The application must parse the response as data, validate it against rule constraints, and show destructive `drop` behavior to a human before execution.

## Evaluation and feedback

`QualityEvaluator` computes missing-field, quarantine-rate, and abnormal-rate outcomes from Pipeline counters. Missing required fields may reject a run; threshold breaches route it to review. `resolve_review()` records the reviewer, decision, comment, and timestamp without mutating the original packet.

This is an evaluation pipeline, not a model-quality benchmark. If RAG is later added, retrieval should be limited to versioned rule documentation and data dictionaries, preserve document provenance, and still feed the same deterministic validator. The current project does not claim a RAG implementation.

Run the synthetic example with:

```bash
python scripts/run_agent_demo.py
```
