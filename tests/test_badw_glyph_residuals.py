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

from badw_glyph_residuals import build_residual_inventory  # noqa: E402


def _write_page(root: Path, volume: int, page: int, *, unknown: bool) -> None:
    pages = root / f"volume_{volume}" / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    glyph = {
        "cid_hex": "0041",
        "glyph_signature": "outline-a",
        "unicode": "⟦UNKNOWN:Test:regular:0041:outline-a⟧" if unknown else "a",
        "unknown": unknown,
    }
    record = {
        "page_id": f"v{volume}-p{page}",
        "printed_page": page,
        "representative_source": {"canonical_url": f"https://example.test/{page}"},
        "representative_fonts": [
            {
                "font_id": "font-a",
                "family": "Test",
                "style": "regular",
                "program_sha256": "a" * 64,
                "font_resource_sha256": "b" * 64,
            }
        ],
        "positioned_page": {
            "positioned_text_runs": [
                {
                    "font_id": "font-a",
                    "decoded_unicode": glyph["unicode"],
                    "glyphs": [glyph],
                }
            ]
        },
    }
    with gzip.open(pages / f"p{page}.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, sort_keys=True)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_registry(path: Path) -> None:
    path.write_text(
        "family\tstyle\tcid\tglyph_signature\tunicode\tevidence_method\t"
        "evidence_count\tevidence_note\n"
        "Test\tregular\t0041\toutline-old\ta\ttest\t1\tfixture\n"
        "Test\tregular\t0042\toutline-a\tb\ttest\t1\tfixture\n",
        encoding="utf-8",
    )


def test_canonical_residual_inventory_counts_and_is_deterministic(tmp_path):
    canonical = tmp_path / "canonical"
    _write_page(canonical, 2, 1, unknown=True)
    _write_page(canonical, 2, 2, unknown=True)
    _write_page(canonical, 2, 3, unknown=False)

    first = tmp_path / "first"
    second = tmp_path / "second"
    registry = tmp_path / "registry.tsv"
    _write_registry(registry)
    summary = build_residual_inventory(canonical, first, (2,), registry)
    build_residual_inventory(canonical, second, (2,), registry)

    assert summary["canonical_pages"] == 3
    assert summary["pages_with_unknowns"] == 2
    assert summary["distinct_unknown_identities"] == 1
    assert summary["unknown_occurrences"] == 2
    with (first / "unknown_glyph_identities.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        row = next(csv.DictReader(handle, delimiter="\t"))
    assert row["family"] == "Test"
    assert row["canonical_page_count"] == "2"
    assert row["font_program_hashes"] == "a" * 64
    assert row["registry_relation"] == "ambiguous_registry_analogy"
    assert row["same_cid_registry_unicode"] == "a"
    assert row["same_outline_registry_unicode"] == "b"
    assert summary["unknown_identities_by_registry_relation"] == {
        "ambiguous_registry_analogy": 1
    }
    assert _tree_hashes(first) == _tree_hashes(second)

    with pytest.raises(FileExistsError, match="existing data"):
        build_residual_inventory(canonical, first, (2,), registry)


@pytest.mark.parametrize(
    ("cid", "signature", "expected"),
    [
        ("0041", "outline-old", "exact_identity_registered"),
        ("0043", "outline-a", "registered_outline_different_cid"),
        ("0041", "outline-new", "registered_cid_new_outline"),
        ("0043", "outline-new", "novel_identity"),
    ],
)
def test_registry_relationship_classification(tmp_path, cid, signature, expected):
    canonical = tmp_path / "canonical"
    _write_page(canonical, 2, 1, unknown=True)
    page = next((canonical / "volume_2" / "pages").glob("*.json.gz"))
    with gzip.open(page, "rt", encoding="utf-8") as handle:
        record = json.load(handle)
    glyph = record["positioned_page"]["positioned_text_runs"][0]["glyphs"][0]
    glyph["cid_hex"] = cid
    glyph["glyph_signature"] = signature
    with gzip.open(page, "wt", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, sort_keys=True)
    registry = tmp_path / "registry.tsv"
    _write_registry(registry)

    output = tmp_path / "output"
    build_residual_inventory(canonical, output, (2,), registry)
    with (output / "unknown_glyph_identities.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        row = next(csv.DictReader(handle, delimiter="\t"))
    assert row["registry_relation"] == expected
