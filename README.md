# Data Cleaning Skills

一套用于 CSV、JSON 和 JSONL 数据清洗、质量检查与交付的模块化工具链。项目将单项规则拆分为独立 Skill，并通过端到端流水线组合执行，输出清洗结果、问题记录、操作日志和交付资料。

所有示例均为本地构造数据。本项目不连接生产数据源，也不包含机器学习或大模型推理能力。

## 模块划分

| 类别 | 模块 |
| --- | --- |
| 清洗与校验 | `table-field-mapping-converter`、`missing-value-checker`、`format-standardizer`、`field-dictionary-value-validator`、`abnormal-value-detector` |
| 编排 | `csv-json-data-cleaning-pipeline` |
| 过程追踪 | `structured-issue-list-generator`、`cleaning-operation-log-generator`、`dataset-before-after-diff-comparator` |
| 交付 | `dataset-documentation-generator`、`dataset-catalog-metadata-generator`、`cleaned-dataset-delivery-packager` |

每个 Skill 目录包含 `SKILL.md`、可运行脚本、测试、示例数据和 `agents/openai.yaml` 元数据。

## 快速开始

需要 Python 3.10 或更高版本。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python qa/run_qa.py --python .venv/bin/python
```

运行单个端到端示例：

```bash
cd csv-json-data-cleaning-pipeline
../.venv/bin/python scripts/clean_dataset.py examples/sample_input.csv examples/sample_rules.yaml
```

执行结果会写入该模块的示例输出目录；完整质量报告默认写入 `qa/reports/latest/`，该目录不纳入版本控制。

## 已验证范围

本项目已包含模块级测试和工作区集成测试。2026-07-14 的本地 QA 结果为：12 个 Skill、150 个测试全部通过；脚本覆盖率估算为 65.7%。在提交或修改后，请以上述命令重新生成报告。

## 使用边界

- 支持规则驱动的结构化数据处理；具体输入规则见每个模块的 `SKILL.md` 与 `examples/`。
- 示例数据只用于验证流程，不代表真实业务数据或生产运行结果。
- 依赖和许可信息见 [requirements.txt](requirements.txt) 与 [LICENSE](LICENSE)。
