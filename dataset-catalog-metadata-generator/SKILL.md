---
name: dataset-catalog-metadata-generator
description: 当用户需要为清洗后的 CSV、JSON 或 JSONL 数据集生成机器可读的编目元数据时使用本 skill，包括数据集标识、模式、文件清单、校验和、质量汇总引用、血缘、许可证、标签、版本、授权说明以及用于编目注册的交付元数据。
---

# Skill概述

`dataset-catalog-metadata-generator` 用于生成面向目录登记、资产索引和交付系统读取的 `catalog_metadata.json`。

该 Skill 对应高质量数据集封装交付中的“数据登记”和“元数据必填字段”要求。它不同于说明文档生成器：说明文档面向人读，本 Skill 面向系统读取。

# 功能范围

## 支持能力

- 读取 CSV、JSON、JSONL 主数据文件。
- 生成数据集 ID、名称、版本、生成时间和文件清单。
- 统计记录数、字段数、字段名、简单类型和空值数量。
- 计算文件 SHA256。
- 合并用户提供的描述、标签、许可证、来源、授权类型和版本。
- 关联质量报告、问题清单、清洗日志、差异摘要等附件。
- 输出 `catalog_metadata.json`。

## 不支持能力

- 不生成 Markdown 说明文档。
- 不打包 zip。
- 不执行数据清洗或检测。
- 不做权限审计、血缘图谱推断或质量评分。

# 稳定接口

```python
generate_catalog_metadata(data_path, output_dir, dataset_name=None, config_path=None, artifacts=None) -> dict
```

# 命令行入口

```bash
python scripts/generate_catalog_metadata.py cleaned_data.csv output_dir --dataset-name demo --config metadata_config.json --artifact issue_rows.csv
```

# 验收标准

- 能读取 CSV、JSON、JSONL。
- 能输出 `catalog_metadata.json`。
- 能包含 schema、file inventory、checksum、row count。
- 能合并配置文件中的描述、标签、许可证、来源、授权和版本。
- 缺失输入文件时返回清晰错误。
