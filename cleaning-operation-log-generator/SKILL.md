---
name: cleaning-operation-log-generator
description: 当用户需要对结构化数据清洗工具产生的清洗操作日志进行规范化、合并或汇总时使用本 skill，尤其针对已有的 cleaning_log.csv 文件或 JSON 清洗步骤日志，用于在数据集文档化或交付打包前提供可追溯性。
---

# Skill概述

`cleaning-operation-log-generator` 用于将多个清洗处理工具输出的操作日志统一为标准 `cleaning_log.csv`。

该 Skill 面向高质量数据集建设中的清洗追溯环节，适合作为数据集说明文档、差异对比和封装交付前的清洗过程记录能力。

# 功能范围

## 支持能力

- 合并已有 `cleaning_log.csv`。
- 读取 JSON 清洗日志。
- 补齐统一日志 schema 的缺失字段。
- 根据文件名推断 `source_skill`。
- 生成清洗日志摘要。
- 按步骤和规则统计影响行数。
- 按执行结果统计成功、警告和失败情况。
- 稳定接口供后续说明文档和交付产线调用。

## 不支持能力

- 不支持平台权限审计。
- 不支持安全合规审计。
- 不支持综合质量评分。
- 不修改原始数据。
- 不修复脏数据。

# 输入定义

支持以下日志文件：

| 文件 | 说明 |
|---|---|
| `cleaning_log.csv` | 已有清洗操作日志。 |
| JSON 日志 | 根节点为数组，或包含 `cleaning_log`、`logs`、`records` 列表。 |

# 输出定义

## cleaning_log

统一清洗日志，字段固定为：

```text
timestamp,step,rule_name,action,affected_rows,result,message,source_skill,input_count,output_count
```

## cleaning_log_summary

日志摘要，包含：

- `total_steps`
- `source_count`
- `success_steps`
- `warning_steps`
- `failed_steps`
- `total_affected_rows`

## step_summary

按 `step` 和 `rule_name` 汇总步骤数量和影响行数。

## result_summary

按 `result` 汇总步骤数量和影响行数。

# 处理流程

1. 读取一个或多个 CSV/JSON 日志文件。
2. 将不同来源字段映射到统一日志 schema。
3. 缺失扩展列补空。
4. 根据文件名或原始记录补充 `source_skill`。
5. 合并所有日志记录。
6. 输出统一日志、摘要、步骤统计和结果统计。

# 稳定接口

```python
normalize_log_records(records, source_skill) -> list[dict]
generate_cleaning_log(input_paths, output_dir) -> dict[str, Path]
```

# 命令行入口

```bash
python scripts/generate_cleaning_log.py input_log1.csv input_log2.json output_dir
```

# 验收标准

| 验收项 | 标准 |
|---|---|
| 标准日志 | 能合并已有 `cleaning_log.csv`。 |
| JSON 日志 | 能读取数组或对象中的日志列表。 |
| 缺失列补齐 | 能补齐 `message`、`source_skill`、`input_count`、`output_count`。 |
| 空日志文件 | 能输出只有表头的 `cleaning_log.csv`。 |
| 摘要统计 | 能生成清洗日志摘要。 |
| 步骤统计 | 能生成 `step_summary.csv`。 |
| 结果统计 | 能生成 `result_summary.csv`。 |
| 接口稳定性 | 两个稳定接口可被后续交付产线调用。 |
