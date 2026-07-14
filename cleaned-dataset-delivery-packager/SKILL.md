---
name: cleaned-dataset-delivery-packager
description: 当用户需要将清洗后的 CSV、JSON 或 JSONL 数据集，连同报告、问题行、清洗日志、元数据、文档、清单、校验和、授权说明以及 zip 压缩包等交付物一起打包，用于交接、发布或高质量数据集交付时使用本 skill。
---

# Skill概述

`cleaned-dataset-delivery-packager` 用于将清洗后的数据文件和交付附件封装为标准交付目录。

该 Skill 对应高质量数据集建设平台中的“数据封装交付”环节，只负责组装、归档、清点、生成 manifest、生成 checksum 和压缩包。不要在本 Skill 中重新执行数据清洗、问题检测、质量评分、说明文档正文生成或目录元数据生成。

# 功能范围

## 支持能力

- 接收一个清洗后主数据文件。
- 接收多个附件文件，例如质量报告、问题清单、差异摘要、清洗日志、说明文档、目录元数据、授权说明。
- 按文件角色归档到 `data/`、`reports/`、`logs/`、`metadata/`、`docs/`、`extras/`。
- 生成 `manifest.json`。
- 生成 `checksums.csv`。
- 生成交付压缩包 `delivery_package.zip`。

## 不支持能力

- 不清洗数据。
- 不生成问题清单。
- 不生成说明文档正文。
- 不生成目录元数据内容。
- 不做权限、安全、隐私或质量评分审计。

# 输出结构

```text
output_dir/
├── package/
│   ├── data/
│   ├── reports/
│   ├── logs/
│   ├── metadata/
│   ├── docs/
│   ├── extras/
│   ├── manifest.json
│   └── checksums.csv
└── delivery_package.zip
```

# 稳定接口

```python
package_dataset(cleaned_data_path, output_dir, artifacts=None, dataset_name=None) -> dict
```

# 命令行入口

```bash
python scripts/package_cleaned_dataset.py cleaned_data.csv output_dir --artifact report.json --artifact cleaning_log.csv --dataset-name demo
```

# 验收标准

- 能复制清洗后主数据文件到 `package/data/`。
- 能按附件文件名归类报告、日志、元数据和文档。
- 能生成 `manifest.json` 和 `checksums.csv`。
- 能生成 `delivery_package.zip`。
- 缺失输入文件时返回清晰错误。
