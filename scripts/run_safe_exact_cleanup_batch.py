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


def git_status_path(line: str) -> str:
    path = line[3:]
    if " -> " in path:
        path = path.rsplit(" -> ", 1)[1]
    return path


def ensure_clean_worktree(root: Path, *, allowed_dirty: set[str] | None = None) -> None:
    allowed_dirty = allowed_dirty or set()
    status = git_output(root, "status", "--porcelain")
    blocked = [
        line
        for line in status.splitlines()
        if git_status_path(line) not in allowed_dirty
    ]
    if blocked:
        raise SystemExit("Refusing to run apply batch with a dirty worktree:\n" + "\n".join(blocked) + "\n")


def parse_key(output: str, key: str) -> str:
    prefix = f"{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return ""


def validation_commands() -> list[list[str]]:
    return [
        [sys.executable, "scripts/check_repo_hygiene.py"],
        [sys.executable, "scripts/check_reference_marker_source_reviews.py"],
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
            "scripts/reference_marker_source_review.py",
            "scripts/build_reference_marker_source_review_packet.py",
            "scripts/check_reference_marker_source_reviews.py",
            "scripts/import_reference_marker_source_reviews.py",
            "scripts/run_safe_exact_cleanup_batch.py",
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_postprocess_regressions.py",
            "tests/test_tibetan_cleanup_diagnostics.py",
            "tests/test_exact_promotion_batch.py",
            "tests/test_reference_marker_investigator.py",
            "tests/test_reference_marker_source_review.py",
            "-q",
        ],
    ]


def build_source_review_packet(args: argparse.Namespace, root: Path, investigation_path: Path, review_packet_path: Path, batch_id: str, work_dir: Path) -> None:
    command = [
        sys.executable,
        "scripts/build_reference_marker_source_review_packet.py",
        "--investigation-packet",
        str(investigation_path),
        "--review-packet",
        str(review_packet_path),
        "--batch-id",
        batch_id,
        "--work-dir",
        str(work_dir / "source_review"),
        "--limit",
        str(args.source_review_limit),
        "--max-per-volume",
        str(args.source_review_max_per_volume),
    ]
    if args.render_source_crops:
        command.append("--render-crops")
    run_checked(command, root=root, capture=True)


def apply_source_reviewed_reference_marker(
    args: argparse.Namespace,
    root: Path,
    *,
    batch_id: str,
    work_dir: Path,
    source_revision: str,
) -> int:
    ledger = args.source_review_ledger
    ledger = ledger if ledger.is_absolute() else root / ledger
    packet_path = work_dir / "selected_source_reviewed_exact_overrides.tsv"
    apply_dir = work_dir / "apply_source_reviewed"
    import_result = run_checked(
        [
            sys.executable,
            "scripts/import_reference_marker_source_reviews.py",
            "--ledger",
            str(ledger),
            "--write-packet",
            str(packet_path),
            "--batch-id",
            batch_id,
            "--limit",
            str(args.source_review_limit),
            "--max-per-volume",
            str(args.source_review_max_per_volume),
        ],
        root=root,
        capture=True,
    )
    selected_count = parse_key(import_result.stdout, "source_review_accepted_rows") or "0"
    packet_rows = batch.load_packet(packet_path)
    print(f"source_review_packet_rows={len(packet_rows)}")

    applied_count = "0"
    volumes: list[str] = []
    if packet_rows:
        apply_result = run_checked(
            [
                sys.executable,
                "scripts/promote_reference_marker_candidates.py",
                "--apply",
                "--direction-from-lemma-order",
                "--tier",
                "A",
                "--limit",
                str(args.source_review_limit),
                "--min-score",
                "100",
                "--max-per-volume",
                str(args.source_review_max_per_volume),
                "--batch-id",
                batch_id,
                "--work-dir",
                str(apply_dir),
                "--apply-packet",
                str(packet_path),
                "--investigation-min-score",
                str(args.investigation_min_score),
            ],
            root=root,
            capture=True,
        )
        applied_count = parse_key(apply_result.stdout, "applied") or "0"
        if int(applied_count):
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

            source_diagnostics = sorted(
                {row.get("source_diagnostic", "") for row in packet_rows if row.get("source_diagnostic", "")}
            )
            batch.append_manifest_row(
                root / MANIFEST_PATH,
                {
                    "batch_id": batch_id,
                    "family_id": "reference_marker",
                    "status": "applied",
                    "source_release_revision": source_revision,
                    "source_diagnostic": ";".join(source_diagnostics),
                    "selection_rule": (
                        "source_image_review;exact_unique_source=true;"
                        "accepted_decision=accept_exact;no_broad_marker_rule"
                    ),
                    "min_score": "100",
                    "row_limit": str(args.source_review_limit),
                    "max_per_volume": str(args.source_review_max_per_volume),
                    "selected_count": selected_count,
                    "applied_count": applied_count,
                    "affected_volumes": ";".join(volumes),
                    "notes": (
                        f"packet={relpath(root, packet_path)};"
                        f"ledger={relpath(root, ledger)}"
                    ),
                },
            )
    else:
        print("No accepted source-image review rows to apply.")

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

    paths_to_add = [
        "data/reference_marker_source_image_reviews.tsv",
        "data/reviewed_tibetan_exact_overrides.tsv",
        str(MANIFEST_PATH),
        "data/correction_families.tsv",
        "docs/STATUS.md",
    ]
    if int(applied_count):
        paths_to_add.append("release/current")
    run_checked(["git", "add", *paths_to_add], root=root)
    message = (
        f"Promote source-reviewed reference-marker batch {batch_id}"
        if int(applied_count)
        else f"Record source-reviewed reference-marker ledger {batch_id}"
    )
    run_checked(["git", "commit", "-m", message], root=root)
    if args.push:
        run_checked(["git", "push"], root=root)
    print_git_status(root)
    return 0


def run_reference_marker(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    source_review_ledger = args.source_review_ledger
    source_review_ledger = source_review_ledger if source_review_ledger.is_absolute() else root / source_review_ledger
    if args.apply_source_reviewed:
        ensure_clean_worktree(root, allowed_dirty={relpath(root, source_review_ledger)})
    elif args.apply:
        ensure_clean_worktree(root)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_id = args.batch_id or f"reference_marker_{timestamp}"
    work_dir = args.work_dir or root / "work" / "safe_exact_batches" / batch_id
    packet_path = work_dir / "selected_exact_overrides.tsv"
    investigation_path = work_dir / "deferred_reference_marker_investigation.tsv"
    source_review_packet_path = work_dir / "reference_marker_source_review_packet.tsv"
    dry_run_dir = work_dir / "dry_run"
    apply_dir = work_dir / "apply"
    source_revision = batch.git_revision(root)

    if args.apply_source_reviewed:
        return apply_source_reviewed_reference_marker(
            args,
            root,
            batch_id=batch_id,
            work_dir=work_dir,
            source_revision=source_revision,
        )

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
            "--write-investigation-packet",
            str(investigation_path),
            "--investigation-limit",
            str(args.investigation_limit),
            "--investigation-min-score",
            str(args.investigation_min_score),
            "--include-investigation-promotions",
        ],
        root=root,
        capture=True,
    )
    packet_rows = batch.load_packet(packet_path)
    selected_count = len(packet_rows)
    investigation_rows = batch.read_tsv(investigation_path) if investigation_path.exists() else []
    investigation_counts = {
        key: sum(1 for row in investigation_rows if row.get("decision") == key)
        for key in ("promote_exact", "reject_not_marker", "needs_source_image")
    }
    print(f"packet_rows={selected_count}")
    print(
        "investigation="
        f"promote_exact:{investigation_counts['promote_exact']},"
        f"reject_not_marker:{investigation_counts['reject_not_marker']},"
        f"needs_source_image:{investigation_counts['needs_source_image']}"
    )
    if selected_count == 0:
        if args.source_review_packet and investigation_counts["needs_source_image"]:
            build_source_review_packet(
                args,
                root,
                investigation_path,
                source_review_packet_path,
                batch_id,
                work_dir,
            )
        print("No rows selected; no concrete promote_exact proof rows to apply.")
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
            "--investigation-min-score",
            str(args.investigation_min_score),
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
                "direction=lemma_order;exact_unique_source=true;"
                "fallback=bounded_deferred_text_investigation"
            ),
            "min_score": str(args.min_score),
            "row_limit": str(args.limit),
            "max_per_volume": str(args.max_per_volume),
            "selected_count": str(selected_count),
            "applied_count": applied_count,
            "affected_volumes": ";".join(volumes),
            "notes": (
                f"packet={relpath(root, packet_path)};"
                f"investigation={relpath(root, investigation_path)}"
            ),
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
    parser.add_argument("--investigation-limit", type=int, default=25)
    parser.add_argument("--investigation-min-score", type=int, default=70)
    parser.add_argument("--source-review-packet", action="store_true")
    parser.add_argument("--render-source-crops", action="store_true")
    parser.add_argument("--source-review-limit", type=int, default=25)
    parser.add_argument("--source-review-max-per-volume", type=int, default=15)
    parser.add_argument(
        "--source-review-ledger",
        type=Path,
        default=Path("data/reference_marker_source_image_reviews.tsv"),
    )
    parser.add_argument("--apply-source-reviewed", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--no-commit", action="store_true")
    args = parser.parse_args()

    if args.apply and args.apply_source_reviewed:
        parser.error("--apply and --apply-source-reviewed are separate modes")
    if args.render_source_crops and not args.source_review_packet:
        parser.error("--render-source-crops requires --source-review-packet")

    if args.family == "reference_marker":
        return run_reference_marker(args)
    raise ValueError(f"Unsupported family: {args.family}")


if __name__ == "__main__":
    raise SystemExit(main())
