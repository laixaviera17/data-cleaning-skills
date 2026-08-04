"""Registry and compatibility adapters for atomic DataFrame Skills.

The repository's historical CLIs remain in their original directories.  This
module gives orchestration code one package-level interface while those CLIs
are migrated incrementally into ``src/``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from types import ModuleType
from typing import Any

import pandas as pd

from .contracts import DataFrameSkill, SkillResult
from .errors import SkillExecutionError, UnknownSkillError


def _discover_repository_root() -> Path:
    """Locate the checkout that contains the compatibility CLI modules."""
    starts = [Path(__file__).resolve().parent, Path.cwd().resolve()]
    configured = os.environ.get("DATA_CLEANING_SKILLS_ROOT")
    if configured:
        starts.insert(0, Path(configured).expanduser().resolve())

    visited: set[Path] = set()
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate in visited:
                continue
            visited.add(candidate)
            if (candidate / "csv-json-data-cleaning-pipeline" / "scripts" / "clean_dataset.py").is_file():
                return candidate
    raise RuntimeError(
        "Cannot locate the data-cleaning-skills checkout. Run from the repository or set DATA_CLEANING_SKILLS_ROOT."
    )


@dataclass(frozen=True)
class LegacyModuleSpec:
    """Location and local import dependencies of one compatibility module."""

    script: Path
    dependencies: tuple[tuple[str, Path], ...] = ()


def _legacy_specs(root: Path) -> dict[str, LegacyModuleSpec]:
    """Build compatibility paths only when a legacy Skill is requested."""
    return {
        "table-field-mapping-converter": LegacyModuleSpec(
            root / "table-field-mapping-converter" / "scripts" / "map_fields.py",
            (
                (
                    "field_mapping_file_utils",
                    root / "table-field-mapping-converter" / "scripts" / "field_mapping_file_utils.py",
                ),
            ),
        ),
        "missing-value-checker": LegacyModuleSpec(
            root / "missing-value-checker" / "scripts" / "check_missing_values.py",
            (
                ("missing_file_utils", root / "missing-value-checker" / "scripts" / "missing_file_utils.py"),
                ("simple_yaml", root / "qa" / "shared" / "simple_yaml.py"),
            ),
        ),
        "format-standardizer": LegacyModuleSpec(
            root / "format-standardizer" / "scripts" / "standardize_format.py",
            (
                ("format_file_utils", root / "format-standardizer" / "scripts" / "format_file_utils.py"),
                ("simple_yaml", root / "qa" / "shared" / "simple_yaml.py"),
            ),
        ),
        "field-dictionary-value-validator": LegacyModuleSpec(
            root / "field-dictionary-value-validator" / "scripts" / "validate_dictionary_values.py",
            (
                (
                    "dictionary_file_utils",
                    root / "field-dictionary-value-validator" / "scripts" / "dictionary_file_utils.py",
                ),
            ),
        ),
        "abnormal-value-detector": LegacyModuleSpec(
            root / "abnormal-value-detector" / "scripts" / "detect_abnormal_values.py",
            (
                ("abnormal_file_utils", root / "abnormal-value-detector" / "scripts" / "abnormal_file_utils.py"),
                ("simple_yaml", root / "qa" / "shared" / "simple_yaml.py"),
            ),
        ),
    }


_IMPORT_LOCK = RLock()
_MODULE_CACHE: dict[str, ModuleType] = {}


def _load_module(module_name: str, path: Path) -> ModuleType:
    """Load one module from an explicit path under a collision-free name."""
    if not path.is_file():
        raise FileNotFoundError(f"Skill module does not exist: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Skill module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_legacy_skill(
    name: str,
    spec: LegacyModuleSpec,
    required_callable: str | None = "process_dataframe",
) -> ModuleType:
    """Load a legacy script while isolating its historical local imports."""
    with _IMPORT_LOCK:
        if name in _MODULE_CACHE:
            return _MODULE_CACHE[name]

        previous: dict[str, ModuleType | None] = {}
        try:
            for dependency_name, dependency_path in spec.dependencies:
                previous[dependency_name] = sys.modules.get(dependency_name)
                sys.modules[dependency_name] = _load_module(
                    f"data_cleaning_skills._compat.{name}.{dependency_name}",
                    dependency_path,
                )
            module = _load_module(f"data_cleaning_skills._compat.{name}", spec.script)
        finally:
            for dependency_name, prior_module in previous.items():
                if prior_module is None:
                    sys.modules.pop(dependency_name, None)
                else:
                    sys.modules[dependency_name] = prior_module

        if required_callable and not callable(getattr(module, required_callable, None)):
            raise SkillExecutionError(f"{name} does not expose required callable: {required_callable}")
        _MODULE_CACHE[name] = module
        return module


@dataclass(frozen=True)
class FunctionSkillAdapter:
    """Adapt an existing ``process_dataframe`` function to ``DataFrameSkill``."""

    name: str
    function: Callable[[pd.DataFrame, Any], tuple[pd.DataFrame, dict[str, Any]]]
    version: str = "1"

    def execute(self, dataframe: pd.DataFrame, rules: Mapping[str, Any] | Any) -> SkillResult:
        """Execute and validate the normalized result shape."""
        processed, report = self.function(dataframe.copy(), rules)
        if not isinstance(processed, pd.DataFrame) or not isinstance(report, dict):
            raise SkillExecutionError(f"{self.name} returned an invalid result")
        return SkillResult(dataframe=processed, report=report)


class SkillRegistry:
    """Explicit registry used by the Pipeline to discover atomic Skills."""

    def __init__(self) -> None:
        self._skills: dict[str, DataFrameSkill] = {}

    def register(self, skill: DataFrameSkill) -> None:
        """Register a Skill name once."""
        if skill.name in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> DataFrameSkill:
        """Return a registered Skill or raise a domain-specific error."""
        try:
            return self._skills[name]
        except KeyError as exc:
            raise UnknownSkillError(f"Unknown Skill: {name}") from exc

    def names(self) -> tuple[str, ...]:
        """Return registered names in deterministic order."""
        return tuple(sorted(self._skills))


def get_default_registry() -> SkillRegistry:
    """Build the default registry containing every atomic cleaning Skill."""
    registry = SkillRegistry()
    for name, spec in _legacy_specs(_discover_repository_root()).items():
        module = _load_legacy_skill(name, spec)
        registry.register(FunctionSkillAdapter(name=name, function=module.process_dataframe))
    return registry
