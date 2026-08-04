# Changelog

All notable changes will be documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses semantic versioning after the first public release.

## [Unreleased]

### Added

- Installable `data_cleaning_skills` package with stable Skill contracts and registry.
- Dependency-aware Pipeline execution plans.
- Draft 2020-12 artifact contract validation and branch coverage gate.
- Correlated `run_id`, structured logging, deterministic Agent evaluation, and human-review handoff.
- Memory-bounded CSV chunk processing under explicitly supported rule combinations.
- Reproducible performance benchmark and sanitized case study.

### Changed

- Pipeline now delegates five atomic transformations through the registry.
- Delivery metadata uses portable paths and stable identifiers.
- CI checks Python compatibility, lint, typing, coverage, workspace integration, and Demo behavior.

### Removed

- Unused duplicate generic `file_utils.py` modules where a responsibility-specific helper already existed.

[Unreleased]: https://github.com/laixaviera17/data-cleaning-skills/compare/v0.1.0...HEAD
