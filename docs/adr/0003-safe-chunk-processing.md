# ADR 0003: Constrain chunk processing to equivalent rule combinations

- Status: Accepted
- Date: 2026-08-03

## Context

Whole-file DataFrames limit scale, but naive chunking changes deduplication semantics and can make benchmark claims misleading.

## Decision

Add an iterator-based CSV interface that maintains exact unique-key state across chunks. Reject enabled field mapping and similarity deduplication until dedicated cross-chunk indexes can guarantee whole-file equivalence.

## Consequences

Supported workloads have bounded DataFrame memory and global exact-key uniqueness. Some valid whole-file configurations are intentionally unavailable in chunk mode, and callers must stream or append yielded outputs rather than collecting them all.
