# 清洗规则配置说明

## 1. 文档目的

本文档说明如何编写 `rule_template.yaml`，帮助中级数据开发人员直接配置 CSV、JSON、JSONL 数据清洗规则。

规则文件的核心目标是把常见清洗动作配置化，包括必填字段检查、去重、缺失值处理、枚举值校验、日期格式校验、手机号校验、金额校验和自定义规则。

## 2. 配置基本原则

1. 规则应尽量明确字段名、处理动作和异常处理方式。
2. 先配置必填字段和去重字段，再配置字段值规则。
3. 可自动修复的规则应明确标准化方式。
4. 无法确认的数据应使用 `mark` 或 `manual_review`，不要强行修复。
5. 删除数据的规则应谨慎配置，并保留问题记录。

## 3. required_fields

### 3.1 用途

`required_fields` 用于定义必须存在或必须有值的字段，适合检查主键、标题、正文、来源、日期等关键字段。

### 3.2 配置格式

```yaml
required_fields:
  - field: "id"
    allow_blank: false
    action: "mark"
  - field: "content"
    allow_blank: false
    action: "drop"
```

字段说明：

| 配置项 | 说明 |
|---|---|
| field | 字段名称。 |
| allow_blank | 是否允许为空。 |
| action | 发现问题后的处理动作，如 mark、drop、ignore。 |

### 3.3 示例

```yaml
required_fields:
  - field: "id"
    allow_blank: false
    action: "mark"
  - field: "title"
    allow_blank: false
    action: "mark"
  - field: "content"
    allow_blank: false
    action: "drop"
```

### 3.4 常见错误

1. 字段名和输入文件表头不一致。
2. 把非关键字段设置为 `drop`，导致误删数据。
3. 未区分字段不存在和字段值为空。
4. `allow_blank` 使用字符串 `"false"`，而不是布尔值 `false`。

## 4. unique_keys

### 4.1 用途

`unique_keys` 用于定义去重规则，可以按单字段去重，也可以按组合字段去重。

### 4.2 配置格式

```yaml
unique_keys:
  enabled: true
  keys:
    - ["id"]
    - ["title", "source"]
  keep: "first"
  issue_action: "export"
```

字段说明：

| 配置项 | 说明 |
|---|---|
| enabled | 是否启用去重。 |
| keys | 去重字段列表，支持多个去重规则。 |
| keep | 保留策略，如 first、last、latest。 |
| issue_action | 重复记录处理方式，如 export、drop、mark。 |

### 4.3 示例

```yaml
unique_keys:
  enabled: true
  keys:
    - ["id"]
  keep: "first"
  issue_action: "export"
```

### 4.4 常见错误

1. 去重字段存在大量空值，导致误判重复。
2. 组合字段顺序写错或字段不存在。
3. 未明确保留策略。
4. 只删除重复数据，没有导出重复问题记录。

## 5. null_handling

### 5.1 用途

`null_handling` 用于定义缺失值识别范围和处理策略。

### 5.2 配置格式

```yaml
null_handling:
  null_values:
    - ""
    - "null"
    - "N/A"
    - "未知"
  strategies:
    - field: "content"
      action: "drop"
    - field: "source"
      action: "fill"
      fill_value: "unknown"
```

字段说明：

| 配置项 | 说明 |
|---|---|
| null_values | 被视为缺失值的取值列表。 |
| strategies | 不同字段的缺失值处理策略。 |
| field | 字段名称。 |
| action | 处理动作，如 drop、fill、mark、ignore。 |
| fill_value | 填充值，仅在 action 为 fill 时使用。 |

### 5.3 示例

```yaml
null_handling:
  null_values:
    - ""
    - "N/A"
    - "无"
  strategies:
    - field: "title"
      action: "mark"
    - field: "content"
      action: "drop"
```

### 5.4 常见错误

1. 未把业务中的占位值加入 `null_values`，例如 `未知`、`-`、`无数据`。
2. 对关键字段使用 `fill`，造成数据失真。
3. `fill_value` 类型与字段类型不一致。
4. 未记录被删除或填充的数据。

## 6. enum_rules

### 6.1 用途

`enum_rules` 用于校验字段值是否在允许范围内，并支持将原始值映射为标准值。

### 6.2 配置格式

```yaml
enum_rules:
  enabled: true
  fields:
    - field: "status"
      allowed_values:
        - "valid"
        - "invalid"
        - "pending"
      standard_mapping:
        "有效": "valid"
        "无效": "invalid"
        "待处理": "pending"
      invalid_action: "mark"
```

字段说明：

| 配置项 | 说明 |
|---|---|
| enabled | 是否启用枚举校验。 |
| fields | 需要校验的字段列表。 |
| allowed_values | 允许出现的标准值。 |
| standard_mapping | 原始值到标准值的映射。 |
| invalid_action | 非法值处理方式，如 mark、drop、manual_review。 |

### 6.3 示例

```yaml
enum_rules:
  enabled: true
  fields:
    - field: "category"
      allowed_values:
        - "news"
        - "finance"
        - "medical"
        - "law"
      invalid_action: "mark"
```

### 6.4 常见错误

1. `allowed_values` 与 `standard_mapping` 的标准值不一致。
2. 忘记配置业务中的中文同义值映射。
3. 把大小写不同的值当作不同类别。
4. 对未知值直接删除，导致后续无法复核。

## 7. date_rules

### 7.1 用途

`date_rules` 用于校验和标准化日期字段，适合处理不同来源中的日期格式不一致问题。

### 7.2 配置格式

```yaml
date_rules:
  enabled: true
  target_format: "YYYY-MM-DD"
  fields:
    - field: "publish_date"
      input_formats:
        - "YYYY-MM-DD"
        - "YYYY/MM/DD"
        - "YYYY年MM月DD日"
      invalid_action: "mark"
```

字段说明：

| 配置项 | 说明 |
|---|---|
| enabled | 是否启用日期规则。 |
| target_format | 输出目标日期格式。 |
| fields | 日期字段配置列表。 |
| input_formats | 允许识别的输入格式。 |
| invalid_action | 日期非法时的处理方式。 |

### 7.3 示例

```yaml
date_rules:
  enabled: true
  target_format: "YYYY-MM-DD"
  fields:
    - field: "publish_date"
      input_formats:
        - "YYYY-MM-DD"
        - "YYYY/MM/DD"
      invalid_action: "mark"
```

### 7.4 常见错误

1. 使用了实际程序不支持的日期格式符号。
2. 未考虑 `2026/06/16` 和 `2026-06-16` 同时存在的情况。
3. 对非法日期如 `2026-02-30` 未设置处理动作。
4. 日期字段中混入文本但未配置异常处理。

## 8. phone_rules

### 8.1 用途

`phone_rules` 用于校验和标准化手机号字段，适合联系人、采集来源、用户信息等数据场景。

### 8.2 配置格式

```yaml
phone_rules:
  enabled: true
  fields:
    - field: "phone"
      country_code: "CN"
      remove_separators: true
      invalid_action: "mark"
```

字段说明：

| 配置项 | 说明 |
|---|---|
| enabled | 是否启用手机号规则。 |
| field | 手机号字段。 |
| country_code | 国家或地区编码。 |
| remove_separators | 是否移除空格、横线等分隔符。 |
| invalid_action | 手机号非法时的处理方式。 |

### 8.3 示例

```yaml
phone_rules:
  enabled: true
  fields:
    - field: "phone"
      country_code: "CN"
      remove_separators: true
      invalid_action: "mark"
```

### 8.4 常见错误

1. 手机号字段包含空格、横线但未启用分隔符清理。
2. 未区分国内手机号和国际号码。
3. 将固定电话误判为手机号。
4. 未保留原始号码，导致复核困难。

## 9. amount_rules

### 9.1 用途

`amount_rules` 用于校验和标准化金额字段，适合金融、订单、交易、费用类数据。

### 9.2 配置格式

```yaml
amount_rules:
  enabled: true
  fields:
    - field: "amount"
      decimal_places: 2
      remove_currency_symbol: true
      allow_negative: false
      invalid_action: "mark"
```

字段说明：

| 配置项 | 说明 |
|---|---|
| enabled | 是否启用金额规则。 |
| field | 金额字段。 |
| decimal_places | 保留小数位数。 |
| remove_currency_symbol | 是否移除货币符号。 |
| allow_negative | 是否允许负数。 |
| invalid_action | 金额非法时的处理方式。 |

### 9.3 示例

```yaml
amount_rules:
  enabled: true
  fields:
    - field: "amount"
      decimal_places: 2
      remove_currency_symbol: true
      allow_negative: false
      invalid_action: "mark"
```

### 9.4 常见错误

1. 金额字段同时存在 `¥100`、`100元`、`1,000.50`，但未配置符号清理。
2. 负数是否允许没有明确。
3. 小数位规则与业务口径不一致。
4. 无法转换的金额没有输出到问题数据。

## 10. custom_rules

### 10.1 用途

`custom_rules` 用于定义项目级的简单业务规则，例如字段长度、数值范围、字段关系等。

### 10.2 配置格式

```yaml
custom_rules:
  enabled: true
  rules:
    - name: "content_min_length"
      field: "content"
      rule_type: "min_length"
      value: 10
      invalid_action: "mark"
    - name: "score_range"
      field: "score"
      rule_type: "range"
      min: 0
      max: 100
      invalid_action: "mark"
```

字段说明：

| 配置项 | 说明 |
|---|---|
| name | 规则名称。 |
| field | 规则作用字段。 |
| rule_type | 规则类型，如 min_length、max_length、range、regex。 |
| value | 单值规则参数。 |
| min | 范围最小值。 |
| max | 范围最大值。 |
| invalid_action | 不符合规则时的处理方式。 |

### 10.3 示例

```yaml
custom_rules:
  enabled: true
  rules:
    - name: "title_min_length"
      field: "title"
      rule_type: "min_length"
      value: 4
      invalid_action: "mark"
```

### 10.4 常见错误

1. 自定义规则写得过多，导致配置难以维护。
2. 规则名称不清晰，日志中难以理解。
3. 未说明规则阈值来源。
4. 复杂逻辑强行写入规则配置，导致后续实现困难。

## 11. 推荐完整配置结构

```yaml
required_fields: []
unique_keys: {}
null_handling: {}
enum_rules: {}
date_rules: {}
phone_rules: {}
amount_rules: {}
custom_rules: {}
```

实际项目中可根据数据类型启用部分规则，不需要每次都配置全部规则。

## 12. 配置验收清单

| 检查项 | 是否应满足 |
|---|---|
| 必填字段是否与输入文件一致 | 是 |
| 去重字段是否存在且稳定 | 是 |
| 缺失值列表是否覆盖业务占位值 | 是 |
| 枚举值是否有标准值范围 | 是 |
| 日期、手机号、金额规则是否明确异常动作 | 是 |
| 自定义规则是否简单可解释 | 是 |
| 删除、填充、标准化动作是否可追溯 | 是 |
