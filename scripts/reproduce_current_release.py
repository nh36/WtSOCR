#!/usr/bin/env python3
"""Rebuild release/current from its locked inputs and compare every file."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import build_current_release_bundle as bundle
import materialize_release_inputs as inputs


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_trees(expected: Path, actual: Path) -> tuple[int, list[str]]:
    expected_files = {
        path.relative_to(expected).as_posix(): path
        for path in expected.rglob("*")
        if path.is_file()
    }
    actual_files = {
        path.relative_to(actual).as_posix(): path
        for path in actual.rglob("*")
        if path.is_file()
    }
    differences: list[str] = []
    for missing in sorted(set(expected_files) - set(actual_files)):
        differences.append(f"missing:{missing}")
    for extra in sorted(set(actual_files) - set(expected_files)):
        differences.append(f"unexpected:{extra}")
    for relative_path in sorted(set(expected_files) & set(actual_files)):
        expected_path = expected_files[relative_path]
        actual_path = actual_files[relative_path]
        if expected_path.stat().st_size != actual_path.stat().st_size:
            differences.append(f"size:{relative_path}")
        elif sha256_file(expected_path) != sha256_file(actual_path):
            differences.append(f"content:{relative_path}")
    return len(expected_files), differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(
            "release/inputs/wtsocr-alignment-review-2026-08-06.lock.json"
        ),
    )
    parser.add_argument("--archive", type=Path)
    parser.add_argument(
        "--cache-dir", type=Path, default=Path("work/release_input_cache")
    )
    parser.add_argument(
        "--materialized-root",
        type=Path,
        default=Path(
            "work/materialized_release_inputs/wtsocr-alignment-review-2026-08-06"
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("work/reproduced_release")
    )
    parser.add_argument(
        "--expected-dir", type=Path, default=Path("release/current")
    )
    args = parser.parse_args(argv)

    lock = inputs.load_lock(args.lock)
    archive_path = inputs.obtain_archive(
        lock, archive_path=args.archive, cache_dir=args.cache_dir
    )
    inputs.materialize(lock, archive_path, args.materialized_root)

    build = lock["release_build"]
    assert isinstance(build, dict)
    production_origin = (
        f"{build['production_input_workspace']}; observed revision "
        f"{build['production_input_revision']}"
    )
    result = bundle.main(
        [
            "--input-root",
            str(args.materialized_root),
            "--input-lock-id",
            str(lock["release_id"]),
            "--output-dir",
            str(args.output_dir),
            "--build-timestamp",
            str(build["build_timestamp"]),
            "--build-revision",
            str(build["recipe_revision"]),
            "--production-input-origin",
            production_origin,
        ]
    )
    if result:
        return result

    expected_count, differences = compare_trees(args.expected_dir, args.output_dir)
    print(f"Expected release files: {expected_count}")
    print(f"Differences: {len(differences)}")
    for difference in differences:
        print(difference)
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
