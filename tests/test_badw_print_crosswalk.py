from __future__ import annotations

import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from badw_print_crosswalk import build_crosswalk, missing_ranges  # noqa: E402


def _canonical_page(root: Path, volume: int, page: int, text: str) -> None:
    volume_root = root / f"volume_{volume}"
    pages = volume_root / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    object_name = f"pages/p{page}.json.gz"
    with gzip.open(volume_root / object_name, "wt", encoding="utf-8") as handle:
        json.dump({"source_faithful_decoded_text": text}, handle, sort_keys=True)
    table = volume_root / "canonical_pages.tsv"
    existing = []
    if table.exists():
        with table.open(encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle, delimiter="\t"))
    existing.append(
        {"printed_page": page, "page_id": f"v{volume}-p{page}", "canonical_object": object_name}
    )
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("printed_page", "page_id", "canonical_object"),
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(sorted(existing, key=lambda row: int(row["printed_page"])))


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_missing_ranges_groups_consecutive_pages():
    assert missing_ranges([7, 2, 3, 8, 10]) == [(2, 3), (7, 8), (10, 10)]


def test_crosswalk_matches_pages_and_maps_missing_shared_half(tmp_path):
    canonical = tmp_path / "canonical"
    _canonical_page(canonical, 2, 1, "alphaunique betaword gammaword deltaword")
    _canonical_page(canonical, 2, 3, "epsilonunique zetaword etaword thetaword")
    scan = tmp_path / "scan.txt"
    scan.write_text(
        "front matter\falphaunique betaword gammaword deltaword\f"
        "epsilonunique zetaword etaword thetaword",
        encoding="utf-8",
    )

    first = tmp_path / "first"
    second = tmp_path / "second"
    summary = build_crosswalk(canonical, scan, first, {2: 3})
    build_crosswalk(canonical, scan, second, {2: 3})
    assert summary["canonical_pages_present"] == 2
    assert summary["canonical_pages_missing"] == 1
    with (first / "print_page_crosswalk.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    page_two = rows[1]
    assert page_two["canonical_status"] == "missing"
    assert page_two["scan_page"] == rows[2]["scan_page"]
    assert page_two["mapping_method"] == "paired_with_printed_page:3"
    with (first / "scan_page_occupancy.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        occupancy = list(csv.DictReader(handle, delimiter="\t"))
    assert occupancy[0]["occupancy"] == "right_dictionary_only"
    assert _tree_hashes(first) == _tree_hashes(second)

    with pytest.raises(FileExistsError, match="existing data"):
        build_crosswalk(canonical, scan, first, {2: 3})


def test_crosswalk_uses_two_up_sequence_only_when_uniquely_bounded(tmp_path):
    canonical = tmp_path / "canonical"
    scan_pages = [
        "front matter",
        "previousunique alphaone betatwo gammathree",
        "middle page with unreadable OCR",
        "followingunique deltaone epsilontwo zetathree",
    ]
    _canonical_page(canonical, 2, 1, scan_pages[1])
    _canonical_page(canonical, 2, 2, "unmatched left")
    _canonical_page(canonical, 2, 3, "unmatched right")
    _canonical_page(canonical, 2, 4, scan_pages[3])
    scan = tmp_path / "scan.txt"
    scan.write_text("\f".join(scan_pages), encoding="utf-8")

    output = tmp_path / "output"
    build_crosswalk(canonical, scan, output, {2: 4})
    with (output / "print_page_crosswalk.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[1]["scan_page"] == "3"
    assert rows[2]["scan_page"] == "3"
    assert rows[1]["match_confidence"] == "high_sequence_inference"
    assert rows[2]["mapping_method"] == "bounded_by_printed_pages:1,4"


def test_crosswalk_maps_missing_first_page_from_agreeing_next_halves(tmp_path):
    canonical = tmp_path / "canonical"
    shared_scan = "secondunique alphaone betatwo gammathree fourthword"
    _canonical_page(canonical, 3, 2, shared_scan)
    _canonical_page(canonical, 3, 3, shared_scan)
    scan = tmp_path / "scan.txt"
    scan.write_text(
        "front matter\fmissing first printed page\f" + shared_scan,
        encoding="utf-8",
    )

    output = tmp_path / "output"
    build_crosswalk(canonical, scan, output, {3: 3})
    with (output / "print_page_crosswalk.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[0]["scan_page"] == "2"
    assert rows[0]["match_confidence"] == "high_adjacent_volume_boundary"
    assert rows[0]["mapping_method"] == "preceding_scan_from_printed_pages:2,3"


def test_crosswalk_distinguishes_duplicate_scan_from_weak_match(tmp_path):
    canonical = tmp_path / "canonical"
    text = "alphaunique betaword gammaword deltaword epsilonword"
    _canonical_page(canonical, 2, 1, text)
    scan = tmp_path / "scan.txt"
    scan.write_text(
        "front matter\f" + text + "\f" + text,
        encoding="utf-8",
    )

    output = tmp_path / "output"
    build_crosswalk(canonical, scan, output, {2: 1})
    with (output / "print_page_crosswalk.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        row = next(csv.DictReader(handle, delimiter="\t"))
    assert row["match_confidence"] == "high_duplicate_scan_match"
    assert row["runner_up_scan_page"] in {"2", "3"}
