---
name: abnormal-value-detector
description: 当用户需要使用可配置的范围、枚举和正则规则，检测 CSV 或 JSON 数据集中的异常值或非法值时使用本 skill，尤其适用于数据清洗、质量检查和交付前校验。
---

# Skill概述

`abnormal-value-detector` 用于检测 CSV/JSON 数据集中的异常值和非法值。

该 Skill 面向数据开发和数据治理项目中的入库前校验、清洗过程质检、交付前质量核查等场景，重点解决数值超范围、枚举值非法、字段格式不符合正则规则等常见问题。

本 Skill 参考 `csv-json-data-cleaning-pipeline`、`missing-value-checker` 和 `format-standardizer` 的项目组织方式，但能力范围更轻量，专注于异常值和非法值检测。

# 分层定位

本 Skill 是原子能力层 Atomic Skill，只负责：

- 数值范围检测。
- 枚举非法值检测。
- 正则表达式检测。
- 异常分类和字段级统计。

它可以被编排层 `csv-json-data-cleaning-pipeline` 调用，也可以作为独立工具使用。不要在本 Skill 中加入自动修复、缺失值填充、格式标准化、去重、清洗日志汇总等 pipeline 职责。

稳定接口：

```python
process_dataframe(dataframe, rules) -> (unchanged_dataframe, abnormal_report)
```

`unchanged_dataframe` 是输入 DataFrame 的副本，本 Skill 只检测不修改；`abnormal_report` 包含 `abnormal_count`、`abnormal_summary`、`field_summary` 和 `abnormal_records`。

`abnormal_records` 使用统一 issue schema：

| 字段 | 说明 |
|---|---|
| row | 数据行号，从 1 开始。 |
| field | 异常字段名。 |
| value | 原始异常值。 |
| issue_type | 异常类型，如 `out_of_range`。 |
| reason | 异常原因，和 `issue_type` 保持一致。 |
| source_skill | 固定为 `abnormal-value-detector`。 |
| action | 固定为 `detect`。 |

# 功能范围

## 支持能力

- CSV 数据读取。
- JSON 数据读取。
- 数值范围检测。
- 枚举值检测。
- 正则表达式检测。
- 空规则跳过。
- `strict` 模式。
- 规则文件校验。
- 异常分类统计。
- 字段级统计。
- 输出异常记录。
- 输出异常原因。

## 不支持能力

- 不支持异常值自动修复。
- 不支持缺失值自动填充。
- 不支持重复数据去重。
- 不支持日期、手机号、金额格式标准化。
- 不支持字段字典批量映射修复。
- 不支持机器学习预测检测。
- 不支持图像、音频、视频等非表格数据。

# 输入定义

## 原始数据文件

支持 CSV 和 JSON。

| 格式 | 要求 |
|---|---|
| CSV | 第一行为表头，建议 UTF-8 编码。 |
| JSON | 推荐为对象数组，每个对象表示一条记录。 |

## 规则文件

规则文件用于定义需要检测的字段、检测类型和输出要求。

建议配置项：

- `range_rules`
- `enum_rules`
- `regex_rules`
- `output`

# 输出定义

## abnormal_records

标准输出文件为 `abnormal_records.json`，用于记录检测出的异常值和非法值。

核心字段包括：

- `total_rows`
- `abnormal_count`
- `abnormal_records`
- `row`
- `field`
- `value`
- `reason`

同时包含：

- `abnormal_summary`
- `field_summary`

示例：

```json
{
  "total_rows": 100,
  "abnormal_count": 3,
  "abnormal_summary": {
    "out_of_range": 1,
    "not_allowed": 1,
    "regex_not_match": 1
  },
  "field_summary": {
    "age": 1,
    "gender": 1,
    "email": 1
  },
  "abnormal_records": [
    {
      "row": 10,
      "field": "age",
      "value": 999,
      "issue_type": "out_of_range",
      "reason": "out_of_range",
      "source_skill": "abnormal-value-detector",
      "action": "detect"
    }
  ]
}
```

## rule_validation_report

规则校验输出文件为 `rule_validation_report.json`，用于记录规则配置是否可用。

核心字段包括：

- `valid`
- `strict`
- `errors`
- `warnings`

# 处理流程

1. 读取输入数据。
2. 读取规则配置。
3. 校验规则文件。
4. 在 `strict: true` 时，规则错误直接返回错误。
5. 在 `strict: false` 时，跳过异常规则继续执行。
6. 对数值字段执行范围检测。
7. 对枚举字段执行合法值检测。
8. 对文本字段执行正则表达式检测。
9. 汇总异常记录、异常分类统计和字段级统计。
10. 输出 `rule_validation_report.json` 和 `abnormal_records.json`。

# 规则配置说明

规则文件建议采用 YAML。

示例结构：

```yaml
strict: false

range_rules:
  age:
    min: 0
    max: 120
  salary:
    min: 0
    max: 1000000

enum_rules:
  gender:
    allowed:
      - male
      - female

regex_rules:
  email:
    pattern: '^[^@]+@[^@]+\.[^@]+$'

output:
  output_dir: "examples/expected_outputs"
  abnormal_records_name: "abnormal_records.json"
  rule_validation_report_name: "rule_validation_report.json"
```

配置项说明：

| 配置项 | 说明 |
|---|---|
| `range_rules` | 数值范围检测规则。 |
| `min` | 字段允许的最小值。 |
| `max` | 字段允许的最大值。 |
| `enum_rules` | 枚举值检测规则。 |
| `allowed` | 字段允许出现的合法取值列表。 |
| `regex_rules` | 正则表达式检测规则。 |
| `pattern` | 字段值需要满足的正则表达式。 |
| `strict` | 严格模式。`true` 时规则错误直接返回错误，`false` 时跳过异常规则继续执行。 |

# 检测示例

## 数值范围检测

规则：

```yaml
age:
  min: 0
  max: 120
```

异常示例：

- `age = -1`
- `age = 999`

异常原因：

```text
out_of_range
```

## 枚举值检测

规则：

```yaml
gender:
  allowed:
    - male
    - female
```

异常示例：

- `gender = unknown`
- `gender = other`

异常原因：

```text
not_allowed
```

## 正则表达式检测

规则：

```yaml
email:
  pattern: '^[^@]+@[^@]+\.[^@]+$'
```

异常示例：

- `email = abc`
- `email = user@`

异常原因：

```text
regex_not_match
```

# 目录结构说明

推荐目录结构：

```text
abnormal-value-detector/
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
│   │   ├── README.md
│   │   ├── boundary_rules_strict_false.yaml
│   │   ├── boundary_rules_strict_true.yaml
│   │   ├── single_row.csv
│   │   ├── all_legal.csv
│   │   ├── all_legal.json
│   │   ├── all_abnormal.csv
│   │   ├── all_abnormal.json
│   │   ├── missing_detection_field.csv
│   │   ├── empty.csv
│   │   ├── empty_rules.yaml
│   │   ├── invalid_rules.yaml
│   │   ├── invalid_rules_strict_true.yaml
│   │   └── large_input.csv
│   └── expected_outputs/
│       ├── abnormal_records.json
│       └── rule_validation_report.json
├── scripts/
│   ├── detect_abnormal_values.py
│   └── file_utils.py
└── tests/
    └── test_abnormal_value_detector.py
```

# 验收标准

| 验收项 | 标准 |
|---|---|
| 文件读取 | 能读取 CSV 和 JSON 数据。 |
| 数值范围检测 | 能识别小于 `min` 或大于 `max` 的值。 |
| 枚举值检测 | 能识别不在 `allowed` 列表中的值。 |
| 正则检测 | 能识别不符合 `pattern` 的值。 |
| 空规则跳过 | 空规则不应导致任务失败。 |
| 异常输出 | 能生成 `abnormal_records.json`。 |
| 规则校验输出 | 能生成 `rule_validation_report.json`。 |
| strict 模式 | `strict: true` 规则错误直接返回错误，`strict: false` 跳过异常规则继续执行。 |
| 异常统计 | 能生成 `abnormal_summary` 和 `field_summary`。 |
| 边界测试 | 空文件、单行文件、全合法、全异常、缺失字段、缺失规则、空规则、非法规则和大文件均有测试覆盖。 |
| 原值保留 | 异常记录中应保留原始字段值。 |
| 错误原因 | 异常记录中应包含明确 `reason`。 |
