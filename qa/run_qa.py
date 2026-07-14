#!/usr/bin/env python3
"""Workspace QA runner for all dataset Skills.

This script is intentionally outside every Skill. It adds a QA layer without
changing business logic.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


COVERAGE_RE = re.compile(r"^\s*(?P<lines>\d+)\s+(?P<coverage>\d+(?:\.\d+)?)%\s+\S+\s+\((?P<path>.+\.py)\)$")


@dataclass
class FileCoverage:
    path: str
    lines: int
    coverage_percent: float


@dataclass
class SkillReport:
    name: str
    path: str
    status: str
    duration_seconds: float
    tests: int
    passed: int
    failures: int
    errors: int
    skipped: int
    coverage_percent: float
    scripts: int
    test_files: int
    readme_exists: bool
    skill_md_exists: bool
    junit_path: str
    log_path: str
    file_coverage: list[FileCoverage]
    issues: list[str]


@dataclass
class WorkspaceTestReport:
    status: str
    duration_seconds: float
    tests: int
    passed: int
    failures: int
    errors: int
    skipped: int
    junit_path: str
    log_path: str
    issues: list[str]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QA for all Skills in this workspace.")
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--python", default=None, help="Python executable. Defaults to .venv/bin/python when present.")
    parser.add_argument("--reports-dir", default=None)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--keep-history", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    python_exe = resolve_python(workspace, args.python)
    reports_dir = Path(args.reports_dir).expanduser().resolve() if args.reports_dir else workspace / "qa" / "reports" / "latest"

    if reports_dir.exists() and not args.keep_history:
        shutil.rmtree(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ("junit", "logs", "coverage", "assets"):
        (reports_dir / subdir).mkdir(parents=True, exist_ok=True)

    skills = discover_skills(workspace)
    started = datetime.now(timezone.utc)
    reports = []
    for skill in skills:
        print(f"===== QA testing {skill.name} =====")
        reports.append(run_skill_qa(skill, python_exe, reports_dir, args.timeout))

    workspace_tests = run_workspace_tests(workspace, python_exe, reports_dir, args.timeout)
    summary = build_summary(workspace, python_exe, started, reports, workspace_tests)
    report_payload = {
        "summary": summary,
        "skills": [serialize_report(report, reports_dir) for report in reports],
        "workspace_tests": serialize_workspace_tests(workspace_tests, reports_dir),
    }

    write_json(reports_dir / "qa_report.json", report_payload)
    write_markdown_audit(reports_dir / "audit_report.md", report_payload)
    write_charts(reports_dir / "assets", report_payload)
    write_html_report(reports_dir / "index.html", report_payload)

    print("")
    print(f"QA report JSON: {reports_dir / 'qa_report.json'}")
    print(f"HTML report:    {reports_dir / 'index.html'}")
    print(f"Audit report:   {reports_dir / 'audit_report.md'}")
    return 0 if summary["failed_skills"] == 0 and summary["workspace_test_failures"] == 0 else 1


@dataclass(frozen=True)
class Skill:
    name: str
    path: Path


def resolve_python(workspace: Path, override: str | None) -> str:
    if override:
        # Do not call .resolve(): a venv's bin/python is often a symlink to the
        # base interpreter, and following it drops the venv's site-packages
        # (pytest/pandas become unavailable). abspath normalizes without
        # dereferencing the symlink.
        return os.path.abspath(os.path.expanduser(override))
    venv_python = workspace / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def discover_skills(workspace: Path) -> list[Skill]:
    skills = []
    for child in sorted(workspace.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or child.name in {"qa"}:
            continue
        if (child / "SKILL.md").is_file():
            skills.append(Skill(child.name, child))
    return skills


def run_skill_qa(skill: Skill, python_exe: str, reports_dir: Path, timeout: int) -> SkillReport:
    start = time.perf_counter()
    junit_path = reports_dir / "junit" / f"{skill.name}.xml"
    log_path = reports_dir / "logs" / f"{skill.name}.log"
    coverdir = reports_dir / "coverage" / skill.name
    coverdir.mkdir(parents=True, exist_ok=True)

    command = [
        python_exe,
        "-m",
        "trace",
        "--count",
        "--missing",
        "--summary",
        "--coverdir",
        str(coverdir),
        "--ignore-dir",
        str(Path(python_exe).resolve().parents[1]),
        "--module",
        "pytest",
        "-q",
        "--tb=short",
        f"--junitxml={junit_path}",
    ]

    try:
        completed = subprocess.run(
            command,
            cwd=skill.path,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        return_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return_code = 124
        stderr += f"\nQA timeout after {timeout} seconds\n"

    log_path.write_text(stdout + ("\n[stderr]\n" + stderr if stderr else ""), encoding="utf-8")
    duration = time.perf_counter() - start

    junit = parse_junit(junit_path)
    file_coverage = parse_trace_coverage(stdout, skill.path)
    file_coverage = include_unexecuted_scripts(skill.path, file_coverage)
    write_clean_coverage_dir(coverdir, file_coverage)
    coverage_percent = weighted_coverage(file_coverage)

    scripts = list((skill.path / "scripts").glob("*.py")) if (skill.path / "scripts").exists() else []
    tests = list((skill.path / "tests").glob("test_*.py")) if (skill.path / "tests").exists() else []
    issues = collect_issues(skill.path, junit, coverage_percent, return_code)
    status = "passed" if return_code == 0 and junit["failures"] == 0 and junit["errors"] == 0 else "failed"
    passed = max(junit["tests"] - junit["failures"] - junit["errors"] - junit["skipped"], 0)

    return SkillReport(
        name=skill.name,
        path=str(skill.path),
        status=status,
        duration_seconds=round(duration, 3),
        tests=junit["tests"],
        passed=passed,
        failures=junit["failures"],
        errors=junit["errors"],
        skipped=junit["skipped"],
        coverage_percent=round(coverage_percent, 1),
        scripts=len(scripts),
        test_files=len(tests),
        readme_exists=(skill.path / "README.md").is_file(),
        skill_md_exists=(skill.path / "SKILL.md").is_file(),
        junit_path=str(junit_path),
        log_path=str(log_path),
        file_coverage=file_coverage,
        issues=issues,
    )


def run_workspace_tests(workspace: Path, python_exe: str, reports_dir: Path, timeout: int) -> WorkspaceTestReport:
    tests_dir = workspace / "qa" / "tests"
    junit_path = reports_dir / "junit" / "workspace-tests.xml"
    log_path = reports_dir / "logs" / "workspace-tests.log"
    if not tests_dir.exists():
        return WorkspaceTestReport(
            status="skipped",
            duration_seconds=0.0,
            tests=0,
            passed=0,
            failures=0,
            errors=0,
            skipped=0,
            junit_path=str(junit_path),
            log_path=str(log_path),
            issues=["qa/tests directory missing"],
        )

    print("===== QA testing workspace integration =====")
    start = time.perf_counter()
    command = [python_exe, "-m", "pytest", "-q", str(tests_dir), f"--junitxml={junit_path}"]
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        return_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return_code = 124
        stderr += f"\nWorkspace QA timeout after {timeout} seconds\n"

    log_path.write_text(stdout + ("\n[stderr]\n" + stderr if stderr else ""), encoding="utf-8")
    junit = parse_junit(junit_path)
    status = "passed" if return_code == 0 and junit["failures"] == 0 and junit["errors"] == 0 else "failed"
    passed = max(junit["tests"] - junit["failures"] - junit["errors"] - junit["skipped"], 0)
    issues = []
    if return_code != 0:
        issues.append(f"pytest exited with code {return_code}")
    if junit["tests"] == 0:
        issues.append("no workspace integration tests collected")
    return WorkspaceTestReport(
        status=status,
        duration_seconds=round(time.perf_counter() - start, 3),
        tests=junit["tests"],
        passed=passed,
        failures=junit["failures"],
        errors=junit["errors"],
        skipped=junit["skipped"],
        junit_path=str(junit_path),
        log_path=str(log_path),
        issues=issues,
    )


def parse_junit(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"tests": 0, "failures": 0, "errors": 1, "skipped": 0}
    root = ET.parse(path).getroot()
    nodes = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for node in nodes:
        for key in totals:
            totals[key] += int(node.attrib.get(key, "0"))
    return totals


def parse_trace_coverage(stdout: str, skill_path: Path) -> list[FileCoverage]:
    by_path: dict[str, FileCoverage] = {}
    scripts_root = (skill_path / "scripts").resolve()
    for line in stdout.splitlines():
        match = COVERAGE_RE.match(line)
        if not match:
            continue
        path = Path(match.group("path")).resolve()
        try:
            path.relative_to(scripts_root)
        except ValueError:
            continue
        by_path[str(path)] = FileCoverage(
            path=str(path.relative_to(skill_path)),
            lines=int(match.group("lines")),
            coverage_percent=float(match.group("coverage")),
        )
    return sorted(by_path.values(), key=lambda item: item.path)


def include_unexecuted_scripts(skill_path: Path, coverage: list[FileCoverage]) -> list[FileCoverage]:
    known = {item.path for item in coverage}
    result = list(coverage)
    scripts_root = skill_path / "scripts"
    if not scripts_root.exists():
        return result
    for script in sorted(scripts_root.glob("*.py")):
        rel = str(script.relative_to(skill_path))
        if rel in known:
            continue
        result.append(FileCoverage(path=rel, lines=count_estimated_executable_lines(script), coverage_percent=0.0))
    return sorted(result, key=lambda item: item.path)


def write_clean_coverage_dir(coverdir: Path, coverage: list[FileCoverage]) -> None:
    """Replace noisy trace .cover files with a compact skill-only summary."""
    if coverdir.exists():
        shutil.rmtree(coverdir)
    coverdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "coverage_percent": round(weighted_coverage(coverage), 1),
        "files": [asdict(item) for item in coverage],
        "note": "Estimated script line coverage from Python trace summary.",
    }
    write_json(coverdir / "script_coverage.json", payload)


def count_estimated_executable_lines(path: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def weighted_coverage(items: list[FileCoverage]) -> float:
    total_lines = sum(item.lines for item in items)
    if total_lines == 0:
        return 0.0
    covered = sum(item.lines * item.coverage_percent / 100 for item in items)
    return covered / total_lines * 100


def collect_issues(skill_path: Path, junit: dict[str, int], coverage: float, return_code: int) -> list[str]:
    issues = []
    if return_code != 0:
        issues.append(f"pytest exited with code {return_code}")
    if junit["tests"] == 0:
        issues.append("no tests collected")
    if not (skill_path / "SKILL.md").exists() and not (skill_path / "README.md").exists():
        issues.append("skill documentation (SKILL.md/README.md) missing")
    if coverage < 60:
        issues.append(f"script coverage below 60% ({coverage:.1f}%)")
    if not (skill_path / "requirements.txt").exists():
        issues.append("requirements.txt missing")
    return issues


def build_summary(
    workspace: Path,
    python_exe: str,
    started: datetime,
    reports: list[SkillReport],
    workspace_tests: WorkspaceTestReport,
) -> dict:
    total_tests = sum(report.tests for report in reports) + workspace_tests.tests
    total_failures = sum(report.failures for report in reports)
    total_errors = sum(report.errors for report in reports)
    total_skipped = sum(report.skipped for report in reports) + workspace_tests.skipped
    total_passed = sum(report.passed for report in reports) + workspace_tests.passed
    failed_skills = sum(1 for report in reports if report.status != "passed")
    weighted_lines = sum(sum(item.lines for item in report.file_coverage) for report in reports)
    weighted_cov = 0.0
    if weighted_lines:
        weighted_cov = sum(
            sum(item.lines * item.coverage_percent / 100 for item in report.file_coverage)
            for report in reports
        ) / weighted_lines * 100
    return {
        "workspace": str(workspace),
        "python": python_exe,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started.isoformat(),
        "skill_count": len(reports),
        "failed_skills": failed_skills,
        "total_tests": total_tests,
        "total_passed": total_passed,
        "total_failures": total_failures,
        "total_errors": total_errors,
        "total_skipped": total_skipped,
        "workspace_tests": workspace_tests.tests,
        "workspace_test_failures": workspace_tests.failures + workspace_tests.errors + (1 if workspace_tests.status == "failed" else 0),
        "coverage_percent": round(weighted_cov, 1),
    }


def serialize_report(report: SkillReport, reports_dir: Path) -> dict:
    data = asdict(report)
    data["junit_path"] = relpath(report.junit_path, reports_dir)
    data["log_path"] = relpath(report.log_path, reports_dir)
    return data


def serialize_workspace_tests(report: WorkspaceTestReport, reports_dir: Path) -> dict:
    data = asdict(report)
    data["junit_path"] = relpath(report.junit_path, reports_dir)
    data["log_path"] = relpath(report.log_path, reports_dir)
    return data


def relpath(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return path


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown_audit(path: Path, payload: dict) -> None:
    summary = payload["summary"]
    lines = [
        "# Workspace QA Audit Report",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Skills: `{summary['skill_count']}`",
        f"- Tests: `{summary['total_passed']} passed / {summary['total_tests']} total`",
        f"- Failures: `{summary['total_failures']}`",
        f"- Errors: `{summary['total_errors']}`",
        f"- Workspace integration tests: `{summary['workspace_tests']}`",
        f"- Estimated script coverage: `{summary['coverage_percent']}%`",
        "",
        "## Skill Summary",
        "",
        "| Skill | Status | Tests | Coverage | Docs | Issues |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for skill in payload["skills"]:
        issues = "; ".join(skill["issues"]) if skill["issues"] else "None"
        readme = "yes" if (skill["skill_md_exists"] or skill["readme_exists"]) else "no"
        lines.append(
            f"| {skill['name']} | {skill['status']} | {skill['passed']}/{skill['tests']} | "
            f"{skill['coverage_percent']}% | {readme} | {issues} |"
        )
    workspace_tests = payload.get("workspace_tests", {})
    if workspace_tests:
        lines.extend([
            "",
            "## Workspace Integration Tests",
            "",
            f"- Status: `{workspace_tests['status']}`",
            f"- Tests: `{workspace_tests['passed']} passed / {workspace_tests['tests']} total`",
            f"- Issues: `{'; '.join(workspace_tests['issues']) if workspace_tests['issues'] else 'None'}`",
        ])
    lines.extend(["", "## Coverage Details", ""])
    for skill in payload["skills"]:
        lines.append(f"### {skill['name']}")
        lines.append("")
        lines.append("| File | Lines | Coverage |")
        lines.append("|---|---:|---:|")
        for item in skill["file_coverage"]:
            lines.append(f"| {item['path']} | {item['lines']} | {item['coverage_percent']}% |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_charts(assets_dir: Path, payload: dict) -> None:
    skills = payload["skills"]
    write_bar_chart(
        assets_dir / "coverage_by_skill.svg",
        "Coverage by Skill",
        [(skill["name"], skill["coverage_percent"]) for skill in skills],
        suffix="%",
        max_value=100,
    )
    write_bar_chart(
        assets_dir / "tests_by_skill.svg",
        "Tests by Skill",
        [(skill["name"], skill["tests"]) for skill in skills],
        suffix="",
        max_value=max([skill["tests"] for skill in skills] + [1]),
    )


def write_bar_chart(path: Path, title: str, values: list[tuple[str, float]], suffix: str, max_value: float) -> None:
    width = 1100
    row_h = 34
    left = 290
    right = 120
    top = 56
    height = top + row_h * len(values) + 35
    bar_w = width - left - right
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:13px} .title{font-size:20px;font-weight:700}.muted{fill:#64748b}.bar{fill:#2563eb}.bg{fill:#e2e8f0}</style>',
        f'<text class="title" x="24" y="32">{html.escape(title)}</text>',
    ]
    for index, (name, value) in enumerate(values):
        y = top + index * row_h
        length = 0 if max_value == 0 else bar_w * float(value) / max_value
        parts.append(f'<text x="24" y="{y + 18}">{html.escape(name)}</text>')
        parts.append(f'<rect class="bg" x="{left}" y="{y}" width="{bar_w}" height="20" rx="3"/>')
        parts.append(f'<rect class="bar" x="{left}" y="{y}" width="{length:.1f}" height="20" rx="3"/>')
        parts.append(f'<text class="muted" x="{left + bar_w + 12}" y="{y + 15}">{value:g}{html.escape(suffix)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_html_report(path: Path, payload: dict) -> None:
    summary = payload["summary"]
    rows = []
    for skill in payload["skills"]:
        issue_text = "<br>".join(html.escape(issue) for issue in skill["issues"]) or "None"
        rows.append(
            "<tr>"
            f"<td>{html.escape(skill['name'])}</td>"
            f"<td class='{skill['status']}'>{html.escape(skill['status'])}</td>"
            f"<td>{skill['passed']}/{skill['tests']}</td>"
            f"<td>{skill['coverage_percent']}%</td>"
            f"<td>{'yes' if (skill['skill_md_exists'] or skill['readme_exists']) else 'no'}</td>"
            f"<td>{issue_text}</td>"
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Workspace QA Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #0f172a; }}
    h1 {{ margin-bottom: 4px; }}
    .cards {{ display: grid; grid-template-columns: repeat(5, minmax(130px, 1fr)); gap: 12px; margin: 24px 0; }}
    .card {{ border: 1px solid #cbd5e1; border-radius: 8px; padding: 14px; }}
    .num {{ font-size: 26px; font-weight: 700; }}
    table {{ border-collapse: collapse; width: 100%; margin: 24px 0; }}
    th, td {{ border-bottom: 1px solid #e2e8f0; padding: 9px; text-align: left; vertical-align: top; }}
    th {{ background: #f8fafc; }}
    .passed {{ color: #15803d; font-weight: 700; }}
    .failed {{ color: #b91c1c; font-weight: 700; }}
    img {{ max-width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; margin: 12px 0; }}
  </style>
</head>
<body>
  <h1>Workspace QA Report</h1>
  <div>Generated at <code>{html.escape(summary['generated_at'])}</code></div>
  <div class="cards">
    <div class="card"><div>Skills</div><div class="num">{summary['skill_count']}</div></div>
    <div class="card"><div>Tests</div><div class="num">{summary['total_tests']}</div></div>
    <div class="card"><div>Passed</div><div class="num">{summary['total_passed']}</div></div>
    <div class="card"><div>Failed Skills</div><div class="num">{summary['failed_skills']}</div></div>
    <div class="card"><div>Coverage</div><div class="num">{summary['coverage_percent']}%</div></div>
  </div>
  <h2>Workspace Integration</h2>
  <p>Status: <strong>{html.escape(payload.get('workspace_tests', {}).get('status', 'unknown'))}</strong>;
  tests: {payload.get('workspace_tests', {}).get('passed', 0)}/{payload.get('workspace_tests', {}).get('tests', 0)}.</p>
  <h2>Visual Charts</h2>
  <img src="assets/coverage_by_skill.svg" alt="Coverage by Skill">
  <img src="assets/tests_by_skill.svg" alt="Tests by Skill">
  <h2>Skill Results</h2>
  <table>
    <thead><tr><th>Skill</th><th>Status</th><th>Tests</th><th>Coverage</th><th>Docs</th><th>Issues</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
