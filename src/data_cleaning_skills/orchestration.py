"""Dependency-aware execution plans for registered atomic Skills."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .errors import SkillConfigurationError

DEFAULT_SKILL_GRAPH: dict[str, tuple[str, ...]] = {
    "table-field-mapping-converter": (),
    "missing-value-checker": ("table-field-mapping-converter",),
    "format-standardizer": ("missing-value-checker",),
    "field-dictionary-value-validator": ("format-standardizer",),
    "abnormal-value-detector": ("field-dictionary-value-validator",),
}


@dataclass(frozen=True)
class ExecutionPlan:
    """Resolved deterministic order for a selected set of registered Skills."""

    steps: tuple[str, ...]

    def includes(self, name: str) -> bool:
        """Return whether the plan enables one Skill."""
        return name in self.steps


def build_execution_plan(
    selected: Sequence[str] | None,
    available: Iterable[str],
    graph: Mapping[str, tuple[str, ...]] = DEFAULT_SKILL_GRAPH,
) -> ExecutionPlan:
    """Validate selected names and topologically order the induced Skill graph."""
    available_set = set(available)
    requested = list(graph) if selected is None else list(selected)
    if len(requested) != len(set(requested)):
        raise SkillConfigurationError("pipeline.steps 不允许重复 Skill")

    unknown = sorted(set(requested) - available_set)
    if unknown:
        raise SkillConfigurationError(f"pipeline.steps 包含未注册 Skill: {', '.join(unknown)}")

    selected_set = set(requested)
    ordered: list[str] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(name: str) -> None:
        if name in permanent:
            return
        if name in temporary:
            raise SkillConfigurationError(f"Skill 依赖图存在环: {name}")
        temporary.add(name)
        for dependency in graph.get(name, ()):
            if dependency not in available_set:
                raise SkillConfigurationError(f"Skill 依赖未注册: {name} -> {dependency}")
            visit(dependency)
        temporary.remove(name)
        permanent.add(name)
        if name in selected_set:
            ordered.append(name)

    for name in requested:
        visit(name)
    return ExecutionPlan(tuple(ordered))
