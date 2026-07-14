---
name: dataset-before-after-diff-comparator
description: 当用户需要对清洗前后的数据集进行比对，识别新增行、删除行、字段值变更，并为 CSV、JSON 或 JSONL 结构化数据集生成差异汇总时使用本 skill。
---

# Skill概述

`dataset-before-after-diff-comparator` 用于比较清洗前后结构化或半结构化数据集的差异。

该 Skill 面向高质量数据集建设中的版本回溯和交付说明环节，适合作为数据集说明文档、目录元数据和封装交付前的差异依据。

# 功能范围

## 支持能力

- CSV 数据读取。
- JSON 数据读取。
- JSONL 数据读取。
- 按主键字段对齐记录。
- 新增记录识别。
- 删除记录识别。
- 字段值变更识别。
- 字段级变更统计。
- 差异摘要生成。
- 稳定接口供后续说明文档和交付产线调用。

## 不支持能力

- 不支持综合质量评分。
- 不修复数据。
- 不修改输入文件。
- 不做语义相似度判断。
- 不做非结构化文本、图像、音频、视频差异对比。

# 输入定义

## 数据文件

支持以下输入：

| 格式 | 要求 |
|---|---|
| CSV | 第一行为字段名，建议 UTF-8 编码。 |
| JSON | 推荐为对象数组。 |
| JSONL | 每行一个 JSON 对象。 |

## 主键字段

主键字段用于对齐清洗前后的记录。支持单字段或组合字段。命令行中组合字段使用英文逗号分隔。

# 输出定义

## diff_summary

差异摘要，包含：

- `before_rows`
- `after_rows`
- `added_rows`
- `removed_rows`
- `changed_records`
- `changed_cells`
- `compared_fields`
- `key_fields`
- `lineage_fields`（若输入包含 `_source_file/_source_row/_record_hash/_batch_id/_rule_version`，会在摘要中标记）

## added_rows

清洗后新增记录，字段包括：

- `record_key`
- `raw_record`
- `source_row`
- `record_hash`

## removed_rows

清洗后被删除的记录，字段包括：

- `record_key`
- `raw_record`

## changed_rows

字段值变更记录，字段包括：

- `record_key`
- `field`
- `before_value`
- `after_value`
- `before_source_row`
- `after_source_row`
- `before_record_hash`
- `after_record_hash`

## field_change_summary

按字段统计变更单元格数量。

# 处理流程

1. 读取清洗前数据和清洗后数据。
2. 校验主键字段是否存在。
3. 校验主键在清洗前后数据中是否唯一。
4. 根据主键对齐记录。
5. 识别新增记录、删除记录和字段值变化。
6. 输出差异摘要、新增记录、删除记录、字段变更和字段变更统计。

# 稳定接口

```python
compare_dataframes(before_dataframe, after_dataframe, key_fields) -> dict
compare_dataset_files(before_path, after_path, key_fields, output_dir) -> dict[str, Path]
```

# 命令行入口

```bash
python scripts/compare_datasets.py before.csv after.csv id output_dir
```

# 验收标准

| 验收项 | 标准 |
|---|---|
| 文件读取 | 能读取 CSV、JSON、JSONL。 |
| 主键校验 | 主键缺失或重复时返回清晰错误。 |
| 新增识别 | 能输出 `added_rows.csv`。 |
| 删除识别 | 能输出 `removed_rows.csv`。 |
| 变更识别 | 能输出 `changed_rows.csv`。 |
| 字段统计 | 能输出 `field_change_summary.csv`。 |
| 摘要输出 | 能输出 `diff_summary.json`。 |
| 接口稳定性 | 稳定接口可被后续交付产线调用。 |
