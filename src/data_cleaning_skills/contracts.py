"""Stable contracts shared by atomic Skills and orchestration layers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import pandas as pd


@dataclass(frozen=True)
class SkillResult:
    """Normalized result returned by every in-memory atomic Skill."""

    dataframe: pd.DataFrame
    report: dict[str, Any]


@runtime_checkable
class DataFrameSkill(Protocol):
    """Protocol for a deterministic Skill that processes one DataFrame."""

    @property
    def name(self) -> str:
        """Stable registry name."""
        ...

    @property
    def version(self) -> str:
        """Skill contract version."""
        ...

    def execute(self, dataframe: pd.DataFrame, rules: Mapping[str, Any] | Any) -> SkillResult:
        """Execute the Skill without writing artifacts or mutating the input."""
        ...
