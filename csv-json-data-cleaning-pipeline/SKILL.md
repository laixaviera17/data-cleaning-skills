---
name: csv-json-data-cleaning-pipeline
description: 当用户需要一条端到端、多步骤的 CSV、JSON 或 JSONL 数据清洗产线，用于编排字段映射、缺失值处理、格式标准化、字典校验、异常检测、问题行导出、清洗日志和汇总生成时使用本 skill。对于单一用途的检查或修复，优先使用更聚焦的原子 skill。
---

# Skill概述

CSV/JSON 数据批量清洗产线用于编排 CSV、JSON、JSONL 等结构化和半结构化数据的清洗流程，帮助数据开发人员完成入库前、加工前或交付前的批量质量处理。

该 Skill 对应“数据清洗规则编排产线”能力，主要支撑《高质量数据集 建设平台技术要求》中 5.3.2 数据清洗和 5.5.3 数据清洗要求。

本 Skill 定位为编排层 Pipeline Skill。它负责读取任务配置、安排字段映射、缺失值处理、格式标准化、字典校验、异常检测、问题导出、统计汇总和日志生成的执行顺序。具体清洗逻辑应优先下沉到原子 Skill；本 Skill 只保留流程控制、跨步骤数据传递、输出汇总和清洗结果封装。

适用场景包括：采集数据清洗、数据集交付前检查、多来源数据格式统一、问题数据导出、清洗过程追溯和清洗统计报告生成。

# 功能范围

## 支持能力

- 读取 CSV、JSON、JSONL 主数据文件。
- 读取清洗规则、字段映射和数据字典配置。
- 按配置编排字段映射、去重、缺失处理、格式标准化、字典校验和异常检测。
- 支持键值去重和相似度去重（阈值可配置）。
- 将各步骤的问题输出汇总为统一 `issue_rows`。
- 生成 `cleaned_data`、`cleaning_summary` 和 `cleaning_log`。
- 调用本目录脚本或已安装的原子 Skill 完成可复用处理。

## 不支持能力

- 不支持非结构化文本清洗，例如长文本语义清洗、段落重写、语义纠错。
- 不支持图像数据清洗，例如图片去重、图片质量检测、图片标注。
- 不支持音频数据清洗，例如音频降噪、静音切分、人声提取。
- 不支持机器学习预测修复，例如基于模型自动预测缺失值或自动生成修复内容。
- 不应替代 `missing-value-checker`、`format-standardizer`、`abnormal-value-detector`、`field-dictionary-value-validator`、`table-field-mapping-converter` 等原子 Skill 的细节规则说明。

# 输入定义

- 原始数据文件：CSV、JSON 或 JSONL。
- 清洗规则文件：优先使用 `assets/rule_template.yaml` 作为模板。
- 字段映射文件：需要统一字段名时提供。
- 数据字典文件：需要枚举值或标准值校验时提供。

详细规则格式见 `references/rule_config_guide.md`，常见质量规则见 `references/data_quality_rules.md`。

# 输出定义

- `cleaned_data`：清洗后的主数据，保持输入格式或按配置输出为 CSV、JSON、JSONL，并附带追溯字段 `_source_file`、`_source_row`、`_record_hash`、`_batch_id`、`_rule_version`。
- `issue_rows`：跨步骤归集的问题数据，字段规范见 `references/output_spec.md`。
- `cleaning_summary`：输入量、输出量、问题量、删除量、修复量和规则执行摘要。
- `cleaning_log`：主要步骤、规则名称、影响行数、执行结果和说明信息。
- `dedup_report`：精确去重和相似度去重统计及命中明细。

# 处理流程

1. 数据加载：读取 CSV、JSON 或 JSONL 原始数据，识别字段、记录数量和文件编码。
2. 规则校验：检查清洗规则文件是否完整，确认规则中引用的字段是否存在。
3. 字段映射：如存在映射文件，先统一字段名。
4. 去重处理：根据 `unique_keys` 配置识别重复数据。
5. 原子清洗：按规则调用缺失处理、格式标准化、字典校验和异常检测能力。
6. 问题归集：将重复、缺失、格式失败、字典不匹配、异常检测等输出合并到 `issue_rows`。
7. 结果汇总：生成 `cleaned_data`、`cleaning_summary` 和 `cleaning_log`。

详细流程见 `references/cleaning_workflow.md`。

# 规则配置说明

使用 `assets/rule_template.yaml` 起步。配置应只描述本次任务需要启用哪些步骤、每步使用哪些字段、失败时如何处理，以及输出格式。

# 核心能力

- 文件格式识别和统一读取。
- 清洗规则校验。
- 原子清洗能力编排。
- 跨步骤问题归集。
- 清洗统计和追溯日志生成。

# 目录结构说明

推荐目录结构如下：

```text
csv-json-data-cleaning-pipeline/
├── SKILL.md
├── requirements.txt
├── references/
│   ├── cleaning_workflow.md
│   ├── rule_config_guide.md
│   ├── data_quality_rules.md
│   └── output_spec.md
├── assets/
│   └── rule_template.yaml
├── scripts/
│   ├── clean_dataset.py
│   ├── validate_rules.py
│   └── file_utils.py
├── tests/
│   ├── test_clean_dataset.py
│   ├── test_file_utils.py
│   ├── test_rules.py
└── examples/
    ├── bad_input.csv
    ├── invalid_rules.yaml
    ├── sample_input.csv
    ├── sample_rules.yaml
    └── expected_outputs/
```

目录和文件用途：

- `SKILL.md`：Skill 主说明文件，定义使用场景、处理流程和操作要求。
- `requirements.txt`：运行依赖。
- `references/cleaning_workflow.md`：详细清洗流程说明。
- `references/rule_config_guide.md`：规则配置说明。
- `references/data_quality_rules.md`：常见数据质量规则说明。
- `references/output_spec.md`：输出文件格式和字段规范。
- `assets/rule_template.yaml`：清洗规则模板。
- `scripts/clean_dataset.py`：编排清洗流程，调用原子 Skill 并生成输出。
- `scripts/validate_rules.py`：规则校验脚本。
- `scripts/pipeline_file_utils.py`：文件读写工具。
- `tests/test_clean_dataset.py`：编排流程测试文件。
- `tests/test_file_utils.py`：文件读写测试文件。
- `tests/test_rules.py`：规则校验测试文件。
- `examples/`：示例输入、示例规则和预期输出。

# 使用示例

## 输入文件

示例输入数据：

- `examples/sample_input.csv`
- `examples/sample_rules.yaml`

其中，`sample_input.csv` 存放待清洗数据，`sample_rules.yaml` 存放本次清洗规则。

## 执行命令

```bash
python scripts/clean_dataset.py examples/sample_input.csv examples/sample_rules.yaml
```

脚本接收两个位置参数：输入数据文件和规则文件。清洗统计摘要会打印到标准输出（JSON）。

输出目录不通过命令行指定，而是由规则文件中的 `output` 配置决定。当规则包含 `output.output_dir` 时，脚本会把以下文件写入该目录；文件名可在 `output` 下覆盖（详见 `references/rule_config_guide.md` 与 `assets/rule_template.yaml`）。示例中的 `sample_rules.yaml` 将输出写入 `examples/expected_outputs`。

```yaml
output:
  output_dir: "outputs/cleaning_result"
  output_format: "csv"
```

## 输出结果

当规则配置了 `output.output_dir` 时，执行完成后该目录下会生成以下文件：

```text
outputs/cleaning_result/
├── cleaned_data.csv
├── issue_rows.csv
├── cleaning_summary.json
├── cleaning_log.csv
└── dedup_report.json
```

输出说明：

- `cleaned_data.csv`：清洗后的有效数据。
- `issue_rows.csv`：问题数据明细。
- `cleaning_summary.json`：清洗统计结果。
- `cleaning_log.csv`：清洗操作日志。

# 验收标准

| 验收项 | 验收标准 |
|---|---|
| 文件读取成功 | 能正确读取 CSV、JSON、JSONL 中至少一种输入文件，并识别字段和记录数量。 |
| 清洗规则生效 | 必填字段、去重字段、缺失值处理、异常值检测和格式标准化规则能够按配置执行。 |
| 问题数据正确输出 | 重复、缺失、异常、格式错误等问题数据能够写入 `issue_rows`，并说明问题原因。 |
| 日志完整记录 | `cleaning_log` 能记录主要处理步骤、执行规则、影响数据量和处理结果。 |
| 统计结果正确 | `cleaning_summary` 能准确统计输入数量、输出数量、问题数量、删除数量和修复数量。 |
| 输出结构清晰 | 输出目录中应包含清洗后数据、问题数据、统计文件和日志文件。 |
| 功能边界明确 | 不应包含非结构化文本清洗、图像清洗、音频清洗或机器学习预测修复能力。 |
