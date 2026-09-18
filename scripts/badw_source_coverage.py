#!/usr/bin/env python3
"""Build a deterministic availability manifest for canonical BAdW source pages.

The manifest is deliberately an observation about a supplied canonical-page
snapshot.  A missing canonical page is *not* evidence that BAdW never exposed
the corresponding printed page: URL availability changes over time and is
recorded separately by the cache manifests.
"""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from badw_print_crosswalk import VOLUME_PAGE_COUNTS


CONTRACT_VERSION = "badw-canonical-source-coverage-v1"
MANIFEST_FIELDS = (
    "volume",
    "printed_page",
    "snapshot_status",
    "page_id",
    "visible_body_sha256",
    "canonical_object",
    "representative_url",
    "representative_source_sha256",
    "url_page_occurrences",
    "sequence_confidence",
    "unknown_glyph_occurrences",
    "scan_page",
    "scan_half",
    "crosswalk_confidence",
    "crosswalk_method",
)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_tsv(path: Path, fields: Iterable[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _canonical_pages(root: Path, volume: int) -> dict[int, dict[str, str]]:
    path = root / f"volume_{volume}" / "canonical_pages.tsv"
    if not path.is_file():
        raise FileNotFoundError(f"missing canonical-page table: {path}")
    pages: dict[int, dict[str, str]] = {}
    for row in _read_tsv(path):
        value = row.get("printed_page", "")
        if not value:
            continue
        page = int(value)
        if page in pages:
            raise ValueError(f"duplicate canonical page v{volume} p{page}")
        pages[page] = row
    return pages


def _crosswalk_rows(path: Path) -> dict[tuple[int, int], dict[str, str]]:
    rows: dict[tuple[int, int], dict[str, str]] = {}
    for row in _read_tsv(path):
        key = (int(row["volume"]), int(row["printed_page"]))
        if key in rows:
            raise ValueError(f"duplicate crosswalk row v{key[0]} p{key[1]}")
        rows[key] = row
    return rows


def build_source_coverage(
    canonical_root: Path,
    crosswalk_path: Path,
    output_root: Path,
    expected_counts: dict[int, int] = VOLUME_PAGE_COUNTS,
) -> dict[str, object]:
    """Write a complete printed-page availability manifest from offline inputs."""
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_root}")
    crosswalk = _crosswalk_rows(crosswalk_path)
    all_pages = {volume: _canonical_pages(canonical_root, volume) for volume in expected_counts}
    rows: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []
    volume_summary: dict[str, dict[str, int]] = {}
    for volume, expected in sorted(expected_counts.items()):
        present = 0
        for printed_page in range(1, expected + 1):
            canonical = all_pages[volume].get(printed_page)
            observed = crosswalk.get((volume, printed_page))
            if observed is None:
                raise ValueError(f"crosswalk lacks v{volume} p{printed_page}")
            if canonical is not None:
                present += 1
            status = "present_in_canonical_snapshot" if canonical else "absent_from_canonical_snapshot"
            row = {
                "volume": volume,
                "printed_page": printed_page,
                "snapshot_status": status,
                "page_id": canonical.get("page_id", "") if canonical else "",
                "visible_body_sha256": canonical.get("visible_body_sha256", "") if canonical else "",
                "canonical_object": canonical.get("canonical_object", "") if canonical else "",
                "representative_url": canonical.get("representative_url", "") if canonical else "",
                "representative_source_sha256": canonical.get("representative_source_sha256", "") if canonical else "",
                "url_page_occurrences": canonical.get("url_page_occurrences", "") if canonical else "",
                "sequence_confidence": canonical.get("sequence_confidence", "") if canonical else "",
                "unknown_glyph_occurrences": canonical.get("unknown_glyph_occurrences", "") if canonical else "",
                "scan_page": observed.get("scan_page", ""),
                "scan_half": observed.get("scan_half", ""),
                "crosswalk_confidence": observed.get("match_confidence", ""),
                "crosswalk_method": observed.get("mapping_method", ""),
            }
            rows.append(row)
            if canonical is None:
                missing.append(
                    {
                        "volume": volume,
                        "printed_page": printed_page,
                        "snapshot_status": status,
                        "scan_page": observed.get("scan_page", ""),
                        "scan_half": observed.get("scan_half", ""),
                        "crosswalk_confidence": observed.get("match_confidence", ""),
                        "crosswalk_method": observed.get("mapping_method", ""),
                    }
                )
        volume_summary[str(volume)] = {
            "expected_printed_pages": expected,
            "present_in_canonical_snapshot": present,
            "absent_from_canonical_snapshot": expected - present,
        }
    _write_tsv(output_root / "canonical_source_manifest.tsv", MANIFEST_FIELDS, rows)
    _write_tsv(
        output_root / "missing_from_canonical_snapshot.tsv",
        (
            "volume", "printed_page", "snapshot_status", "scan_page", "scan_half",
            "crosswalk_confidence", "crosswalk_method",
        ),
        missing,
    )
    manifest = output_root / "canonical_source_manifest.tsv"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "canonical_root": canonical_root.as_posix(),
        "canonical_root_tables_sha256": {
            str(volume): sha256((canonical_root / f"volume_{volume}" / "canonical_pages.tsv").read_bytes()).hexdigest()
            for volume in sorted(expected_counts)
        },
        "crosswalk_path": crosswalk_path.as_posix(),
        "crosswalk_sha256": sha256(crosswalk_path.read_bytes()).hexdigest(),
        "expected_printed_pages": sum(expected_counts.values()),
        "present_in_canonical_snapshot": sum(item["present_in_canonical_snapshot"] for item in volume_summary.values()),
        "absent_from_canonical_snapshot": len(missing),
        "volumes": volume_summary,
        "manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--crosswalk", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build_source_coverage(args.canonical_root, args.crosswalk, args.output_root), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
