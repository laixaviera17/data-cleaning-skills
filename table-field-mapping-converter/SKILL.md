---
name: table-field-mapping-converter
description: 当用户需要使用源到目标的字段映射文件，对 CSV、JSON 或 JSONL 数据集中的表字段进行重命名或映射时使用本 skill，尤其是在结构化数据清洗、字典校验、异常检测或数据集交付之前。
---

# Skill概述

`table-field-mapping-converter` 用于将结构化或半结构化数据中的来源字段名映射为目标标准字段名。

该 Skill 面向高质量数据集建设中的清洗处理环节，适合作为字段字典校验、异常值检测、缺失值处理和封装交付前的字段标准化能力。

# 功能范围

## 支持能力

- CSV 数据读取。
- JSON 数据读取。
- JSONL 数据读取。
- CSV 字段映射表读取。
- 按 `source_field -> target_field` 执行字段改名。
- 必填字段缺失检查。
- 缺失必填字段默认值补齐。
- 未映射字段清单生成。
- 字段映射问题清单生成。
- 字段映射统计报告生成。
- 稳定 DataFrame 接口供编排层调用。

## 不支持能力

- 不支持通用 JSON 转 CSV。
- 不支持编码修复或批量转码。
- 不支持字段值清洗、枚举值修复或异常值检测。
- 不支持字段类型强制转换。
- 不支持非结构化文本、图像、音频、视频字段抽取。

# 输入定义

## 原始数据文件

支持以下输入：

| 格式 | 要求 |
|---|---|
| CSV | 第一行为字段名，建议 UTF-8 编码。 |
| JSON | 推荐为对象数组。 |
| JSONL | 每行一个 JSON 对象。 |

## 字段映射文件

字段映射文件为 CSV，必须包含：

| 字段 | 说明 |
|---|---|
| `source_field` | 原始字段名。 |
| `target_field` | 目标标准字段名。 |
| `target_type` | 目标字段类型，仅作为元数据保留。 |
| `required` | 是否必填。 |
| `default_value` | 源字段缺失时的默认值。 |
| `description` | 字段说明。 |

# 输出定义

## mapped_data

字段改名后的数据文件，默认保持输入格式。

## field_mapping_report

字段映射统计报告，包含：

- `input_fields`
- `output_fields`
- `mapped_fields`
- `unmapped_fields`
- `missing_required_fields`
- `duplicate_target_fields`
- `empty_target_fields`

## unmapped_fields

未配置映射但保留在输出中的字段清单。

## mapping_issues

字段映射问题清单，字段包括：

| 字段 | 说明 |
|---|---|
| `source_field` | 源字段名。 |
| `target_field` | 目标字段名。 |
| `issue_type` | 问题类型。 |
| `reason` | 问题原因。 |
| `action` | 处理动作。 |

# 处理流程

1. 读取 CSV、JSON 或 JSONL 原始数据。
2. 读取 CSV 字段映射文件。
3. 校验映射文件是否包含必需列。
4. 检查空源字段、空目标字段和重复目标字段。
5. 对合法映射执行字段改名。
6. 对缺失必填源字段记录问题；如存在默认值，则补齐目标字段。
7. 保留未映射字段，并写入未映射字段清单。
8. 输出映射后数据、统计报告、未映射字段清单和问题清单。

# 稳定接口

```python
process_dataframe(dataframe, mapping_rules) -> (mapped_dataframe, mapping_report)
```

# 命令行入口

```bash
python scripts/map_fields.py input.csv field_mapping.csv output_dir
```

# 验收标准

| 验收项 | 标准 |
|---|---|
| 文件读取 | 能读取 CSV、JSON、JSONL。 |
| 字段映射 | 能按映射表改名字段。 |
| 未映射字段 | 默认保留并生成清单。 |
| 缺失字段 | 必填源字段缺失时生成问题记录。 |
| 默认值 | 必填源字段缺失且有默认值时补齐目标字段。 |
| 重复目标字段 | 能识别并避免静默覆盖。 |
| 报告输出 | 能生成 `field_mapping_report.json`。 |
| 接口稳定性 | `process_dataframe` 可被编排层调用。 |
