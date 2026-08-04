# Contributing

Thank you for improving Data Cleaning Skills. Contributions should preserve the repository's central contract: atomic Skills remain independently testable, while orchestration, policy, and delivery concerns stay in their own layers.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[test]'
```

Before opening a pull request, run:

```bash
.venv/bin/ruff check src benchmarks qa/tests/test_skill_registry.py qa/tests/test_contract_validation.py qa/tests/test_runtime.py qa/tests/test_benchmark.py qa/tests/test_agent.py qa/tests/test_chunking.py
.venv/bin/mypy src/data_cleaning_skills
.venv/bin/python -m pytest -q --cov=data_cleaning_skills --cov-branch
.venv/bin/python qa/run_qa.py --python .venv/bin/python
```

## Change design

- Put deterministic, single-purpose transformations in an atomic Skill.
- Expose in-memory behavior through `process_dataframe(dataframe, rules)` and normalize it through `SkillRegistry`.
- Keep filesystem writes, orchestration, evaluation, and human review outside atomic transformations.
- Reject unsupported configurations explicitly; do not silently ignore misspelled rules.
- Add boundary and failure-path tests, not only happy-path examples.
- Do not commit customer, production, personal, credential, or absolute local-path data.

For changes that affect public contracts, add or update a JSON Schema and document compatibility impact. For architecture-level changes, add a short ADR under `docs/adr/`.

## Pull requests and commits

Keep pull requests focused and explain the problem, design choice, validation evidence, and compatibility risk. Use Conventional Commit prefixes where practical:

- `feat:` new behavior
- `fix:` bug fix
- `refactor:` behavior-preserving internal change
- `docs:` documentation only
- `test:` tests only
- `ci:` automation and workflow changes

By contributing, you agree that your contribution is licensed under the repository's MIT License and follows the project Code of Conduct.
