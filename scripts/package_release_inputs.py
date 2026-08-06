#!/usr/bin/env python3
"""Package the exact minimum current-release inputs into a deterministic ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import build_current_release_bundle as bundle


ARCHIVE_ROOT = "wtsocr-release-inputs"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def producer_for(logical_path: str) -> str:
    name = Path(logical_path).name
    if logical_path.startswith("tibetan_cleanup_diagnostics_"):
        if name.startswith("tibetan_final_ng_"):
            return "python3 scripts/build_tibetan_final_ng_consensus.py"
        if name == "tibetan_latin_integrity_candidates.tsv":
            return "python3 scripts/build_tibetan_latin_integrity.py"
        return "python3 scripts/build_tibetan_cleanup_diagnostics.py"
    if name.endswith("_corrected_full.txt"):
        return "scripts/postprocess_entry_map.py production pipeline; exact historical invocation unavailable"
    return "postprocess/reporting production pipeline; exact historical invocation unavailable"


def provenance_for(logical_path: str, production_revision: str) -> str:
    if logical_path.startswith("tibetan_cleanup_diagnostics_"):
        kind = "generated diagnostic input"
    elif logical_path.endswith("_corrected_full.txt"):
        kind = "trusted corrected four-volume text input"
    else:
        kind = "generated postprocess QA input"
    return f"{kind}; production workspace observed at {production_revision}"


def collect_required_files(source_root: Path) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for label in sorted(bundle.DEFAULT_SOURCES):
        source_dir = source_root / label
        if not source_dir.is_dir():
            raise FileNotFoundError(f"missing volume directory: {source_dir}")
        corrected = source_dir / f"{label}_corrected_full.txt"
        if not corrected.is_file():
            raise FileNotFoundError(f"missing corrected text: {corrected}")
        files.append((f"{label}/{corrected.name}", corrected))
        files.extend(
            (f"{label}/{path.name}", path)
            for path in sorted(source_dir.iterdir())
            if path.is_file() and bundle.is_qa_artifact(path, label)
        )

    for name in bundle.ROOT_QA_FILES:
        path = source_root / name
        if path.is_file():
            files.append((name, path))

    for label in sorted(bundle.DEFAULT_DIAGNOSTIC_SOURCES):
        dirname = f"tibetan_cleanup_diagnostics_{label}"
        source_dir = source_root / dirname
        if not source_dir.is_dir():
            raise FileNotFoundError(f"missing diagnostics directory: {source_dir}")
        files.extend(
            (f"{dirname}/{path.name}", path)
            for path in sorted(source_dir.iterdir())
            if path.is_file()
        )

    logical_paths = [logical for logical, _path in files]
    if len(logical_paths) != len(set(logical_paths)):
        raise ValueError("duplicate logical paths in release-input selection")
    return sorted(files)


def write_deterministic_zip(
    files: list[tuple[str, Path]], output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for logical_path, source in files:
            info = zipfile.ZipInfo(
                f"{ARCHIVE_ROOT}/{logical_path}", date_time=FIXED_ZIP_TIME
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(
                info,
                source.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def build_lock(
    *,
    release_id: str,
    archive_path: Path,
    asset_base_url: str,
    files: list[tuple[str, Path]],
    recipe_revision: str,
    production_revision: str,
    production_workspace: str,
    build_timestamp: str,
) -> dict[str, object]:
    file_rows = []
    for logical_path, source in files:
        data = source.read_bytes()
        file_rows.append(
            {
                "logical_path": logical_path,
                "archive_path": f"{ARCHIVE_ROOT}/{logical_path}",
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "provenance": provenance_for(logical_path, production_revision),
                "producer": producer_for(logical_path),
            }
        )
    return {
        "schema_version": 1,
        "release_id": release_id,
        "archive": {
            "filename": archive_path.name,
            "url": f"{asset_base_url.rstrip('/')}/{archive_path.name}",
            "bytes": archive_path.stat().st_size,
            "sha256": sha256_file(archive_path),
            "format": "deterministic-zip",
            "root": ARCHIVE_ROOT,
        },
        "release_build": {
            "build_timestamp": build_timestamp,
            "recipe_revision": recipe_revision,
            "production_input_revision": production_revision,
            "production_input_workspace": production_workspace,
        },
        "files": file_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--lock-output", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--asset-base-url", required=True)
    parser.add_argument("--recipe-revision", required=True)
    parser.add_argument("--production-revision", required=True)
    parser.add_argument("--production-workspace", required=True)
    parser.add_argument("--build-timestamp", required=True)
    args = parser.parse_args(argv)

    files = collect_required_files(args.source_root.resolve())
    temporary = args.output_dir / f"{args.release_id}.zip.tmp"
    write_deterministic_zip(files, temporary)
    archive_sha = sha256_file(temporary)
    archive_path = args.output_dir / f"{args.release_id}-{archive_sha}.zip"
    if archive_path.exists():
        if sha256_file(archive_path) != archive_sha:
            raise ValueError(f"existing archive has unexpected content: {archive_path}")
        temporary.unlink()
    else:
        temporary.rename(archive_path)

    lock = build_lock(
        release_id=args.release_id,
        archive_path=archive_path,
        asset_base_url=args.asset_base_url,
        files=files,
        recipe_revision=args.recipe_revision,
        production_revision=args.production_revision,
        production_workspace=args.production_workspace,
        build_timestamp=args.build_timestamp,
    )
    args.lock_output.parent.mkdir(parents=True, exist_ok=True)
    args.lock_output.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Archive: {archive_path}")
    print(f"Archive SHA-256: {archive_sha}")
    print(f"Archive bytes: {archive_path.stat().st_size}")
    print(f"Locked files: {len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
