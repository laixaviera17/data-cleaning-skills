# 招聘方 2 分钟演示

运行 `python scripts/run_recruiter_demo.py` 后，Demo 使用仓库内 `csv-json-data-cleaning-pipeline/examples/manual_demo/input_dirty.csv` 的 16 行模拟脏数据；既不读取生产数据，也不访问网络、数据库或云服务。

```mermaid
flowchart LR
    A[公开模拟脏数据] --> B[CSV/JSON 清洗编排]
    B --> C[缺失值处理与格式标准化]
    C --> D[异常检测与问题归集]
    D --> E[清洗后数据与操作日志]
    E --> F[文档、元数据、校验和与交付包]
```

## 实际复用的模块

| 环节 | 复用模块 | 产出 |
| --- | --- | --- |
| 清洗编排 | `csv-json-data-cleaning-pipeline` | `cleaned_data.csv`、`issue_rows.csv`、`cleaning_log.csv` |
| 原子校验 | `missing-value-checker`、`format-standardizer`、`abnormal-value-detector` | 缺失、格式与范围/枚举问题记录 |
| 过程追踪 | `structured-issue-list-generator`、`cleaning-operation-log-generator`、`dataset-before-after-diff-comparator` | 归一化问题清单、日志与前后差异 |
| 交付资料 | `dataset-documentation-generator`、`dataset-catalog-metadata-generator`、`cleaned-dataset-delivery-packager` | 文档、元数据、manifest、校验和与 ZIP 包 |

## 输出目录

`demo/output/` 每次运行会重新生成，且已被 Git 忽略。

| 文件 | 用途 |
| --- | --- |
| `cleaned_data.csv` | 规则处理后的可交付数据及追溯字段 |
| `issue_rows.csv` | 重复、缺失、格式与异常问题明细 |
| `cleaning_log.csv` | 各处理步骤和受影响行数 |
| `summary.json` | 固定路径的输入、输出、问题和处理统计 |
| `delivery_manifest.json` | 交付包文件清单与 SHA-256 校验信息 |
| `delivery/delivery_package.zip` | 可交付的数据、报告、日志、文档与元数据归档 |

该 Demo 仅用于展示规则驱动的本地结构化数据处理，不声称提供生产级实时处理、分布式调度或真实生产数据治理能力。

公开样例故意重复 `id` 以展示去重，因此前后差异报告使用 `id + title + content` 作为仅供比较用的唯一复合键；这不会改变流水线中以 `id` 为准的去重规则。
