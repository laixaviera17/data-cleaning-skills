---
name: format-standardizer
description: 当用户需要使用可配置规则，对 CSV 或 JSON 数据集中的格式、编码和单位进行标准化时使用本 skill，尤其适用于数据清洗、数据集预处理或交付前的字段规范化。
---

# Skill概述

`format-standardizer` 用于对 CSV/JSON 数据集中的日期、手机号、金额、证件号、单位字段进行统一标准化，并输出编码转换报告（统一到 UTF-8）。

该 Skill 面向数据开发和数据治理项目中的入库前处理、清洗后交付、字段口径统一等场景，重点解决多来源数据格式不一致、人工录入格式混乱、交付口径不统一等常见问题。

本 Skill 参考 `csv-json-data-cleaning-pipeline` 和 `missing-value-checker` 的项目组织方式，但能力范围更轻量，专注于字段格式标准化。

# 分层定位

本 Skill 是原子能力层 Atomic Skill，只负责：

- 日期格式标准化。
- 手机号格式标准化。
- 金额格式标准化。
- 证件号格式标准化。
- 单位标准化（重量/长度/时间/金额单位）。
- 输入编码检测与 UTF-8 统一输出。
- 格式标准化失败记录。

它可以被编排层 `csv-json-data-cleaning-pipeline` 调用，也可以作为独立工具使用。不要在本 Skill 中加入缺失值修复、去重、异常值业务规则检测、清洗统计汇总等 pipeline 职责。

稳定接口：

```python
process_dataframe(dataframe, rules) -> (standardized_dataframe, standardization_report)
```

`standardized_dataframe` 是格式统一后的 DataFrame，`standardization_report` 包含 `standardized_cells`、`failed_cells`、`missing_fields`、`abnormal_records` 和字段统计。

`abnormal_records` 使用统一 issue schema：

| 字段 | 说明 |
|---|---|
| row | 数据行号，从 1 开始。 |
| field | 无法标准化的字段名。 |
| value | 原始值。 |
| issue_type | 固定为 `standardization_failed`。 |
| reason | 失败原因，如 `date_standardization_failed`。 |
| source_skill | 固定为 `format-standardizer`。 |
| action | 固定为 `standardize`。 |

# 功能范围

## 支持能力

- CSV 数据读取。
- JSON 数据读取。
- 日期字段标准化，统一输出 `YYYY-MM-DD`。
- 手机号字段标准化，统一输出 11 位数字格式。
- 金额字段标准化，统一输出两位小数字符串。
- 证件号字段标准化，统一输出 18 位大写格式。
- 单位字段标准化，支持重量、长度、时间、金额单位转换并记录换算明细。
- 编码检测（UTF-8、UTF-8 BOM、GBK/GB18030）并统一输出 UTF-8。
- 按规则指定需要处理的字段。
- 支持 `date_rules`、`phone_rules`、`amount_rules`。
- 支持 `id_card_rules`、`unit_rules`、`encoding_rules`。
- 支持 `enable: true/false` 控制规则启用。
- 支持严格模式 `strict: true` 记录异常值。
- 输出格式标准化统计报告。
- 输出异常记录。

## 不支持能力

- 不支持重复数据去重。
- 不支持缺失值自动填充。
- 不支持输出标准化后的数据文件。
- 不支持异常值业务判断。
- 不支持非日期、非手机号、非金额字段的标准化。
- 不支持国际手机号复杂归属地判断。
- 不支持汇率换算。
- 不支持图像、音频、视频等非表格数据。

# 输入定义

## 原始数据文件

支持 CSV 和 JSON。

| 格式 | 要求 |
|---|---|
| CSV | 第一行为表头，建议 UTF-8 编码。 |
| JSON | 推荐为对象数组，每个对象表示一条记录。 |

## 规则文件

规则文件用于定义需要标准化的字段、字段类型和输出要求。

建议配置项：

- `date_rules`
- `phone_rules`
- `amount_rules`
- `output`

# 输出定义

## standardization_report

标准输出文件为 `standardization_report.json`，记录输入行数、处理字段、成功标准化数量、无法标准化数量和缺失字段。

## abnormal_records

异常记录文件为 `abnormal_records.json`。当规则启用严格模式 `strict: true` 时，无法标准化的值会记录到该文件。

# 处理流程

1. 读取输入数据。
2. 读取规则配置。
3. 检查规则指定字段是否存在。
4. 对日期字段进行标准化。
5. 对手机号字段进行标准化。
6. 对金额字段进行标准化。
7. 严格模式下记录无法标准化的异常值。
8. 统计标准化成功和失败数量。
9. 输出 `standardization_report.json` 和 `abnormal_records.json`。

# 规则配置说明

规则文件建议采用 YAML。

示例结构：

```yaml
date_rules:
  enable: true
  strict: true
  fields:
    - publish_date

phone_rules:
  enable: true
  strict: true
  country_code: "86"
  fields:
    - phone

amount_rules:
  enable: true
  strict: true
  decimal_places: 2
  fields:
    - amount

id_card_rules:
  enable: true
  strict: true
  fields:
    - id_card

unit_rules:
  enable: true
  strict: true
  fields:
    - field: weight
      unit_type: weight
      target_unit: g
      decimal_places: 1
    - field: distance
      unit_type: length
      target_unit: m
      decimal_places: 2

encoding_rules:
  detect_order: ["utf-8-sig", "utf-8", "gb18030", "gbk"]

output:
  output_dir: "examples/expected_outputs"
  standardization_report_name: "standardization_report.json"
  abnormal_records_name: "abnormal_records.json"
  encoding_report_name: "encoding_report.json"
  standardized_data_name: "standardized_data.csv"
```

配置项说明：

| 配置项 | 说明 |
|---|---|
| `date_rules` | 日期字段标准化配置。 |
| `phone_rules` | 手机号字段标准化配置。 |
| `amount_rules` | 金额字段标准化配置。 |
| `id_card_rules` | 证件号字段标准化配置。 |
| `unit_rules` | 单位标准化配置。 |
| `encoding_rules` | 编码检测顺序配置。 |
| `enable` | 是否启用规则。 |
| `strict` | 是否记录无法标准化的异常值。 |
| `fields` | 需要标准化的字段名列表。 |
| `country_code` | 手机号国家区号处理配置，默认处理中国大陆 `86`。 |
| `decimal_places` | 金额保留小数位数，默认 2。 |

# 标准化示例

## 日期

输入：

- `2025/01/01`
- `2025-1-1`
- `01-01-2025`
- `2025.01.01`

统一输出：

```text
2025-01-01
```

## 手机号

输入：

- `138 0013 8000`
- `138-0013-8000`
- `+86-13800138000`
- `0086 13800138000`

统一输出：

```text
13800138000
```

## 金额

输入：

- `￥1,200.00`
- `1,200`
- `1200`
- `1200元`

统一输出：

```text
1200.00
```

# 一条命令复现（Day2）

```bash
python3 scripts/standardize_format.py examples/sample_input.csv examples/sample_rules.yaml examples/day2_output
```

输出物：

- `examples/day2_output/standardized_data.csv`
- `examples/day2_output/standardization_report.json`
- `examples/day2_output/encoding_report.json`
- `examples/day2_output/abnormal_records.json`

编码样例（GBK / UTF-8 / UTF-8 BOM）可用同一条命令分别复现：

```bash
python3 scripts/standardize_format.py examples/encoding/sample_gbk.csv examples/sample_rules.yaml examples/day2_output_gbk
python3 scripts/standardize_format.py examples/encoding/sample_utf8.csv examples/sample_rules.yaml examples/day2_output_utf8
python3 scripts/standardize_format.py examples/encoding/sample_utf8_bom.csv examples/sample_rules.yaml examples/day2_output_utf8_bom
```

# 目录结构说明

推荐目录结构：

```text
format-standardizer/
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
│   │   ├── boundary_rules.yaml
│   │   ├── empty.csv
│   │   ├── single_row.csv
│   │   ├── empty_phone.csv
│   │   ├── invalid_phone.csv
│   │   ├── invalid_date.csv
│   │   ├── invalid_amount.csv
│   │   ├── mixed_formats.csv
│   │   └── large_input.csv
│   └── expected_outputs/
│       ├── standardization_report.json
│       └── abnormal_records.json
├── scripts/
│   ├── standardize_format.py
│   └── file_utils.py
└── tests/
    └── test_format_standardizer.py
```

# 验收标准

| 验收项 | 标准 |
|---|---|
| 文件读取 | 能读取 CSV 和 JSON 数据。 |
| 日期标准化 | 能将常见日期格式统一为 `YYYY-MM-DD`。 |
| 手机号标准化 | 能去除空格、横线、`+86`、`0086` 等前缀并输出 11 位手机号。 |
| 金额标准化 | 能去除人民币符号、千分位、中文单位并输出两位小数。 |
| 报告输出 | 能生成 `standardization_report.json`。 |
| 异常输出 | 严格模式下能生成 `abnormal_records.json`。 |
| 边界处理 | 无法识别的值应保留原值并记录在报告中。 |
| 边界测试 | 空文件、单行文件、空手机号、非法手机号、非法日期、非法金额、超大文件和混合格式文件均有测试覆盖。 |
