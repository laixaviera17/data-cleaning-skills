---
name: structured-issue-list-generator
description: 当用户需要将结构化数据清洗的各类问题输出合并并规范化为标准的 issue_rows.csv 文件时使用本 skill，尤其是来自 CSV 问题行、字段映射问题、字典校验问题、格式标准化问题或异常值检测 JSON 报告的输出。
---

# Skill概述

`structured-issue-list-generator` 用于将多个清洗类 Skill 的问题输出统一为标准 `issue_rows.csv`。

该 Skill 面向高质量数据集建设中的问题数据归集环节，适合作为清洗日志、差异对比、说明文档和封装交付前的公共问题清单能力。

# 功能范围

## 支持能力

- 合并标准 `issue_rows.csv`。
- 归一化 `mapping_issues.csv`。
- 归一化 `dictionary_issues.csv`。
- 读取 `abnormal_records.json` 中的 `abnormal_records`。
- 补齐统一 issue schema 的缺失字段。
- 根据文件名推断 `source_skill`。
- 生成问题类型统计。
- 生成字段级问题统计。
- 生成问题摘要 JSON。

## 不支持能力

- 不支持综合质量评分。
- 不修复脏数据。
- 不修改原始数据。
- 不做日志审计。
- 不做数据脱敏、编码修复或 JSON Schema 校验。

# 输入定义

支持以下问题文件：

| 文件 | 说明 |
|---|---|
| `issue_rows.csv` | 已经符合统一 schema 的问题清单。 |
| `mapping_issues.csv` | 字段映射工具输出的问题清单。 |
| `dictionary_issues.csv` | 字典校验工具输出的问题清单。 |
| `abnormal_records.json` | 异常值或格式标准化工具输出的异常记录。 |

# 输出定义

## issue_rows

统一问题清单，字段固定为：

```text
row,field,value,issue_type,reason,source_skill,action,record_id,process_result,raw_record
```

## issue_summary

问题摘要，包含：

- `total_issues`
- `source_count`
- `issue_type_count`
- `field_count`

## issue_type_summary

按 `issue_type` 统计问题数量。

## field_issue_summary

按 `field` 统计问题数量。

# 处理流程

1. 读取一个或多个 CSV/JSON 问题文件。
2. 根据文件结构识别问题记录。
3. 将不同来源字段映射到统一 issue schema。
4. 缺失的可选列补空。
5. 根据文件名或原始记录补充 `source_skill`。
6. 合并所有问题记录。
7. 输出统一问题清单、摘要、问题类型统计和字段统计。

# 稳定接口

```python
normalize_issue_records(records, source_skill) -> list[dict]
generate_issue_list(input_paths, output_dir) -> dict[str, Path]
```

# 命令行入口

```bash
python scripts/generate_issue_list.py input1.csv input2.json output_dir
```

# 验收标准

| 验收项 | 标准 |
|---|---|
| 标准问题清单 | 能合并已有 `issue_rows.csv`。 |
| 字段映射问题 | 能转换 `mapping_issues.csv`。 |
| 字典问题 | 能转换 `dictionary_issues.csv`。 |
| 异常记录 | 能读取 JSON 中的 `abnormal_records`。 |
| 空问题文件 | 能输出只有表头的 `issue_rows.csv`。 |
| 统计输出 | 能生成摘要、问题类型统计和字段统计。 |
| 接口稳定性 | 两个稳定接口可被后续交付产线调用。 |
