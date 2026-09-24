from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from badw_source_snapshot import create_snapshot, verify_snapshot  # noqa: E402


def _write_tsv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_inputs(root: Path) -> dict[str, Path]:
    canonical = root / "work/canonical"
    page_fields = ("printed_page", "page_id")
    unknown_fields = ("family", "style", "cid", "glyph_signature", "canonical_page_occurrences")
    for volume in (2, 3, 4):
        _write_tsv(canonical / f"volume_{volume}/canonical_pages.tsv", page_fields,
                   [{"printed_page": 1, "page_id": f"v{volume}-1"}])
        _write_tsv(canonical / f"volume_{volume}/canonical_unknown_glyphs.tsv", unknown_fields,
                   [{"family": "RabtenTibetan", "style": "regular", "cid": "0002",
                     "glyph_signature": "a" * 64, "canonical_page_occurrences": volume}])
    crosswalk = root / "work/crosswalk.tsv"
    _write_tsv(crosswalk, ("volume", "printed_page"), [{"volume": 2, "printed_page": 1}])
    coverage = root / "work/coverage"
    _write_tsv(coverage / "canonical_source_manifest.tsv", ("volume",), [])
    _write_tsv(coverage / "missing_from_canonical_snapshot.tsv", ("volume", "printed_page", "snapshot_status"),
               [{"volume": 2, "printed_page": 2, "snapshot_status": "absent_from_canonical_snapshot"}])
    (coverage / "summary.json").write_text("{}\n", encoding="utf-8")
    registry = root / "data/registry.tsv"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text("identity\nknown\n", encoding="utf-8")
    cache = root / "work/cache"
    body = b"small cached BAdW body"
    digest = sha256(body).hexdigest()
    object_file = cache / "objects/sha256" / digest[:2] / digest
    object_file.parent.mkdir(parents=True, exist_ok=True)
    object_file.write_bytes(body)
    manifest = {"request_key": "request-1", "requested_url": "https://example.test/pdf/a",
                "final_url": "https://example.test/pdf/a", "fetched_at_utc": "2026-09-24T00:00:00Z",
                "http_status": 200, "content_classification": "generated_pdf", "delivery_type": "generated_pdf",
                "valid_resource": True, "sha256": digest,
                "object_path": f"objects/sha256/{digest[:2]}/{digest}"}
    request = cache / "requests/aa/request-1.json"
    request.parent.mkdir(parents=True, exist_ok=True)
    request.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return {"canonical": canonical, "crosswalk": crosswalk, "coverage": coverage,
            "registry": registry, "cache": cache}


def _create(root: Path, destination: str = "snapshot") -> dict[str, object]:
    items = _write_inputs(root)
    return create_snapshot("fixture-20260924", "2026-09-24T12:00:00Z", items["canonical"], items["crosswalk"],
                           items["coverage"], items["registry"], items["cache"], root / f"work/{destination}", root)


def test_snapshot_is_deterministic_offline_and_records_quality_issues(tmp_path):
    _create(tmp_path, "first")
    _create(tmp_path, "second")
    first, second = tmp_path / "work/first", tmp_path / "work/second"
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {path.name: path.read_bytes() for path in second.iterdir()}
    verified = verify_snapshot(first, tmp_path)
    assert verified["verified"] is True
    with (first / "source_quality_inventory.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert {row["category"] for row in rows} == {"printed_page_gap", "unresolved_glyph_identity"}
    assert all(row["evidence_path"].startswith("work/") for row in rows)


def test_snapshot_rejects_cache_mutation_and_output_overwrite(tmp_path):
    _create(tmp_path)
    items = _write_inputs(tmp_path / "other")
    with pytest.raises(FileExistsError):
        create_snapshot("fixture", "2026-09-24T12:00:00Z", items["canonical"], items["crosswalk"],
                        items["coverage"], items["registry"], items["cache"], tmp_path / "work/snapshot", tmp_path)
    cache_body = next(path for path in (tmp_path / "work/cache/objects").rglob("*") if path.is_file())
    cache_body.write_bytes(b"changed")
    with pytest.raises(ValueError, match="cache"):
        verify_snapshot(tmp_path / "work/snapshot", tmp_path)
