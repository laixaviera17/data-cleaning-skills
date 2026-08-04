# ADR 0001: Registry and dependency-aware Pipeline

- Status: Accepted
- Date: 2026-08-03

## Context

The original modules were independently executable but orchestration depended on script locations and a fixed list of imports. This made extension, packaging, and contract testing fragile.

## Decision

Expose atomic transformations through `DataFrameSkill` and `SkillResult`, register them by stable name, and resolve selected Pipeline steps through an explicit dependency graph. Keep legacy CLIs behind compatibility adapters while migration continues.

## Consequences

Pipeline code no longer owns atomic script paths. Unknown and duplicate Skills fail before execution, and tests can replace the executor through stable interfaces. The compatibility layer still needs the repository checkout because legacy CLI packages have not all moved under `src/`.
