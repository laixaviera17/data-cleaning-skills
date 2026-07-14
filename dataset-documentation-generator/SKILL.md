---
name: dataset-documentation-generator
description: 当用户需要为清洗后的 CSV、JSON 或 JSONL 数据集生成人类可读的数据集文档时使用本 skill，尤其是 README 风格的交付说明，包含基本信息、内容特征、构建过程、应用说明、质量汇总、问题清单、清洗日志以及清洗前后差异汇总。
---

# Skill概述

`dataset-documentation-generator` 用于为清洗后的结构化数据集生成面向交付和人工阅读的 `dataset_readme.md`。

该 Skill 对应高质量数据集封装中的“文档生成”要求，只负责说明文档生成。它可以读取已有质量报告、问题清单、差异摘要和清洗日志来汇总说明，但不重新清洗数据、不检测异常、不生成目录元数据、不打包交付目录。

# 功能范围

## 支持能力

- 读取 CSV、JSON、JSONL 数据文件。
- 统计记录数、字段数、字段名和简单字段类型。
- 读取 JSON 报告并提取关键摘要。
- 读取 CSV 问题清单或清洗日志并统计行数。
- 生成 Markdown 格式 `dataset_readme.md`。

## 不支持能力

- 不修改数据。
- 不做质量评分。
- 不生成机器目录元数据。
- 不打包交付目录或 zip。
- 不处理图像、音频、视频等非表格数据。

# 输出定义

`dataset_readme.md` 包含：

- 数据集名称。
- 数据文件信息。
- 行数和字段数。
- 字段概览。
- 质量、清洗、差异报告摘要。
- 应用说明和交付备注。

# 稳定接口

```python
generate_dataset_documentation(data_path, output_dir, dataset_name=None, reports=None) -> dict
```

# 命令行入口

```bash
python scripts/generate_dataset_documentation.py cleaned_data.csv output_dir --dataset-name demo --report cleaning_summary.json
```

# 验收标准

- 能读取 CSV、JSON、JSONL。
- 能生成 `dataset_readme.md`。
- 能包含字段概览和记录统计。
- 能汇总 JSON/CSV 附件报告。
- 缺失输入文件时返回清晰错误。
