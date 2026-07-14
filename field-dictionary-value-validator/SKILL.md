---
name: field-dictionary-value-validator
description: 当用户需要使用数据字典对 CSV、JSON 或 JSONL 数据集中的结构化字段值进行校验、标准化或修复时使用本 skill，尤其是在字段名映射之后、异常检测、质量问题导出或数据集交付之前。
---

# Skill概述

`field-dictionary-value-validator` 用于根据字段字典校验和标准化结构化字段值。

该 Skill 面向高质量数据集建设中的清洗处理环节，适合作为字段名映射之后、异常检测和封装交付之前的字段值标准化能力。

# 功能范围

## 支持能力

- CSV 数据读取。
- JSON 数据读取。
- JSONL 数据读取。
- CSV 字典文件读取。
- 按 `field_name + raw_value -> standard_value` 标准化字段值。
- `allowed=false` 非法值识别。
- 未配置字典值识别。
- 字典字段缺失识别。
- 字典替换记录生成。
- 字典校验统计报告生成。
- 稳定 DataFrame 接口供编排层调用。

## 不支持能力

- 不支持综合质量评分。
- 不支持 JSON Schema 校验修复。
- 不支持敏感数据脱敏。
- 不支持编码修复或格式转换。
- 不支持非结构化文本、图像、音频、视频内容清洗。

# 输入定义

## 原始数据文件

支持以下输入：

| 格式 | 要求 |
|---|---|
| CSV | 第一行为字段名，建议 UTF-8 编码。 |
| JSON | 推荐为对象数组。 |
| JSONL | 每行一个 JSON 对象。 |

## 字典文件

字典文件为 CSV，必须包含：

| 字段 | 说明 |
|---|---|
| `field_name` | 需要校验的字段名。 |
| `raw_value` | 原始取值。 |
| `standard_value` | 标准取值。 |
| `allowed` | 是否允许该取值。 |
| `remark` | 备注说明。 |

# 输出定义

## standardized_data

字典值标准化后的数据文件，默认保持输入格式。

## dictionary_validation_report

字典校验统计报告，包含：

- `input_rows`
- `processed_fields`
- `changed_values`
- `illegal_values`
- `unknown_values`
- `missing_fields`

## dictionary_issues

字段字典问题清单，字段包括：

| 字段 | 说明 |
|---|---|
| `row` | 数据行号。 |
| `field_name` | 字段名。 |
| `value` | 原始字段值。 |
| `issue_type` | 问题类型。 |
| `reason` | 问题原因。 |
| `action` | 处理动作。 |
| `remark` | 备注说明。 |

## dictionary_changes

字段值替换记录，字段包括：

| 字段 | 说明 |
|---|---|
| `row` | 数据行号。 |
| `field_name` | 字段名。 |
| `raw_value` | 原始值。 |
| `standard_value` | 标准值。 |
| `remark` | 备注说明。 |

# 处理流程

1. 读取 CSV、JSON 或 JSONL 原始数据。
2. 读取 CSV 字典文件。
3. 校验字典文件是否包含必需列。
4. 按字段分组加载字典规则。
5. 对存在于数据中的字段逐值校验。
6. 对允许且有标准值的字段执行标准化替换。
7. 对不允许值、未知值、缺失字段输出问题清单。
8. 输出标准化数据、统计报告、问题清单和替换记录。

# 稳定接口

```python
process_dataframe(dataframe, dictionary_rules) -> (processed_dataframe, dictionary_report)
```

# 命令行入口

```bash
python scripts/validate_dictionary_values.py input.csv dictionary.csv output_dir
```

# 验收标准

| 验收项 | 标准 |
|---|---|
| 文件读取 | 能读取 CSV、JSON、JSONL。 |
| 字典读取 | 能读取 CSV 字典文件。 |
| 标准化 | 能按字典替换标准值。 |
| 非法值 | `allowed=false` 的值被记录且不自动修复。 |
| 未知值 | 未配置字典值被记录。 |
| 缺失字段 | 字典字段不存在时被记录。 |
| 替换记录 | 能生成 `dictionary_changes.csv`。 |
| 报告输出 | 能生成 `dictionary_validation_report.json`。 |
| 接口稳定性 | `process_dataframe` 可被编排层调用。 |
