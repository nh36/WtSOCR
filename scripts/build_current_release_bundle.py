#!/usr/bin/env python3
"""Build the tracked current WtS OCR release bundle.

The production/postprocess runs live under work/, which is intentionally not
versioned. This script copies the latest trusted corrected text plus compact QA
artifacts into release/current so the repository always has a clear deployable
etext snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_SOURCES: dict[str, str] = {
    "wts_1_34": "work/final_ng_seed_clean_20260719T210000Z/wts_1_34",
    "wts_35_51": "work/final_ng_seed_clean_20260719T210000Z/wts_35_51",
    "wts_8_b": "work/final_ng_seed_clean_20260719T210000Z/wts_8_b",
    "wts_9_m": "work/final_ng_seed_clean_20260719T210000Z/wts_9_m",
}

DEFAULT_DIAGNOSTIC_SOURCES: dict[str, str] = {
    "wts_1_34": "work/final_ng_seed_clean_20260719T210000Z/tibetan_cleanup_diagnostics_wts_1_34",
    "wts_35_51": "work/final_ng_seed_clean_20260719T210000Z/tibetan_cleanup_diagnostics_wts_35_51",
    "wts_8_b": "work/final_ng_seed_clean_20260719T210000Z/tibetan_cleanup_diagnostics_wts_8_b",
    "wts_9_m": "work/final_ng_seed_clean_20260719T210000Z/tibetan_cleanup_diagnostics_wts_9_m",
}

QA_SUFFIXES = (
    "_changes.tsv",
    "_alternate_witness_adoptions.tsv",
    "_alternate_witness_unresolved.tsv",
    "_review_queue.tsv",
    "_watchdog_flags.tsv",
    "_validator_issues.tsv",
    "_sanskrit_report.tsv",
    "_citation_name_report.tsv",
    "_summary.json",
    "_line_zones.tsv",
    "_discovered_patterns.tsv",
)

ROOT_QA_FILES = (
    "checksums.sha256",
    "manual_audit_sample.tsv",
)

BUCKET_PREFIXES = (
    "bucket_report.",
    "unresolved_buckets.",
)


@dataclass(frozen=True)
class VolumeSource:
    label: str
    path: Path
    manifest_path: str | None = None


def parse_source_override(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            f"source override must be label=path, got {raw!r}"
        )
    label, path = raw.split("=", 1)
    label = label.strip()
    path = path.strip()
    if not label or not path:
        raise argparse.ArgumentTypeError(
            f"source override must be label=path, got {raw!r}"
        )
    return label, Path(path)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def resolve_build_timestamp(explicit: str | None) -> str:
    """Return a normalized UTC timestamp, honoring reproducible-build inputs."""
    if explicit:
        raw = explicit
    elif os.environ.get("SOURCE_DATE_EPOCH"):
        try:
            epoch = int(os.environ["SOURCE_DATE_EPOCH"])
        except ValueError as exc:
            raise ValueError("SOURCE_DATE_EPOCH must be an integer") from exc
        return datetime.fromtimestamp(epoch, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    else:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "build timestamp must be ISO-8601, for example 2026-07-29T16:22:11Z"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError("build timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_output_dir(root: Path, output_dir: Path) -> None:
    resolved_output = output_dir.resolve()
    resolved_root = root.resolve()
    if resolved_output == resolved_root or resolved_output == resolved_root.parent:
        raise ValueError(f"refusing to clean unsafe output directory: {output_dir}")
    if resolved_root not in resolved_output.parents:
        raise ValueError(f"output directory must be inside repo: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("text", "qa", "manifest.md", "checksums.tsv", "qa_bundle.zip"):
        target = output_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def is_qa_artifact(path: Path, label: str) -> bool:
    name = path.name
    if name == f"{label}_corrected_full.txt":
        return False
    if name == f"{label}_entry_map.jsonl":
        return False
    if any(name.endswith(suffix) for suffix in QA_SUFFIXES):
        return True
    if any(name.startswith(prefix) for prefix in BUCKET_PREFIXES):
        return True
    return False


def copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def copy_volume(
    source: VolumeSource,
    output_dir: Path,
    copied: list[Path],
    missing_optional: list[str],
) -> None:
    if not source.path.is_dir():
        raise FileNotFoundError(f"{source.label} source directory not found: {source.path}")

    corrected_src = source.path / f"{source.label}_corrected_full.txt"
    if not corrected_src.is_file():
        raise FileNotFoundError(f"missing corrected text: {corrected_src}")

    text_dest = output_dir / "text" / corrected_src.name
    copy_file(corrected_src, text_dest)
    copied.append(text_dest)

    qa_dest_dir = output_dir / "qa" / source.label
    for path in sorted(source.path.iterdir()):
        if path.is_file() and is_qa_artifact(path, source.label):
            dest = qa_dest_dir / path.name
            copy_file(path, dest)
            copied.append(dest)

    required = [
        f"{source.label}_changes.tsv",
        f"{source.label}_alternate_witness_adoptions.tsv",
        f"{source.label}_alternate_witness_unresolved.tsv",
        f"{source.label}_watchdog_flags.tsv",
        f"{source.label}_review_queue.tsv",
    ]
    for name in required:
        if not (qa_dest_dir / name).exists():
            missing_optional.append(f"{source.label}: {name}")


def validate_volume_sources(volume_sources: Iterable[VolumeSource]) -> None:
    """Fail before cleaning the tracked bundle when required inputs are absent."""
    for source in volume_sources:
        if not source.path.is_dir():
            raise FileNotFoundError(
                f"{source.label} source directory not found: {source.path}"
            )
        corrected = source.path / f"{source.label}_corrected_full.txt"
        if not corrected.is_file():
            raise FileNotFoundError(f"missing corrected text: {corrected}")


def copy_root_artifacts(
    root: Path,
    output_dir: Path,
    copied: list[Path],
    missing_optional: list[str],
    volume_sources: Iterable[VolumeSource],
) -> None:
    seen_roots: set[Path] = {source.path.parent for source in volume_sources}
    for source_root in sorted(seen_roots):
        for name in ROOT_QA_FILES:
            path = source_root / name
            if path.is_file():
                dest = output_dir / "qa" / source_root.name / name
                copy_file(path, dest)
                copied.append(dest)


def copy_diagnostics(
    diagnostics: dict[str, Path],
    output_dir: Path,
    copied: list[Path],
    missing_optional: list[str],
) -> None:
    for label, path in sorted(diagnostics.items()):
        if not path.exists():
            missing_optional.append(f"{label}: diagnostics directory {path}")
            continue
        if not path.is_dir():
            missing_optional.append(f"{label}: diagnostics path is not a directory {path}")
            continue
        dest_dir = output_dir / "qa" / label / "tibetan_cleanup_diagnostics"
        for src in sorted(path.iterdir()):
            if src.is_file():
                dest = dest_dir / src.name
                copy_file(src, dest)
                copied.append(dest)


def build_checksums(output_dir: Path) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "checksums.tsv":
            continue
        rows.append((sha256_file(path), path.stat().st_size, relative(path, output_dir)))
    return rows


def write_checksums(output_dir: Path, rows: list[tuple[str, int, str]]) -> Path:
    path = output_dir / "checksums.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("sha256\tbytes\tpath\n")
        for checksum, size, rel_path in rows:
            handle.write(f"{checksum}\t{size}\t{rel_path}\n")
    return path


def zip_qa(output_dir: Path, copied: list[Path]) -> Path:
    qa_dir = output_dir / "qa"
    zip_path = output_dir / "qa_bundle.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(qa_dir.rglob("*")):
            if path.is_file():
                archive.write(path, relative(path, output_dir))
    shutil.rmtree(qa_dir)
    copied[:] = [
        path for path in copied if not (qa_dir in path.parents or path == qa_dir)
    ]
    copied.append(zip_path)
    return zip_path


def write_manifest(
    root: Path,
    output_dir: Path,
    volume_sources: list[VolumeSource],
    diagnostics: dict[str, Path],
    copied: list[Path],
    missing_optional: list[str],
    compressed_qa: bool,
    *,
    timestamp: str,
    build_revision: str,
    production_input_origin: str,
    input_lock_id: str | None,
    diagnostic_manifest_paths: dict[str, str],
) -> Path:
    text_files = sorted((output_dir / "text").glob("*_corrected_full.txt"))
    qa_files = sorted(
        path for path in (output_dir / "qa").rglob("*") if path.is_file()
    ) if (output_dir / "qa").exists() else []

    lines = [
        "# Current WtS OCR Release Bundle",
        "",
        f"Generated UTC: `{timestamp}`",
        f"Build recipe revision: `{build_revision}`",
        f"Production input provenance: `{production_input_origin}`",
        "",
        "This directory is the tracked best-current deployable etext snapshot.",
        "`release/current/manifest.md` is an inventory and reproducibility file",
        "for this snapshot; it is not the project to-do list.",
        "The large production outputs under `work/` are local artifacts and are",
        "not versioned in the repository.",
        "The build command reports its runtime repository revision separately.",
        "The recipe revision above is pinned for deterministic reproduction and",
        "the production-input provenance identifies the workspace that produced",
        "the locked source payload. Neither value is inferred from the other.",
        "",
        "No OCR correction behavior is changed by this bundle builder. It copies",
        "the latest trusted corrected text and compact QA artifacts into",
        "`release/current`.",
        "",
        "## Source Outputs",
        "",
        "| Volume | Local source directory |",
        "| --- | --- |",
    ]
    for source in volume_sources:
        display = source.manifest_path or relative(source.path, root)
        lines.append(f"| `{source.label}` | `{display}` |")

    if diagnostics:
        lines.extend(["", "## Diagnostic Sources", "", "| Volume | Local source directory |", "| --- | --- |"])
        for label, path in sorted(diagnostics.items()):
            display = diagnostic_manifest_paths.get(label) or relative(path, root)
            lines.append(f"| `{label}` | `{display}` |")

    if input_lock_id:
        lines.extend(
            [
                "",
                "## Locked Input",
                "",
                f"- Input lock: `{input_lock_id}`",
                "- Every archived input is verified by SHA-256 before materialization.",
            ]
        )

    lines.extend(["", "## Corrected Text", ""])
    for path in text_files:
        lines.append(f"- `{relative(path, output_dir)}`")

    lines.extend(["", "## QA Artifacts", ""])
    if compressed_qa:
        lines.append("- `qa_bundle.zip` contains the copied QA TSV/JSON/Markdown artifacts.")
    elif qa_files:
        for path in qa_files:
            lines.append(f"- `{relative(path, output_dir)}`")
    else:
        lines.append("- No QA artifacts were copied.")

    lines.extend(
        [
            "",
            "## Checksums",
            "",
            "- `checksums.tsv` records SHA-256 checksums and byte sizes for every file",
            "  in this bundle except the checksum file itself.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python3 scripts/reproduce_current_release.py",
            "python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_current_release_bundle.py scripts/report_unresolved_buckets.py scripts/build_tibetan_cleanup_diagnostics.py",
            "python3 -m pytest tests/test_postprocess_regressions.py tests/test_tibetan_cleanup_diagnostics.py -q",
            "```",
            "",
            "If QA artifacts become too large to keep expanded in Git, rebuild with:",
            "",
            "```bash",
            "python3 scripts/build_current_release_bundle.py --zip-qa",
            "```",
            "",
            "## Policy Notes",
            "",
            "- Base OCR remains authoritative; Google Vision is an alternate witness.",
            "- This bundle does not loosen adoption gates or add correction heuristics.",
            "- `work/` outputs remain local and ignored; `release/current` is the",
            "  repository-level best current release snapshot.",
        ]
    )

    if missing_optional:
        lines.extend(["", "## Missing Optional Artifacts", ""])
        for item in missing_optional:
            lines.append(f"- `{item}`")

    lines.append("")
    path = output_dir / "manifest.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    copied.append(path)
    return path


def total_size(paths: Iterable[Path]) -> int:
    return sum(path.stat().st_size for path in paths if path.exists() and path.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="release/current",
        type=Path,
        help="Destination directory for the tracked release bundle.",
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        help=(
            "Materialized locked-input root containing the four volume and four "
            "diagnostic directories."
        ),
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        type=parse_source_override,
        metavar="LABEL=PATH",
        help="Override or add a volume source directory.",
    )
    parser.add_argument(
        "--diagnostics",
        action="append",
        default=[],
        type=parse_source_override,
        metavar="LABEL=PATH",
        help="Override or add a per-volume diagnostics directory.",
    )
    parser.add_argument(
        "--build-timestamp",
        help="Explicit ISO-8601 UTC build timestamp; otherwise SOURCE_DATE_EPOCH or current UTC is used.",
    )
    parser.add_argument(
        "--build-revision",
        help="Pinned build recipe revision for deterministic manifest provenance.",
    )
    parser.add_argument(
        "--production-input-origin",
        help="Immutable description of the workspace/revision that produced the inputs.",
    )
    parser.add_argument(
        "--input-lock-id",
        help="Stable identifier for the verified release-input lock.",
    )
    parser.add_argument(
        "--zip-qa",
        action="store_true",
        help="Store copied QA artifacts in release/current/qa_bundle.zip.",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    output_dir = (root / args.output_dir).resolve()

    if args.input_root and (args.source or args.diagnostics):
        parser.error("--input-root cannot be combined with --source or --diagnostics")

    timestamp = resolve_build_timestamp(args.build_timestamp)
    runtime_revision = git_commit(root)
    build_revision = args.build_revision or runtime_revision
    production_input_origin = (
        args.production_input_origin
        or f"local production workspace; build checkout {runtime_revision}"
    )

    if args.input_root:
        input_root = (
            args.input_root
            if args.input_root.is_absolute()
            else root / args.input_root
        ).resolve()
        sources = {label: input_root / label for label in DEFAULT_SOURCES}
        diagnostics = {
            label: input_root / f"tibetan_cleanup_diagnostics_{label}"
            for label in DEFAULT_DIAGNOSTIC_SOURCES
        }
    else:
        input_root = None
        sources = {label: root / path for label, path in DEFAULT_SOURCES.items()}
        diagnostics = {
            label: root / path
            for label, path in DEFAULT_DIAGNOSTIC_SOURCES.items()
        }
    for label, path in args.source:
        sources[label] = path if path.is_absolute() else root / path
    volume_sources = [
        VolumeSource(
            label,
            path,
            (
                f"locked://{args.input_lock_id}/{label}"
                if input_root and args.input_lock_id
                else None
            ),
        )
        for label, path in sorted(sources.items())
    ]

    for label, path in args.diagnostics:
        diagnostics[label] = path if path.is_absolute() else root / path
    diagnostic_manifest_paths = {
        label: f"locked://{args.input_lock_id}/tibetan_cleanup_diagnostics_{label}"
        for label in diagnostics
        if input_root and args.input_lock_id
    }

    # Required sources are intentionally preflighted before the output directory
    # is cleaned.  A fresh checkout lacks ignored work/ inputs and must fail
    # without destroying its already tracked release snapshot.
    validate_volume_sources(volume_sources)
    clean_output_dir(root, output_dir)

    copied: list[Path] = []
    missing_optional: list[str] = []
    for source in volume_sources:
        copy_volume(source, output_dir, copied, missing_optional)
    copy_root_artifacts(root, output_dir, copied, missing_optional, volume_sources)
    copy_diagnostics(diagnostics, output_dir, copied, missing_optional)

    compressed_qa = False
    if args.zip_qa:
        zip_qa(output_dir, copied)
        compressed_qa = True

    write_manifest(
        root,
        output_dir,
        volume_sources,
        diagnostics,
        copied,
        missing_optional,
        compressed_qa,
        timestamp=timestamp,
        build_revision=build_revision,
        production_input_origin=production_input_origin,
        input_lock_id=args.input_lock_id,
        diagnostic_manifest_paths=diagnostic_manifest_paths,
    )
    checksum_rows = build_checksums(output_dir)
    checksum_path = write_checksums(output_dir, checksum_rows)

    bundle_size = total_size(path for path in output_dir.rglob("*") if path.is_file())
    print(f"Wrote {relative(output_dir, root)}")
    print(f"Copied {len(copied)} files before checksums")
    print(f"Wrote {relative(checksum_path, root)}")
    print(f"Bundle size: {bundle_size} bytes")
    print(f"Runtime repository revision: {runtime_revision}")
    print(f"Build recipe revision: {build_revision}")
    if missing_optional:
        print(f"Missing optional artifacts: {len(missing_optional)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
