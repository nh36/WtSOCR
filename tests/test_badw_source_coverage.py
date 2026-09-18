from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from badw_source_coverage import build_source_coverage  # noqa: E402


def _write_tsv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _fixture(root: Path) -> tuple[Path, Path]:
    canonical = root / "canonical"
    page_fields = ("printed_page", "page_id", "visible_body_sha256", "canonical_object", "representative_url", "representative_source_sha256", "url_page_occurrences", "sequence_confidence", "unknown_glyph_occurrences")
    _write_tsv(canonical / "volume_2/canonical_pages.tsv", page_fields, [{"printed_page": 1, "page_id": "v2-1", "visible_body_sha256": "a" * 64, "canonical_object": "pages/v2-1.json.gz", "representative_url": "https://example.test/a", "representative_source_sha256": "b" * 64, "url_page_occurrences": 3, "sequence_confidence": "high", "unknown_glyph_occurrences": 0}])
    _write_tsv(canonical / "volume_3/canonical_pages.tsv", page_fields, [])
    _write_tsv(canonical / "volume_4/canonical_pages.tsv", page_fields, [{"printed_page": 1, "page_id": "v4-1", "visible_body_sha256": "c" * 64, "canonical_object": "pages/v4-1.json.gz", "representative_url": "https://example.test/c", "representative_source_sha256": "d" * 64, "url_page_occurrences": 1, "sequence_confidence": "high", "unknown_glyph_occurrences": 2}])
    crosswalk = root / "crosswalk.tsv"
    fields = ("volume", "printed_page", "scan_page", "scan_half", "match_confidence", "mapping_method")
    _write_tsv(crosswalk, fields, [
        {"volume": 2, "printed_page": 1, "scan_page": 2, "scan_half": "left", "match_confidence": "high_text_match", "mapping_method": "tokens"},
        {"volume": 2, "printed_page": 2, "scan_page": 2, "scan_half": "right", "match_confidence": "high_sequence", "mapping_method": "neighbour"},
        {"volume": 3, "printed_page": 1, "scan_page": 3, "scan_half": "left", "match_confidence": "high_text_match", "mapping_method": "tokens"},
        {"volume": 4, "printed_page": 1, "scan_page": 4, "scan_half": "right", "match_confidence": "high_text_match", "mapping_method": "tokens"},
    ])
    return canonical, crosswalk


def _tree_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest() for path in root.rglob("*") if path.is_file()}


def test_manifest_is_complete_deterministic_and_temporally_cautious(tmp_path):
    canonical, crosswalk = _fixture(tmp_path)
    expected = {2: 2, 3: 1, 4: 1}
    first, second = tmp_path / "first", tmp_path / "second"
    summary = build_source_coverage(canonical, crosswalk, first, expected)
    build_source_coverage(canonical, crosswalk, second, expected)
    assert summary["present_in_canonical_snapshot"] == 2
    assert summary["absent_from_canonical_snapshot"] == 2
    assert _tree_hashes(first) == _tree_hashes(second)
    with (first / "missing_from_canonical_snapshot.tsv").open(encoding="utf-8", newline="") as handle:
        missing = list(csv.DictReader(handle, delimiter="\t"))
    assert {(row["volume"], row["printed_page"]) for row in missing} == {("2", "2"), ("3", "1")}
    assert all(row["snapshot_status"] == "absent_from_canonical_snapshot" for row in missing)
    assert "unavailable" not in (first / "canonical_source_manifest.tsv").read_text(encoding="utf-8")
    recorded = json.loads((first / "summary.json").read_text(encoding="utf-8"))
    assert recorded["manifest_sha256"] == sha256((first / "canonical_source_manifest.tsv").read_bytes()).hexdigest()


def test_manifest_requires_complete_unique_crosswalk(tmp_path):
    canonical, crosswalk = _fixture(tmp_path)
    rows = [
        row
        for row in csv.DictReader(crosswalk.open(encoding="utf-8", newline=""), delimiter="\t")
        if not (row["volume"] == "2" and row["printed_page"] == "2")
    ]
    _write_tsv(
        crosswalk,
        ("volume", "printed_page", "scan_page", "scan_half", "match_confidence", "mapping_method"),
        rows,
    )
    with pytest.raises(ValueError, match="crosswalk lacks v2 p2"):
        build_source_coverage(canonical, crosswalk, tmp_path / "out", {2: 2, 3: 0, 4: 0})
