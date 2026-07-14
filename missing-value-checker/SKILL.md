---
name: missing-value-checker
description: 当用户需要使用可配置规则，检查并修复 CSV 或 JSON 数据集中的缺失值、缺失列或必填字段问题时使用本 skill。
---

# Skill概述

`missing-value-checker` 用于检查 CSV/JSON 数据中的空值、缺失字段和必填字段缺失问题，并根据规则执行基础自动修复。

该 Skill 面向数据开发和数据治理项目中的入库前检查、清洗前预处理、交付前质量核查等场景，重点解决字段不完整、关键字段为空、默认占位值混乱等常见问题。

本 Skill 参考 `csv-json-data-cleaning-pipeline` 的项目组织方式，但能力范围更轻量，专注于缺失值相关检查和修复。

# 分层定位

本 Skill 是原子能力层 Atomic Skill，只负责：

- 缺失字段检查。
- 空值识别。
- 必填字段校验。
- 基础缺失值修复。

它可以被编排层 `csv-json-data-cleaning-pipeline` 调用，也可以作为独立工具使用。不要在本 Skill 中加入去重、格式标准化、异常值检测、报告编排等 pipeline 职责。

稳定接口：

```python
process_dataframe(dataframe, rules) -> (processed_dataframe, quality_report)
```

`processed_dataframe` 是修复后的 DataFrame，`quality_report` 包含 `missing_cells`、`repaired_cells`、`unrepaired_cells`、`missing_fields` 和字段统计。

统一 issue schema 由编排层生成。本 Skill 如需表达问题，应优先在报告中提供结构化统计，由 pipeline 转换为 `row`、`field`、`value`、`issue_type`、`reason`、`source_skill`、`action` 结构。

# 功能范围

## 支持能力

- CSV 数据读取。
- JSON 数据读取。
- 字段存在性检查。
- 必填字段缺失检查。
- 空值、空字符串、null、N/A、未知等缺失值识别。
- 按规则填充默认值。
- 按字段配置自定义填充值。
- 按字段执行均值/中位数/众数填补。
- 按字段执行前向/后向填补（ffill/bfill）。
- 按字段删除缺失值所在行（drop）。
- 按字段配置保留空值。
- 输出质量报告。
- 输出已修复和未修复单元格数量。

## 不支持能力

- 不支持输出修复后的 cleaned_data 文件。
- 不支持输出逐行缺失问题清单。
- 不支持日期、手机号、金额等格式标准化。
- 不支持重复数据去重。
- 不支持异常值和非法值检测。
- 不支持字段字典值校验。
- 不支持机器学习预测填补。
- 不支持图像、音频、视频等非表格数据。

# 输入定义

## 原始数据文件

支持 CSV 和 JSON。

| 格式 | 要求 |
|---|---|
| CSV | 第一行为表头，建议 UTF-8 编码。 |
| JSON | 推荐为对象数组，每个对象表示一条记录。 |

## 规则文件

规则文件用于定义必填字段、缺失值识别范围和修复策略。

建议配置项：

- `required_fields`
- `null_values`
- `field_rules`
- `output`

# 输出定义

## quality_report

标准输出文件为 `quality_report.json`，用于记录缺失检测与修复统计。

核心字段包括：

- `total_rows`
- `total_fields`
- `missing_cells`
- `repaired_cells`
- `unrepaired_cells`
- `missing_fields`
- `field_stats`

# 处理流程

1. 读取输入数据。
2. 读取规则配置。
3. 检查必填字段是否存在。
4. 识别字段值中的缺失值。
5. 根据规则执行默认填充、自定义填充或保留空值。
6. 统计已修复和未修复单元格数量。
7. 输出 `quality_report.json`。

# 规则配置说明

规则文件建议采用 YAML。

示例结构：

```yaml
required_fields:
  - id
  - name

null_values:
  - ""
  - "null"
  - "N/A"
  - "未知"

field_rules:
  name:
    action: fill_default
    value: UNKNOWN
  country:
    action: fill_custom
    value: CHINA
  phone:
    action: keep_null
```

配置项说明：

| 配置项 | 说明 |
|---|---|
| `required_fields` | 必须存在的字段列表。 |
| `null_values` | 被视为缺失值的取值列表。 |
| `field_rules` | 各字段的缺失值处理策略。 |
| `action` | 支持 `fill_default`、`fill_custom`、`fill`、`mean`、`median`、`mode`、`ffill`、`bfill`、`drop`、`keep_null`。 |
| `value` | 填充值，供 `fill_default` 和 `fill_custom` 使用。 |

# 一条命令复现（Day1）

```bash
python3 scripts/check_missing_values.py examples/sample_input.csv examples/sample_rules.yaml examples/day1_output
```

# 目录结构说明

推荐目录结构：

```text
missing-value-checker/
├── README.md
├── SKILL.md
├── PROJECT_STRUCTURE.md
├── TEST_PLAN.md
├── acceptance_report.md
├── requirements.txt
├── examples/
│   ├── README.md
│   ├── sample_input.csv
│   ├── sample_input.json
│   ├── sample_rules.yaml
│   ├── boundary/
│   └── expected_outputs/
│       └── quality_report.json
├── scripts/
│   ├── check_missing_values.py
│   └── file_utils.py
└── tests/
    └── test_missing_value_checker.py
```

# 验收标准

| 验收项 | 标准 |
|---|---|
| 文件读取 | 能读取 CSV 和 JSON 数据。 |
| 字段检查 | 能识别缺失的必填字段。 |
| 空值识别 | 能识别空字符串、null、N/A、未知等缺失值。 |
| 自动修复 | 能按规则默认填充、自定义填充或保留空值。 |
| 报告输出 | 能生成 `quality_report.json`。 |
| 摘要输出 | 能统计 `repaired_cells` 和 `unrepaired_cells`。 |
| 边界处理 | 空文件、无缺失数据、全部缺失数据均有明确结果。 |
| 错误处理 | 不合法规则应返回清晰错误信息。 |
