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

from badw_canonical_pages import build_volume, printed_page_number  # noqa: E402


def _run(index, text, y, font_id="body", *, unknown=False):
    return {
        "run_index": index,
        "decoded_unicode": text,
        "x": 10.0,
        "y": y,
        "font_id": font_id,
        "glyphs": [
            {
                "cid_hex": "0041",
                "glyph_signature": "outline-a",
                "unknown": unknown,
            }
        ],
    }


def _page(number, text, *, heading=False, pdf_page=None):
    if heading:
        runs = [
            _run(0, "ཀ", 100.0, "rabten", unknown=True),
            _run(1, "ka", 100.0, "italic"),
            _run(2, str(number), 20.0),
        ]
        candidates = [
            {
                "candidate_index": 0,
                "kind": "body_tibetan_text",
                "decoded_unicode": "ཀ",
                "run_indices": [0],
                "unknown_glyphs": 1,
                "x": 10.0,
                "y": 100.0,
            }
        ]
    else:
        runs = [_run(0, text, 100.0), _run(1, str(number), 20.0)]
        candidates = []
    return {
        "page": pdf_page or number,
        "visible_text": text,
        "normalized_reading": text.replace("\n", " "),
        "source_stream_text": text,
        "positioned_text_runs": runs,
        "tibetan_text_candidates": candidates,
        "unknown_glyphs": int(heading),
        "overprinted_glyphs": 0,
    }


def _record(url, source_hash, pages):
    return {
        "contract_version": "test-decoder-contract",
        "decoder_version": "test-decoder-version",
        "glyph_registry_sha256": "c" * 64,
        "canonical_url": url,
        "catalogue_identity": {"lemma": url.rsplit("/", 1)[-1]},
        "source_sha256": source_hash,
        "fonts": [
            {"font_id": "body", "family": "TGaramond", "style": "regular"},
            {"font_id": "italic", "family": "TGaramond", "style": "italic"},
            {"font_id": "rabten", "family": "RabtenTibetan", "style": "regular"},
        ],
        "pages": pages,
    }


def _write_fixture(decode_root: Path) -> None:
    positioned = decode_root / "decoded/corpus/positioned/volume_2"
    positioned.mkdir(parents=True)
    records = [
        _record(
            "https://example.test/pdf/a",
            "a" * 64,
            [_page(1, "ཀka\n1", heading=True), _page(2, "second\n2")],
        ),
        _record(
            "https://example.test/pdf/b",
            "b" * 64,
            [_page(2, "second\n2", pdf_page=1)],
        ),
    ]
    with gzip.open(positioned / "part-00.jsonl.gz", "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    reports = decode_root / "reports"
    reports.mkdir()
    with (reports / "structural_census.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["canonical_url", "page_dimensions"], delimiter="\t"
        )
        writer.writeheader()
        writer.writerow(
            {
                "canonical_url": "https://example.test/pdf/a",
                "page_dimensions": "[[595.22,842.0],[595.22,842.0]]",
            }
        )
        writer.writerow(
            {
                "canonical_url": "https://example.test/pdf/b",
                "page_dimensions": "[[595.22,842.0]]",
            }
        )


def _tree_hashes(root: Path):
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_printed_page_number_joins_same_baseline_fragments():
    runs = [_run(0, "body", 100.0), _run(1, "3", 20.0), _run(2, "63", 20.0)]
    assert printed_page_number(runs) == (363, "positioned_footer_same_baseline:363")


def test_canonical_builder_deduplicates_and_preserves_provenance(tmp_path):
    decode_root = tmp_path / "decode"
    _write_fixture(decode_root)
    first = tmp_path / "first"
    second = tmp_path / "second"

    summary = build_volume(decode_root, first, 2)
    assert summary["source_records"] == 2
    assert summary["source_page_occurrences"] == 3
    assert summary["canonical_pages"] == 2
    assert summary["numbered_pages"] == 2
    assert summary["headings_extracted"] == 1
    assert summary["distinct_unknown_identities"] == 1

    with (first / "volume_2/page_occurrences.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        occurrences = list(csv.DictReader(handle, delimiter="\t"))
    page_two = [row for row in occurrences if row["printed_page"] == "2"]
    assert len(page_two) == 2
    assert {row["source_pdf_sha256"] for row in page_two} == {"a" * 64, "b" * 64}

    with (first / "volume_2/headings.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        heading = next(csv.DictReader(handle, delimiter="\t"))
    assert heading["tibetan"] == "ཀ"
    assert heading["wylie"] == "ka"

    page_path = next((first / "volume_2/pages").glob("*.json.gz"))
    with gzip.open(page_path, "rt", encoding="utf-8") as handle:
        canonical = json.load(handle)
    assert canonical["representative_source"]["source_sha256"] in {"a" * 64, "b" * 64}
    assert canonical["source_decoder_contract_version"] == "test-decoder-contract"
    assert canonical["decoder_version"] == "test-decoder-version"
    assert canonical["glyph_registry_sha256"] == "c" * 64
    assert canonical["representative_fonts"]
    assert canonical["positioned_page"]["positioned_text_runs"]

    build_volume(decode_root, second, 2)
    assert _tree_hashes(first) == _tree_hashes(second)

    with pytest.raises(FileExistsError, match="existing output"):
        build_volume(decode_root, first, 2)
