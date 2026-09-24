#!/usr/bin/env python3
"""Pin and verify an offline BAdW source snapshot.

This records *which* ignored BAdW cache and derived canonical-page products
were used by a later stage.  It deliberately does not copy source HTML, PDFs,
or decoded text into the repository.  A snapshot is immutable: creation
refuses to overwrite its output directory, while ``verify`` is fully offline.
"""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
from typing import Iterable


CONTRACT_VERSION = "badw-source-snapshot-v1"
QUALITY_FIELDS = (
    "issue_id", "category", "status", "volume", "printed_page", "identity",
    "occurrences", "evidence_path", "evidence_sha256", "notes",
)
CACHE_FIELDS = (
    "request_manifest_path", "request_manifest_sha256", "request_key",
    "requested_url", "final_url", "fetched_at_utc", "http_status",
    "content_classification", "delivery_type", "valid_resource", "source_sha256",
    "object_path", "object_exists", "object_sha256_matches",
)
INVENTORY_FIELDS = ("role", "path", "sha256", "byte_length")


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_tsv(path: Path, fields: Iterable[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _tsv_bytes(fields: Iterable[str], rows: Iterable[dict[str, object]]) -> bytes:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode("utf-8")


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"input must be inside repository: {path}") from exc


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    return path


def _cache_index(cache_root: Path, repo_root: Path) -> tuple[list[dict[str, object]], dict[str, int]]:
    requests = cache_root / "requests"
    if not requests.is_dir():
        raise FileNotFoundError(f"missing cache requests directory: {requests}")
    rows: list[dict[str, object]] = []
    unique_objects: set[str] = set()
    missing = mismatch = 0
    object_hashes: dict[Path, str] = {}
    for manifest_path in sorted(requests.rglob("*.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        object_path = str(manifest.get("object_path") or "")
        source_sha = str(manifest.get("sha256") or "")
        object_exists = False
        object_matches = False
        if object_path:
            object_file = cache_root / object_path
            object_exists = object_file.is_file()
            if object_exists:
                if object_file not in object_hashes:
                    object_hashes[object_file] = _sha(object_file)
                observed_hash = object_hashes[object_file]
                object_matches = bool(source_sha) and observed_hash == source_sha
                unique_objects.add(source_sha or observed_hash)
            else:
                missing += 1
        if object_exists and not object_matches:
            mismatch += 1
        rows.append({
            "request_manifest_path": _repo_relative(manifest_path, repo_root),
            "request_manifest_sha256": _sha(manifest_path),
            "request_key": manifest.get("request_key", ""),
            "requested_url": manifest.get("requested_url", ""),
            "final_url": manifest.get("final_url", ""),
            "fetched_at_utc": manifest.get("fetched_at_utc", ""),
            "http_status": manifest.get("http_status", ""),
            "content_classification": manifest.get("content_classification", ""),
            "delivery_type": manifest.get("final_delivery_type") or manifest.get("delivery_type", ""),
            "valid_resource": str(bool(manifest.get("valid_resource"))).lower(),
            "source_sha256": source_sha,
            "object_path": object_path,
            "object_exists": str(object_exists).lower(),
            "object_sha256_matches": str(object_matches).lower(),
        })
    return rows, {"request_manifests": len(rows), "unique_content_objects": len(unique_objects), "missing_objects": missing, "hash_mismatches": mismatch}


def _quality_rows(canonical_root: Path, coverage_root: Path, repo_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    missing = _require_file(coverage_root / "missing_from_canonical_snapshot.tsv", "coverage gaps")
    missing_sha = _sha(missing)
    for item in _read_tsv(missing):
        volume, page = item["volume"], item["printed_page"]
        rows.append({"issue_id": f"print-page-v{volume}-p{page}", "category": "printed_page_gap",
                     "status": item["snapshot_status"], "volume": volume, "printed_page": page,
                     "identity": "", "occurrences": "", "evidence_path": _repo_relative(missing, repo_root),
                     "evidence_sha256": missing_sha, "notes": "canonical BAdW page absent in this snapshot"})
    for volume_dir in sorted(canonical_root.glob("volume_*")):
        unknown = volume_dir / "canonical_unknown_glyphs.tsv"
        if not unknown.is_file():
            continue
        unknown_sha = _sha(unknown)
        volume = volume_dir.name.removeprefix("volume_")
        for item in _read_tsv(unknown):
            identity = ":".join(item.get(field, "") for field in ("family", "style", "cid", "glyph_signature"))
            token = sha256(identity.encode("utf-8")).hexdigest()[:16]
            rows.append({"issue_id": f"unknown-glyph-v{volume}-{token}", "category": "unresolved_glyph_identity",
                         "status": "unmapped_in_registry", "volume": volume, "printed_page": "",
                         "identity": identity, "occurrences": item.get("canonical_page_occurrences", ""),
                         "evidence_path": _repo_relative(unknown, repo_root), "evidence_sha256": unknown_sha,
                         "notes": "explicit unknown preserved by BAdW PDF decoder"})
    return sorted(rows, key=lambda row: str(row["issue_id"]))


def _inventory(inputs: list[tuple[str, Path]], repo_root: Path) -> list[dict[str, object]]:
    return [{"role": role, "path": _repo_relative(path, repo_root), "sha256": _sha(path), "byte_length": path.stat().st_size}
            for role, path in sorted(inputs, key=lambda item: (item[0], item[1].as_posix()))]


def create_snapshot(snapshot_id: str, observed_at_utc: str, canonical_root: Path, crosswalk: Path,
                    coverage_root: Path, glyph_registry: Path, cache_root: Path, output_root: Path,
                    repo_root: Path | None = None) -> dict[str, object]:
    """Create an immutable source snapshot entirely from existing offline files."""
    repo_root = repo_root or Path(__file__).resolve().parents[1]
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite snapshot output: {output_root}")
    tables = [_require_file(canonical_root / f"volume_{volume}" / "canonical_pages.tsv", "canonical page table") for volume in (2, 3, 4)]
    unknowns = [_require_file(canonical_root / f"volume_{volume}" / "canonical_unknown_glyphs.tsv", "canonical unknown-glyph table") for volume in (2, 3, 4)]
    inputs = [("canonical_pages", path) for path in tables] + [("canonical_unknown_glyphs", path) for path in unknowns]
    inputs += [("print_crosswalk", _require_file(crosswalk, "print crosswalk")),
               ("coverage_summary", _require_file(coverage_root / "summary.json", "coverage summary")),
               ("coverage_manifest", _require_file(coverage_root / "canonical_source_manifest.tsv", "coverage manifest")),
               ("coverage_gaps", _require_file(coverage_root / "missing_from_canonical_snapshot.tsv", "coverage gaps")),
               ("glyph_registry", _require_file(glyph_registry, "glyph registry"))]
    cache_rows, cache_summary = _cache_index(cache_root, repo_root)
    if cache_summary["missing_objects"] or cache_summary["hash_mismatches"]:
        raise ValueError(f"cache integrity failure: {cache_summary}")
    output_root.mkdir(parents=True)
    _write_tsv(output_root / "input_inventory.tsv", INVENTORY_FIELDS, _inventory(inputs, repo_root))
    _write_tsv(output_root / "cache_manifest_index.tsv", CACHE_FIELDS, cache_rows)
    _write_tsv(output_root / "source_quality_inventory.tsv", QUALITY_FIELDS, _quality_rows(canonical_root, coverage_root, repo_root))
    summary = {
        "contract_version": CONTRACT_VERSION, "snapshot_id": snapshot_id, "observed_at_utc": observed_at_utc,
        "inputs": {role: [{"path": _repo_relative(path, repo_root), "sha256": _sha(path), "byte_length": path.stat().st_size}
                          for current_role, path in inputs if current_role == role] for role in sorted({role for role, _ in inputs})},
        "cache_root": _repo_relative(cache_root, repo_root), "cache": cache_summary,
        "input_inventory_sha256": _sha(output_root / "input_inventory.tsv"),
        "cache_manifest_index_sha256": _sha(output_root / "cache_manifest_index.tsv"),
        "source_quality_inventory_sha256": _sha(output_root / "source_quality_inventory.tsv"),
    }
    (output_root / "source_snapshot.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def verify_snapshot(snapshot_root: Path, repo_root: Path | None = None) -> dict[str, object]:
    """Verify a snapshot's designated inputs and raw cache without networking."""
    repo_root = repo_root or Path(__file__).resolve().parents[1]
    summary_path = _require_file(snapshot_root / "source_snapshot.json", "source snapshot")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"unsupported snapshot contract: {summary.get('contract_version')}")
    for role, items in summary["inputs"].items():
        for item in items:
            path = repo_root / item["path"]
            if not path.is_file() or _sha(path) != item["sha256"] or path.stat().st_size != item["byte_length"]:
                raise ValueError(f"input changed or missing ({role}): {item['path']}")
    for name in ("input_inventory", "cache_manifest_index", "source_quality_inventory"):
        if _sha(snapshot_root / f"{name}.tsv") != summary[f"{name}_sha256"]:
            raise ValueError(f"snapshot artifact changed: {name}")
    cache_rows, cache_summary = _cache_index(repo_root / summary["cache_root"], repo_root)
    if cache_summary != summary["cache"]:
        raise ValueError(f"cache changed or integrity failed: {cache_summary}")
    if _tsv_bytes(CACHE_FIELDS, cache_rows) != (snapshot_root / "cache_manifest_index.tsv").read_bytes():
        raise ValueError("cache manifest observations changed")
    return {"contract_version": CONTRACT_VERSION, "snapshot_id": summary["snapshot_id"], "verified": True, "cache": cache_summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--snapshot-id", required=True)
    create.add_argument("--observed-at-utc", required=True)
    create.add_argument("--canonical-root", required=True, type=Path)
    create.add_argument("--crosswalk", required=True, type=Path)
    create.add_argument("--coverage-root", required=True, type=Path)
    create.add_argument("--glyph-registry", required=True, type=Path)
    create.add_argument("--cache-root", required=True, type=Path)
    create.add_argument("--output-root", required=True, type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("--snapshot-root", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "create":
        result = create_snapshot(args.snapshot_id, args.observed_at_utc, args.canonical_root, args.crosswalk,
                                 args.coverage_root, args.glyph_registry, args.cache_root, args.output_root)
    else:
        result = verify_snapshot(args.snapshot_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
