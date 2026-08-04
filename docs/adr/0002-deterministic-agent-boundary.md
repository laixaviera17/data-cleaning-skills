# ADR 0002: Deterministic Agent boundary

- Status: Accepted
- Date: 2026-08-03

## Context

The repository should be callable by AI systems without implying that nondeterministic model output is a trusted cleaning rule or quality decision.

## Decision

Provide a thin Agent adapter with Tool metadata, deterministic planning, Pipeline execution, bounded session events, explicit threshold evaluation, and Human Review Packets. Model-assisted rule generation remains outside the trusted runtime boundary.

## Consequences

Agent architecture is demonstrable without adding an LLM dependency, prompt lock-in, hidden cost, or network requirement. Applications may add an LLM planner, but generated rules must still pass the same validator and evaluator.
