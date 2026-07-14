# QA 报告结构说明

统一报告生成在 `qa/reports/latest/qa_report.json`。

## 顶层

- `summary`：工作区级别的汇总指标。
- `skills`：每个 Skill 对应一个对象。

## summary

- `workspace`：被审计的工作区路径。
- `python`：QA 使用的 Python 解释器。
- `generated_at`：报告生成时间（UTC）。
- `skill_count`：发现的 Skill 目录数量。
- `failed_skills`：测试失败的 Skill 数量。
- `total_tests`：收集到的测试总数。
- `total_passed`：通过的测试数。
- `total_failures`：断言失败数。
- `total_errors`：收集 / 运行时错误数。
- `total_skipped`：跳过的测试数。
- `coverage_percent`：对 `scripts/*.py` 的加权估算覆盖率。

## skill 条目

- `name`：Skill 目录名。
- `status`：`passed` 或 `failed`。
- `tests`、`passed`、`failures`、`errors`、`skipped`：pytest/JUnit 指标。
- `coverage_percent`：该 Skill 脚本的加权估算覆盖率。
- `scripts`：`scripts/` 下的 Python 脚本数量。
- `test_files`：`tests/test_*.py` 文件数量。
- `readme_exists`：是否存在 `README.md`。
- `skill_md_exists`：是否存在 `SKILL.md`。
- `junit_path`：JUnit XML 的相对路径。
- `log_path`：捕获的 QA 日志的相对路径。
- `file_coverage`：逐脚本的覆盖率明细。
- `issues`：自动化 QA 发现的问题项。
