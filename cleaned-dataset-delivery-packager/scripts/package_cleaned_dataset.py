#!/usr/bin/env python3
"""Package cleaned datasets and delivery artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_DIRS = ("data", "reports", "logs", "metadata", "docs", "extras")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_artifact(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if any(token in name for token in ("metadata", "catalog", "schema", "license", "authorization")):
        return "metadata"
    if "log" in name:
        return "logs"
    if suffix in {".md", ".txt"} or any(token in name for token in ("readme", "doc", "说明")):
        return "docs"
    if any(token in name for token in ("report", "summary", "issue", "diff", "quality", "validation")):
        return "reports"
    return "extras"


def copy_unique(source: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if not target.exists():
        shutil.copy2(source, target)
        return target

    stem = source.stem
    suffix = source.suffix
    index = 2
    while True:
        candidate = target_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            shutil.copy2(source, candidate)
            return candidate
        index += 1


def file_record(path: Path, role: str, package_root: Path, source_path: Path | None = None) -> dict:
    return {
        "path": path.relative_to(package_root).as_posix(),
        "role": role,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "source_path": str(source_path) if source_path else "",
    }


def package_dataset(
    cleaned_data_path: str | Path,
    output_dir: str | Path,
    artifacts: list[str | Path] | None = None,
    dataset_name: str | None = None,
) -> dict:
    cleaned_data = Path(cleaned_data_path).expanduser().resolve()
    if not cleaned_data.exists():
        raise FileNotFoundError(f"cleaned data file not found: {cleaned_data}")
    if not cleaned_data.is_file():
        raise ValueError(f"cleaned data path is not a file: {cleaned_data}")

    output = Path(output_dir).expanduser().resolve()
    package_root = output / "package"
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True, exist_ok=True)
    for dirname in PACKAGE_DIRS:
        (package_root / dirname).mkdir(exist_ok=True)

    files: list[dict] = []
    copied_data = copy_unique(cleaned_data, package_root / "data")
    files.append(file_record(copied_data, "data", package_root, cleaned_data))

    for artifact in artifacts or []:
        artifact_path = Path(artifact).expanduser().resolve()
        if not artifact_path.exists():
            raise FileNotFoundError(f"artifact file not found: {artifact_path}")
        if not artifact_path.is_file():
            raise ValueError(f"artifact path is not a file: {artifact_path}")
        role = classify_artifact(artifact_path)
        copied = copy_unique(artifact_path, package_root / role)
        files.append(file_record(copied, role, package_root, artifact_path))

    manifest = {
        "dataset_name": dataset_name or cleaned_data.stem,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package_layout": list(PACKAGE_DIRS),
        "file_count": len(files),
        "files": files,
    }

    manifest_path = package_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    checksums_path = package_root / "checksums.csv"
    with checksums_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "role", "size_bytes", "sha256"])
        writer.writeheader()
        for record in files:
            writer.writerow({key: record[key] for key in ("path", "role", "size_bytes", "sha256")})

    archive_base = output / "delivery_package"
    archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=package_root))

    return {
        "package_dir": str(package_root),
        "manifest_path": str(manifest_path),
        "checksums_path": str(checksums_path),
        "archive_path": str(archive_path),
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Package a cleaned dataset for delivery.")
    parser.add_argument("cleaned_data")
    parser.add_argument("output_dir")
    parser.add_argument("--artifact", action="append", default=[], help="Additional delivery artifact file.")
    parser.add_argument("--dataset-name")
    args = parser.parse_args()

    result = package_dataset(args.cleaned_data, args.output_dir, args.artifact, args.dataset_name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
