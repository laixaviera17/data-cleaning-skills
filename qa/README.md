# QA 运行说明

`run_qa.py` 会对每个 Skill 的 `tests/` 运行 pytest、估算脚本覆盖率，并在
`qa/reports/latest/` 下生成统一报告（`qa_report.json`、`index.html`、
`audit_report.md`）。报告的 JSON 结构见 `report_schema.md`。

## 环境要求

- **Python >= 3.10。** Skill 的脚本和测试使用了 PEP 604 联合类型注解
  （`X | None`、`list[...]`）。脚本通过 `from __future__ import annotations`
  延迟注解求值，因此在 Python 3.9 下也能导入；但受支持的基线版本是
  Python 3.10+。（在 3.9 下运行时，请确保每个测试文件都保留顶部的
  `from __future__ import annotations`。）
- 测试 / 运行依赖：`pytest`、`pandas`、`pyyaml`。各 Skill 具体需要哪些依赖，
  见其各自的 `requirements.txt`。

## 安装与运行

```bash
# 在工作区根目录执行
python3 -m venv .venv
.venv/bin/pip install pytest pandas pyyaml
.venv/bin/python qa/run_qa.py --python .venv/bin/python
```

`--python` 用于指定运行各 Skill 测试的解释器；请传入 venv 的解释器，
这样它的 `pytest` / `pandas` / `pyyaml` 才可见。不传时，若存在
`.venv/bin/python` 则使用它，否则使用当前解释器。

仅当没有任何 Skill 失败、且工作区集成测试通过时，退出码才为 `0`。

## 其它参数

- `--reports-dir DIR` —— 将报告写到 `qa/reports/latest` 以外的目录。
- `--timeout N` —— 单个 Skill 的测试超时时间（秒，默认 180）。
- `--keep-history` —— 运行前不清空报告目录。
