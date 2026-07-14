# 标准输出文件格式说明

## 1. 文档目的

本文档定义 `CSV/JSON数据批量清洗产线` 的标准输出文件格式，确保清洗后数据、问题数据、统计结果和清洗日志具备统一结构，便于后续验收、追溯、复核和交付。

本 Skill 的标准输出包括：

- `cleaned_data`
- `issue_rows`
- `cleaning_summary`
- `cleaning_log`

## 2. cleaned_data

### 2.1 字段要求

`cleaned_data` 用于保存清洗后的有效数据。字段应以原始数据字段为基础，并结合字段映射和标准化规则输出。

字段要求：

1. 应保留业务使用所需的核心字段。
2. 字段名称应与字段映射结果或标准字段名称一致。
3. 已执行格式标准化的字段，应输出标准化后的值。
4. 被判定为删除的数据不应出现在 `cleaned_data` 中。
5. 如保留被标记的问题数据，应有明确的问题标记字段或在 `issue_rows` 中保留对应记录。

推荐字段示例：

| 字段 | 说明 |
|---|---|
| id | 数据唯一编号。 |
| title | 数据标题。 |
| content | 数据正文或主要内容。 |
| publish_date | 标准化后的发布日期。 |
| phone | 标准化后的手机号。 |
| amount | 标准化后的金额。 |
| status | 标准化后的状态值。 |
| category | 数据类别。 |
| source | 数据来源。 |

### 2.2 文件格式

支持以下文件格式：

| 格式 | 说明 |
|---|---|
| CSV | 推荐用于表格型数据交付和人工查看。 |
| JSON | 推荐用于系统接口或对象数组交付。 |
| JSONL | 推荐用于大规模数据和逐行处理场景。 |

默认建议输出 CSV，文件名使用 `cleaned_data_YYYYMMDD.csv`。

### 2.3 编码要求

1. 默认使用 UTF-8 编码。
2. CSV 文件建议使用 UTF-8 with BOM 或 UTF-8，具体根据下游系统要求选择。
3. 换行符建议统一为 LF。
4. 字段中如包含逗号、换行或引号，应按 CSV 标准进行转义。

### 2.4 命名规范

推荐命名：

```text
cleaned_data_YYYYMMDD.csv
cleaned_data_YYYYMMDD.json
cleaned_data_YYYYMMDD.jsonl
```

示例：

```text
cleaned_data_20260616.csv
```

## 3. issue_rows

### 3.1 文件用途

`issue_rows` 用于保存清洗过程中发现的问题数据，便于人工复核、规则调整和数据源整改。

### 3.2 错误类型

建议使用统一错误类型，便于统计和治理。

| 错误类型 | 说明 |
|---|---|
| duplicate | 重复数据。 |
| missing_field | 缺少字段。 |
| missing_value | 字段值缺失。 |
| invalid_date | 日期格式错误或日期无法解析。 |
| invalid_phone | 手机号格式错误。 |
| invalid_amount | 金额格式错误。 |
| enum_invalid | 枚举值不在允许范围内。 |
| out_of_range | 数值超出设定范围。 |
| low_quality | 内容过短、无意义或明显低质量。 |
| inconsistent | 字段之间存在逻辑冲突。 |

### 3.3 统一 issue schema

`issue_rows` 采用统一字段，便于接收来自不同原子 Skill 的问题记录。

| 字段 | 说明 |
|---|---|
| row | 数据行号，从 1 开始；字段级问题无法定位到具体行时为空。 |
| field | 问题字段名。 |
| value | 原始问题值。 |
| issue_type | 问题类型，如 `duplicate`、`missing_field`、`standardization_failed`、`out_of_range`。 |
| reason | 问题原因。 |
| source_skill | 问题来源 Skill，如 `missing-value-checker`、`format-standardizer`、`abnormal-value-detector`。 |
| action | 处理动作，如 `drop`、`check`、`standardize`、`detect`。 |
| record_id | 可选，业务主键。 |
| process_result | 可选，处理结果。 |
| raw_record | 可选，原始记录 JSON 字符串。 |

### 3.4 错误原因

`reason` 应简洁说明问题原因，建议包含规则依据。

示例：

| issue_type | reason |
|---|---|
| duplicate | `id` 与已有记录重复。 |
| missing_value | `content` 为空，且该字段为必填字段。 |
| invalid_date | `publish_date` 不符合 `YYYY-MM-DD` 格式。 |
| invalid_phone | `phone` 包含非数字字符或长度不符合要求。 |
| invalid_amount | `amount` 无法转换为合法金额。 |

### 3.5 原始记录

问题数据应尽量保留原始记录，便于人工复核。

原始记录建议放在 `raw_record` 字段中，使用 JSON 字符串保存；如有业务主键，可同步写入 `record_id`。

### 3.6 建议处理方式

| action | 说明 |
|---|---|
| drop | 建议删除该记录。 |
| fill | 建议填充默认值或补充缺失值。 |
| standardize | 建议标准化为合法格式。 |
| detect | 仅检测并输出异常，不自动修复。 |
| manual_review | 建议人工复核。 |
| keep_with_mark | 建议保留但标记问题。 |

## 4. cleaning_summary

### 4.1 文件用途

`cleaning_summary` 用于汇总本次清洗任务的整体统计结果，适合输出为 JSON 文件。

### 4.2 统计指标

必须包含以下指标：

| 指标 | 说明 |
|---|---|
| input_rows | 输入总记录数。 |
| output_rows | 清洗后输出记录数。 |
| removed_rows | 被删除的记录数。 |
| duplicate_rows | 重复记录数。 |
| null_rows | 存在缺失值问题的记录数。 |
| abnormal_rows | 存在异常值、非法格式、非法枚举等问题的记录数。 |
| repaired_rows | 被自动修复或标准化处理的记录数。 |

可选指标：

| 指标 | 说明 |
|---|---|
| issue_rows | 问题记录总数。 |
| issue_type_count | 按问题类型统计的数量。 |
| rule_result | 按规则统计的执行结果。 |
| start_time | 清洗开始时间。 |
| end_time | 清洗结束时间。 |

### 4.3 JSON结构示例

```json
{
  "task_name": "sample_cleaning_task",
  "input_file": "examples/sample_input.csv",
  "output_dir": "examples/expected_outputs",
  "start_time": "2026-06-16 10:00:00",
  "end_time": "2026-06-16 10:00:05",
  "input_rows": 25,
  "output_rows": 16,
  "removed_rows": 4,
  "duplicate_rows": 3,
  "null_rows": 4,
  "abnormal_rows": 8,
  "repaired_rows": 6,
  "issue_type_count": {
    "duplicate": 3,
    "missing_value": 4,
    "invalid_date": 2,
    "invalid_phone": 3,
    "invalid_amount": 3,
    "enum_invalid": 2,
    "low_quality": 1
  },
  "result": "success"
}
```

## 5. cleaning_log

### 5.1 文件用途

`cleaning_log` 用于记录每一步清洗操作，支撑清洗追溯和问题定位。建议输出为 CSV。

### 5.2 字段定义

| 字段 | 说明 |
|---|---|
| timestamp | 操作发生时间。 |
| rule_name | 执行的规则名称。 |
| action | 执行动作，如 check、drop、fill、standardize、export。 |
| affected_rows | 本次规则影响的记录数。 |
| result | 执行结果，如 success、warning、failed。 |

建议扩展字段：

| 字段 | 说明 |
|---|---|
| message | 规则执行说明。 |
| input_count | 执行前记录数。 |
| output_count | 执行后记录数。 |

### 5.3 CSV格式示例

```text
timestamp,rule_name,action,affected_rows,result,message
2026-06-16 10:00:00,load_input,check,25,success,读取输入文件成功
2026-06-16 10:00:01,required_fields,check,4,warning,发现必填字段缺失或为空
2026-06-16 10:00:02,unique_keys,drop,3,success,删除重复记录
2026-06-16 10:00:03,date_rules,standardize,2,warning,发现日期格式错误
2026-06-16 10:00:04,export_issue_rows,export,10,success,导出问题数据
```

## 6. 文件命名规范

标准命名建议：

```text
cleaned_data_YYYYMMDD.csv
issue_rows_YYYYMMDD.csv
cleaning_summary_YYYYMMDD.json
cleaning_log_YYYYMMDD.csv
```

示例：

```text
cleaned_data_20260616.csv
issue_rows_20260616.csv
cleaning_summary_20260616.json
cleaning_log_20260616.csv
```

命名要求：

1. 文件名前缀固定，便于程序识别。
2. 日期使用 8 位数字格式 `YYYYMMDD`。
3. 同一批次输出文件日期应保持一致。
4. 如同一天多次执行，可追加批次号，例如 `cleaned_data_20260616_batch01.csv`。

## 7. 输出目录规范

### 7.1 推荐目录

示例输出目录：

```text
expected_outputs/
├── cleaned_data_YYYYMMDD.csv
├── issue_rows_YYYYMMDD.csv
├── cleaning_summary_YYYYMMDD.json
├── cleaning_log_YYYYMMDD.csv
└── README.md
```

### 7.2 目录结构说明

| 文件 | 说明 |
|---|---|
| `cleaned_data_YYYYMMDD.csv` | 清洗后的有效数据。 |
| `issue_rows_YYYYMMDD.csv` | 清洗过程中发现的问题数据。 |
| `cleaning_summary_YYYYMMDD.json` | 清洗统计结果。 |
| `cleaning_log_YYYYMMDD.csv` | 清洗过程日志。 |
| `README.md` | 说明预期输出结果和验收口径。 |

### 7.3 输出要求

1. 每次清洗任务应输出到独立目录或独立批次文件。
2. 输出目录中应至少包含 `cleaned_data`、`issue_rows`、`cleaning_summary`、`cleaning_log` 四类文件。
3. 如没有问题数据，仍建议生成空的 `issue_rows` 文件并保留表头。
4. 输出文件应能支撑清洗结果复核和过程追溯。
