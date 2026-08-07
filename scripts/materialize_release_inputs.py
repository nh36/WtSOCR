#!/usr/bin/env python3
"""Obtain, verify, and materialize an immutable WtSOCR release-input lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


REQUIRED_FILE_FIELDS = {
    "logical_path",
    "archive_path",
    "bytes",
    "sha256",
    "provenance",
    "producer",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(raw: str) -> Path:
    posix = PurePosixPath(raw)
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise ValueError(f"unsafe archive or logical path: {raw!r}")
    return Path(*posix.parts)


def load_lock(path: Path) -> dict[str, object]:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1:
        raise ValueError("unsupported release-input lock schema")
    archive = lock.get("archive")
    files = lock.get("files")
    build = lock.get("release_build")
    if not isinstance(archive, dict) or not isinstance(files, list):
        raise ValueError("release-input lock must define archive and files")
    if not isinstance(build, dict):
        raise ValueError("release-input lock must define release_build")
    for field in ("filename", "url", "bytes", "sha256", "format", "root"):
        if field not in archive:
            raise ValueError(f"release-input archive metadata missing {field}")
    if archive["format"] != "deterministic-zip":
        raise ValueError("unsupported release-input archive format")
    seen_logical: set[str] = set()
    seen_archive: set[str] = set()
    for row in files:
        if not isinstance(row, dict) or not REQUIRED_FILE_FIELDS.issubset(row):
            raise ValueError("release-input file row has missing fields")
        logical = str(row["logical_path"])
        archived = str(row["archive_path"])
        safe_relative_path(logical)
        safe_relative_path(archived)
        if logical in seen_logical or archived in seen_archive:
            raise ValueError("duplicate logical or archive path in release-input lock")
        seen_logical.add(logical)
        seen_archive.add(archived)
    if not files:
        raise ValueError("release-input lock contains no files")
    return lock


def verify_archive(path: Path, archive: dict[str, object]) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"release-input archive not found: {path}")
    expected_size = int(archive["bytes"])
    if path.stat().st_size != expected_size:
        raise ValueError(
            f"archive size mismatch: expected {expected_size}, got {path.stat().st_size}"
        )
    actual_sha = sha256_file(path)
    if actual_sha != archive["sha256"]:
        raise ValueError(
            f"archive SHA-256 mismatch: expected {archive['sha256']}, got {actual_sha}"
        )


def obtain_archive(
    lock: dict[str, object], *, archive_path: Path | None, cache_dir: Path
) -> Path:
    archive = lock["archive"]
    assert isinstance(archive, dict)
    if archive_path is not None:
        selected = archive_path.resolve()
        verify_archive(selected, archive)
        return selected

    cache_dir.mkdir(parents=True, exist_ok=True)
    selected = cache_dir / str(archive["filename"])
    if selected.exists():
        verify_archive(selected, archive)
        return selected

    temporary = selected.with_suffix(selected.suffix + ".part")
    if temporary.exists():
        temporary.unlink()
    request = urllib.request.Request(
        str(archive["url"]), headers={"User-Agent": "WtSOCR-release-reproducer/1"}
    )
    try:
        with urllib.request.urlopen(request) as response, temporary.open("wb") as out:
            shutil.copyfileobj(response, out)
        verify_archive(temporary, archive)
        temporary.rename(selected)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return selected


def materialize(
    lock: dict[str, object], archive_path: Path, output_root: Path
) -> None:
    files = lock["files"]
    archive_meta = lock["archive"]
    assert isinstance(files, list) and isinstance(archive_meta, dict)
    expected_members = {str(row["archive_path"]): row for row in files}

    output_root = output_root.resolve()
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=output_root.parent)
    )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("release-input archive contains duplicate members")
            actual_members = {name for name in names if not name.endswith("/")}
            expected_names = set(expected_members)
            missing = sorted(expected_names - actual_members)
            extra = sorted(actual_members - expected_names)
            if missing or extra:
                raise ValueError(
                    f"archive member mismatch: missing={missing!r} extra={extra!r}"
                )
            for member in sorted(expected_names):
                row = expected_members[member]
                data = archive.read(member)
                if len(data) != int(row["bytes"]):
                    raise ValueError(f"input size mismatch for {member}")
                actual_sha = hashlib.sha256(data).hexdigest()
                if actual_sha != row["sha256"]:
                    raise ValueError(f"input SHA-256 mismatch for {member}")
                destination = staging / safe_relative_path(str(row["logical_path"]))
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)

        actual_files = {
            path.relative_to(staging).as_posix()
            for path in staging.rglob("*")
            if path.is_file()
        }
        expected_files = {str(row["logical_path"]) for row in files}
        if actual_files != expected_files:
            raise ValueError("materialized input tree does not match the lock")
        if output_root.exists():
            if output_root.is_dir():
                shutil.rmtree(output_root)
            else:
                output_root.unlink()
        staging.rename(output_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


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
        "--output-root",
        type=Path,
        default=Path(
            "work/materialized_release_inputs/wtsocr-alignment-review-2026-08-06"
        ),
    )
    args = parser.parse_args(argv)

    lock = load_lock(args.lock)
    archive_path = obtain_archive(
        lock, archive_path=args.archive, cache_dir=args.cache_dir
    )
    materialize(lock, archive_path, args.output_root)
    print(f"Verified archive: {archive_path}")
    print(f"Materialized {len(lock['files'])} locked files at {args.output_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
