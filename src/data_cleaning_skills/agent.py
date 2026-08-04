"""Deterministic Agent adapter around the rule-driven cleaning Pipeline.

An LLM may prepare rules outside this boundary, but it cannot bypass registry,
configuration, execution, or quality-gate validation here.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import pandas as pd

from .orchestration import DEFAULT_SKILL_GRAPH, ExecutionPlan, build_execution_plan
from .registry import get_default_registry
from .validation import validate_pipeline_rules
from .workflow import load_workflow_tools


@dataclass(frozen=True)
class ToolDefinition:
    """Agent-facing description of one registered atomic Skill."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]


def atomic_tool_catalog() -> tuple[ToolDefinition, ...]:
    """Return stable tool metadata suitable for function/tool registration."""
    descriptions = {
        "table-field-mapping-converter": "Map source columns to a canonical schema.",
        "missing-value-checker": "Detect and deterministically repair configured missing values.",
        "format-standardizer": "Standardize configured date, phone, amount, id, and unit formats.",
        "field-dictionary-value-validator": "Normalize and validate values against a field dictionary.",
        "abnormal-value-detector": "Detect configured range, enumeration, and regular-expression anomalies.",
    }
    input_schema = {
        "type": "object",
        "required": ["records", "rules"],
        "properties": {
            "records": {"type": "array", "items": {"type": "object"}},
            "rules": {"type": ["object", "array"]},
        },
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "required": ["records", "report"],
        "properties": {
            "records": {"type": "array", "items": {"type": "object"}},
            "report": {"type": "object"},
        },
        "additionalProperties": False,
    }
    return tuple(ToolDefinition(name, descriptions[name], input_schema, output_schema) for name in DEFAULT_SKILL_GRAPH)


def execute_atomic_tool(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one atomic Skill through a JSON-safe Agent tool boundary."""
    records = payload.get("records")
    rules = payload.get("rules")
    if not isinstance(records, list) or not all(isinstance(record, Mapping) for record in records):
        raise ValueError("tool payload records must be an array of objects")
    if not isinstance(rules, (Mapping, list)):
        raise ValueError("tool payload rules must be an object or array")
    dataframe = pd.DataFrame.from_records(records)
    result = get_default_registry().get(name).execute(dataframe, rules)
    normalized_records = json.loads(result.dataframe.to_json(orient="records", force_ascii=False))
    normalized_report = json.loads(json.dumps(_json_safe(result.report), ensure_ascii=False, allow_nan=False))
    return {"records": normalized_records, "report": normalized_report}


def _json_safe(value: Any) -> Any:
    """Recursively normalize pandas/numpy scalars and missing values for JSON."""
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item") and callable(value.item):
        return value.item()
    return value


@dataclass(frozen=True)
class AgentEvent:
    """One auditable planning, execution, evaluation, or feedback event."""

    timestamp: str
    phase: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


class SessionMemory:
    """Bounded in-memory event history for one Agent execution session."""

    def __init__(self, max_events: int = 100) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._max_events = max_events
        self._events: list[AgentEvent] = []

    def record(self, phase: str, message: str, **details: Any) -> AgentEvent:
        """Append one event and discard the oldest entry beyond the bound."""
        event = AgentEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            phase=phase,
            message=message,
            details=details,
        )
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events.pop(0)
        return event

    def snapshot(self) -> tuple[AgentEvent, ...]:
        """Return an immutable view of recorded events."""
        return tuple(self._events)


class EvaluationDecision(str, Enum):
    """Quality-gate outcome used by automation and review routing."""

    PASS = "pass"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True)
class EvaluationPolicy:
    """Explicit thresholds; no hidden model judgment is used."""

    max_quarantine_rate: float = 0.05
    max_abnormal_rate: float = 0.05
    reject_missing_fields: bool = True

    def __post_init__(self) -> None:
        for name in ("max_quarantine_rate", "max_abnormal_rate"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class QualityEvaluation:
    """Machine-readable evaluation result for downstream routing."""

    decision: EvaluationDecision
    reasons: tuple[str, ...]
    metrics: Mapping[str, float | int]


class PipelinePlanner:
    """Resolve configured Skill names into a dependency-safe execution plan."""

    def plan(self, rules: Mapping[str, Any]) -> ExecutionPlan:
        """Build a plan from `pipeline.steps`, defaulting to every atomic Skill."""
        pipeline = rules.get("pipeline")
        selected = pipeline.get("steps") if isinstance(pipeline, Mapping) else None
        return build_execution_plan(selected, DEFAULT_SKILL_GRAPH)


class PipelineExecutor:
    """Execute a resolved plan through the existing deterministic Pipeline."""

    def __init__(self, runner: Callable[..., tuple[pd.DataFrame, dict[str, Any]]] | None = None) -> None:
        self._runner = runner

    def execute(
        self,
        dataframe: pd.DataFrame,
        rules: Mapping[str, Any],
        plan: ExecutionPlan,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Execute without mutating the caller's rules or DataFrame."""
        runtime_rules = deepcopy(dict(rules))
        runtime_rules["pipeline"] = {"steps": list(plan.steps)}
        runner = self._runner or load_workflow_tools()["process_dataframe"]
        return runner(dataframe.copy(), runtime_rules)


class QualityEvaluator:
    """Evaluate Pipeline counters against an explicit policy."""

    def __init__(self, policy: EvaluationPolicy | None = None) -> None:
        self.policy = policy or EvaluationPolicy()

    def evaluate(self, result: Mapping[str, Any]) -> QualityEvaluation:
        """Return pass, review, or reject with reproducible reasons and metrics."""
        input_rows = max(int(result.get("input_rows", 0)), 1)
        quarantined_rows = int(result.get("quarantined_rows", 0))
        abnormal_rows = int(result.get("abnormal_rows", 0))
        missing_fields = list(result.get("missing_fields", []))
        quarantine_rate = quarantined_rows / input_rows
        abnormal_rate = abnormal_rows / input_rows
        reasons: list[str] = []

        if missing_fields and self.policy.reject_missing_fields:
            reasons.append("required fields are missing: " + ", ".join(str(value) for value in missing_fields))
            decision = EvaluationDecision.REJECT
        else:
            if quarantine_rate > self.policy.max_quarantine_rate:
                reasons.append(f"quarantine rate {quarantine_rate:.2%} exceeds {self.policy.max_quarantine_rate:.2%}")
            if abnormal_rate > self.policy.max_abnormal_rate:
                reasons.append(f"abnormal rate {abnormal_rate:.2%} exceeds {self.policy.max_abnormal_rate:.2%}")
            decision = EvaluationDecision.REVIEW if reasons else EvaluationDecision.PASS

        return QualityEvaluation(
            decision=decision,
            reasons=tuple(reasons),
            metrics={
                "input_rows": input_rows,
                "quarantined_rows": quarantined_rows,
                "abnormal_rows": abnormal_rows,
                "quarantine_rate": quarantine_rate,
                "abnormal_rate": abnormal_rate,
            },
        )


class ReviewStatus(str, Enum):
    """State of one human quality decision."""

    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ReviewPacket:
    """Serializable Human-in-the-loop handoff without embedding raw records."""

    run_id: str
    status: ReviewStatus
    evaluation: QualityEvaluation
    reviewer: str = ""
    comment: str = ""
    decided_at: str = ""


def resolve_review(packet: ReviewPacket, status: ReviewStatus, reviewer: str, comment: str) -> ReviewPacket:
    """Return a resolved review packet while preserving the original object."""
    if packet.status is not ReviewStatus.PENDING:
        raise ValueError("review packet has already been resolved")
    if status is ReviewStatus.PENDING:
        raise ValueError("a review decision cannot remain pending")
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    return replace(
        packet,
        status=status,
        reviewer=reviewer.strip(),
        comment=comment.strip(),
        decided_at=datetime.now(timezone.utc).isoformat(),
    )


@dataclass(frozen=True)
class AgentRunResult:
    """Complete result returned by the deterministic Agent adapter."""

    dataframe: pd.DataFrame
    pipeline_result: Mapping[str, Any]
    plan: ExecutionPlan
    evaluation: QualityEvaluation
    review: ReviewPacket | None
    events: tuple[AgentEvent, ...]


class DataCleaningAgent:
    """Coordinate planner, executor, memory, evaluation, and review routing."""

    def __init__(
        self,
        planner: PipelinePlanner | None = None,
        executor: PipelineExecutor | None = None,
        evaluator: QualityEvaluator | None = None,
        memory: SessionMemory | None = None,
        validator: Callable[[Any], Mapping[str, Any]] | None = None,
    ) -> None:
        self.planner = planner or PipelinePlanner()
        self.executor = executor or PipelineExecutor()
        self.evaluator = evaluator or QualityEvaluator()
        self.memory = memory or SessionMemory()
        self.validator = validator

    def run(self, dataframe: pd.DataFrame, rules: Mapping[str, Any]) -> AgentRunResult:
        """Execute one deterministic Agent session and route quality exceptions."""
        validate_pipeline_rules(rules, validator=self.validator)
        self.memory.record("validation", "rules validated")
        plan = self.planner.plan(rules)
        self.memory.record("planner", "execution plan resolved", steps=list(plan.steps))
        processed, pipeline_result = self.executor.execute(dataframe, rules, plan)
        self.memory.record(
            "executor",
            "pipeline completed",
            run_id=pipeline_result.get("run_id", ""),
            output_rows=len(processed),
        )
        evaluation = self.evaluator.evaluate(pipeline_result)
        self.memory.record(
            "evaluation",
            "quality policy evaluated",
            decision=evaluation.decision.value,
            reasons=list(evaluation.reasons),
        )
        review = None
        if evaluation.decision is not EvaluationDecision.PASS:
            review = ReviewPacket(
                run_id=str(pipeline_result.get("run_id", "")),
                status=ReviewStatus.PENDING,
                evaluation=evaluation,
            )
            self.memory.record("human_review", "review packet created", run_id=review.run_id)
        return AgentRunResult(
            dataframe=processed,
            pipeline_result=pipeline_result,
            plan=plan,
            evaluation=evaluation,
            review=review,
            events=self.memory.snapshot(),
        )
