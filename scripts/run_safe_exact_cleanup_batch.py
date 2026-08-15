#!/usr/bin/env python3
"""Run a bounded exact OCR cleanup batch end to end."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import exact_promotion_batch as batch


VOLUME_ORDER = ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m")
DEFAULT_WORK_ROOT = Path("work/final_ng_seed_clean_20260719T210000Z")
MANIFEST_PATH = Path("data/exact_promotion_batch_manifest.tsv")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def relpath(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def run_checked(
    command: list[str],
    *,
    root: Path,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("+ " + shlex.join(command))
    result = subprocess.run(
        command,
        cwd=root,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
        check=False,
    )
    if capture:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout if capture else None,
            stderr=result.stderr if capture else None,
        )
    return result


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, ["git", *args], result.stdout, result.stderr)
    return result.stdout


def print_git_status(root: Path) -> None:
    print("+ git status --short")
    status = git_output(root, "status", "--short")
    if status:
        print(status, end="")


def ensure_clean_worktree(root: Path) -> None:
    status = git_output(root, "status", "--porcelain")
    if status.strip():
        raise SystemExit("Refusing to run apply batch with a dirty worktree:\n" + status)


def parse_key(output: str, key: str) -> str:
    prefix = f"{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return ""


def validation_commands() -> list[list[str]]:
    return [
        [sys.executable, "scripts/check_repo_hygiene.py"],
        [sys.executable, "scripts/build_status.py", "--check"],
        [sys.executable, "-m", "py_compile", "scripts/build_status.py"],
        [
            sys.executable,
            "-m",
            "py_compile",
            "scripts/postprocess_entry_map.py",
            "scripts/build_current_release_bundle.py",
            "scripts/report_unresolved_buckets.py",
            "scripts/build_tibetan_cleanup_diagnostics.py",
        ],
        [
            sys.executable,
            "-m",
            "py_compile",
            "scripts/exact_promotion_batch.py",
            "scripts/promote_reference_marker_candidates.py",
            "scripts/run_safe_exact_cleanup_batch.py",
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_postprocess_regressions.py",
            "tests/test_tibetan_cleanup_diagnostics.py",
            "tests/test_exact_promotion_batch.py",
            "-q",
        ],
    ]


def run_reference_marker(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if args.apply:
        ensure_clean_worktree(root)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_id = args.batch_id or f"reference_marker_{timestamp}"
    work_dir = args.work_dir or root / "work" / "safe_exact_batches" / batch_id
    packet_path = work_dir / "selected_exact_overrides.tsv"
    dry_run_dir = work_dir / "dry_run"
    apply_dir = work_dir / "apply"
    source_revision = batch.git_revision(root)

    dry_run = run_checked(
        [
            sys.executable,
            "scripts/promote_reference_marker_candidates.py",
            "--dry-run",
            "--direction-from-lemma-order",
            "--tier",
            "A",
            "--limit",
            str(args.limit),
            "--min-score",
            str(args.min_score),
            "--max-per-volume",
            str(args.max_per_volume),
            "--batch-id",
            batch_id,
            "--work-dir",
            str(dry_run_dir),
            "--write-packet",
            str(packet_path),
        ],
        root=root,
        capture=True,
    )
    packet_rows = batch.load_packet(packet_path)
    selected_count = len(packet_rows)
    print(f"packet_rows={selected_count}")
    if selected_count == 0:
        print("No rows selected; nothing to apply.")
        return 0
    if not args.apply:
        return 0

    apply_result = run_checked(
        [
            sys.executable,
            "scripts/promote_reference_marker_candidates.py",
            "--apply",
            "--direction-from-lemma-order",
            "--tier",
            "A",
            "--limit",
            str(args.limit),
            "--min-score",
            str(args.min_score),
            "--max-per-volume",
            str(args.max_per_volume),
            "--batch-id",
            batch_id,
            "--work-dir",
            str(apply_dir),
            "--apply-packet",
            str(packet_path),
        ],
        root=root,
        capture=True,
    )
    applied_count = parse_key(apply_result.stdout, "applied") or "0"
    volumes = batch.affected_volumes(packet_rows, VOLUME_ORDER)
    incremental = [
        sys.executable,
        "scripts/apply_incremental_reviewed_exact_overrides.py",
        "--work-root",
        str(args.work_root),
    ]
    for volume in volumes:
        incremental.extend(["--volume", volume])
    run_checked(incremental, root=root)
    run_checked([sys.executable, "scripts/build_current_release_bundle.py"], root=root)
    run_checked([sys.executable, "scripts/build_status.py"], root=root)

    source_diagnostics = sorted({row.get("source_diagnostic", "") for row in packet_rows if row.get("source_diagnostic", "")})
    batch.append_manifest_row(
        root / MANIFEST_PATH,
        {
            "batch_id": batch_id,
            "family_id": "reference_marker",
            "status": "applied",
            "source_release_revision": source_revision,
            "source_diagnostic": ";".join(source_diagnostics),
            "selection_rule": (
                "tier=A;sort=score_desc_volume_page_line_token;"
                "direction=lemma_order;exact_unique_source=true"
            ),
            "min_score": str(args.min_score),
            "row_limit": str(args.limit),
            "max_per_volume": str(args.max_per_volume),
            "selected_count": str(selected_count),
            "applied_count": applied_count,
            "affected_volumes": ";".join(volumes),
            "notes": f"packet={relpath(root, packet_path)}",
        },
    )

    for command in validation_commands():
        run_checked(command, root=root)

    if args.no_commit:
        print_git_status(root)
        return 0

    status_before_commit = git_output(root, "status", "--porcelain")
    if not status_before_commit.strip():
        print("No tracked changes to commit.")
        print_git_status(root)
        return 0
    run_checked(
        [
            "git",
            "add",
            "data/reviewed_tibetan_exact_overrides.tsv",
            str(MANIFEST_PATH),
            "data/correction_families.tsv",
            "docs/STATUS.md",
            "release/current",
        ],
        root=root,
    )
    run_checked(
        ["git", "commit", "-m", f"Promote reference-marker exact batch {batch_id}"],
        root=root,
    )
    if args.push:
        run_checked(["git", "push"], root=root)
    print_git_status(root)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=["reference_marker"], required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-per-volume", type=int, default=20)
    parser.add_argument("--min-score", type=int, default=100)
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument("--root", type=Path, default=repo_root())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--no-commit", action="store_true")
    args = parser.parse_args()

    if args.family == "reference_marker":
        return run_reference_marker(args)
    raise ValueError(f"Unsupported family: {args.family}")


if __name__ == "__main__":
    raise SystemExit(main())
