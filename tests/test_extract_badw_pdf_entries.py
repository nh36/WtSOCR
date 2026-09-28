from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from extract_badw_pdf_entries import extract_page, build  # noqa: E402
from audit_badw_pdf_entries import audit  # noqa: E402


def _run(index: int, value: str, font: str, y: float = 400.0, unknown: bool = False):
    return {
        "run_index": index, "decoded_unicode": value, "x": 10.0, "y": y,
        "font_id": font, "glyphs": [{"unknown": unknown, "cid_hex": "00AF",
                                      "glyph_signature": "f" * 64}] if unknown else [],
    }


def _page():
    page = {
        "page_id": "badw-v2-abc", "volume": 2, "printed_page": 7,
        "representative_source": {"canonical_url": "https://example.test/pdf/ka",
                                  "source_sha256": "a" * 64},
        "representative_fonts": [
            {"font_id": "t", "family": "RabtenTibetan", "style": "regular"},
            {"font_id": "i", "family": "TGaramond", "style": "italic"},
            {"font_id": "r", "family": "TGaramond", "style": "regular"},
        ],
        "positioned_page": {
            "positioned_text_runs": [
                _run(0, "previous", "r"), _run(1, "ཀ", "t"), _run(2, "1", "r"),
                _run(3, "ka", "i"), _run(4, " meaning ↑", "r"),
                _run(5, "ཁ", "t"), _run(6, "kha", "i"),
                _run(7, " Ḍa [?]", "r", 380.0, True),
                _run(8, "7", "r", 100.0), _run(9, "repeated header", "r", 820.0),
            ],
            "tibetan_text_candidates": [
                {"candidate_index": 0, "kind": "body_tibetan_text", "decoded_unicode": "ཀ",
                 "run_indices": [1], "unknown_glyphs": 0, "x": 10.0, "y": 400.0},
                {"candidate_index": 1, "kind": "body_tibetan_text", "decoded_unicode": "ཁ",
                 "run_indices": [5], "unknown_glyphs": 0, "x": 10.0, "y": 400.0},
            ],
        },
    }
    page["source_faithful_decoded_text"] = "".join(
        run["decoded_unicode"] for run in page["positioned_page"]["positioned_text_runs"]
    )
    page["visible_body_sha256"] = sha256(page["source_faithful_decoded_text"].encode()).hexdigest()
    return page


def test_exact_run_spans_exclude_footer_and_repeated_header():
    entries, diagnostic = extract_page(_page(), "volume_2/pages/page.json.gz")
    assert len(entries) == 2
    assert diagnostic["leading_unassigned_runs"] == 1
    assert diagnostic["footer_evidence"] == "positioned_footer"
    assert entries[0]["source_faithful_text"] == "ཀ1ka meaning ↑"
    assert entries[0]["homonym"] == "1"
    assert entries[0]["boundary_status"] == "bounded_on_page"
    assert entries[1]["source_faithful_text"] == "ཁkha Ḍa [?]"
    assert entries[1]["boundary_status"] == "page_end_open"
    assert entries[1]["unknown_glyphs"][0]["cid_hex"] == "00AF"
    assert entries[1]["source_span"]["run_end_exclusive"] == 8


def test_missing_loc_stays_explicit_and_no_semantic_fields_are_inferred():
    page = _page()
    page["positioned_page"]["positioned_text_runs"][6]["font_id"] = "r"
    entries, diagnostic = extract_page(page, "volume_2/pages/page.json.gz")
    assert diagnostic["unpaired_headings"] == 1
    assert entries[1]["loc_headword"] == ""
    assert "missing_loc_heading" in entries[1]["flags"]
    assert "senses" not in entries[1]
    assert "attestations" not in entries[1]


def test_homonym_lower_baseline_does_not_hide_loc_heading():
    page = _page()
    runs = page["positioned_page"]["positioned_text_runs"]
    runs[2]["y"] = 395.392
    runs[3]["y"] = 390.784
    entries, diagnostic = extract_page(page, "volume_2/pages/page.json.gz")
    assert diagnostic["unpaired_headings"] == 0
    assert entries[0]["homonym"] == "1"
    assert entries[0]["loc_headword"] == "ka"


def test_footer_is_identified_even_when_printed_page_is_positioned_high():
    page = _page()
    page["positioned_page"]["positioned_text_runs"][8]["y"] = 635.0
    entries, diagnostic = extract_page(page, "volume_2/pages/page.json.gz")
    assert diagnostic["footer_evidence"] == "positioned_footer"
    assert entries[-1]["source_span"]["run_end_exclusive"] == 8


def test_wrapped_tibetan_and_multiline_loc_form_one_entry():
    page = _page()
    runs = page["positioned_page"]["positioned_text_runs"]
    runs[:] = [
        _run(0, "ཀཁ", "t", 400.0),
        _run(1, "ག།", "t", 398.9),
        _run(2, "ka ", "i", 397.7),
        _run(3, "kha", "i", 396.5),
        _run(4, " meaning", "r", 396.5),
        _run(5, "7", "r", 635.0),
    ]
    page["positioned_page"]["tibetan_text_candidates"] = [
        {"candidate_index": 0, "kind": "body_tibetan_text", "decoded_unicode": "ཀཁ",
         "run_indices": [0], "unknown_glyphs": 0, "x": 10.0, "y": 400.0},
        {"candidate_index": 1, "kind": "body_tibetan_text", "decoded_unicode": "ག།",
         "run_indices": [1], "unknown_glyphs": 0, "x": 10.0, "y": 398.9},
    ]
    entries, diagnostic = extract_page(page, "volume_2/pages/page.json.gz")
    assert len(entries) == 1
    assert diagnostic["wrapped_tibetan_headings"] == 1
    assert diagnostic["multiline_loc_headings"] == 1
    assert entries[0]["tibetan_headword"] == "ཀཁག།"
    assert entries[0]["loc_headword"] == "ka kha"
    assert entries[0]["loc_headword_reading"] == "ka\nkha"
    assert entries[0]["source_span"]["tibetan_run_indices"] == [0, 1]
    assert entries[0]["source_span"]["loc_run_indices"] == [2, 3]


def test_alphabet_section_title_is_not_an_entry():
    page = _page()
    page["positioned_page"]["positioned_text_runs"][0] = _run(0, "ཀ", "t", 700.0)
    page["positioned_page"]["tibetan_text_candidates"].insert(
        0, {"candidate_index": 9, "kind": "body_tibetan_text", "decoded_unicode": "ཀ",
            "run_indices": [0], "unknown_glyphs": 0, "x": 10.0, "y": 700.0})
    entries, diagnostic = extract_page(page, "volume_2/pages/page.json.gz")
    assert len(entries) == 2
    assert diagnostic["section_headers"] == 1
    assert entries[0]["source_span"]["run_start"] == 1


def test_build_is_byte_deterministic_and_replays_page(tmp_path: Path):
    root = tmp_path / "canonical"
    for volume in (2, 3, 4):
        folder = root / f"volume_{volume}"
        (folder / "pages").mkdir(parents=True)
        (folder / "canonical_pages.tsv").write_text(
            "page_id\tprinted_page\tcanonical_object\tvisible_body_sha256\n" +
            (f"badw-v2-abc\t7\tpages/page.json.gz\t{_page()['visible_body_sha256']}\n" if volume == 2 else ""),
            encoding="utf-8",
        )
    with gzip.open(root / "volume_2/pages/page.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(_page(), handle, ensure_ascii=False)
    one = build(root, tmp_path / "one")
    two = build(root, tmp_path / "two")
    assert one["canonical_index_sha256"] == two["canonical_index_sha256"]
    assert one["logical_sha256"] == two["logical_sha256"]
    assert (tmp_path / "one/pdf_page_entries.jsonl.gz").read_bytes() == (
        tmp_path / "two/pdf_page_entries.jsonl.gz").read_bytes()
    with gzip.open(tmp_path / "one/pdf_page_entries.jsonl.gz", "rt", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    assert len(records) == 2
    replay = audit(root, tmp_path / "one/pdf_page_entries.jsonl.gz")
    assert replay["logical_sha256"] == one["logical_sha256"]
    assert replay["counts"]["entries"] == 2
    page = _page()
    for record in records:
        span = record["source_span"]
        runs = page["positioned_page"]["positioned_text_runs"]
        assert record["source_faithful_text"] == "".join(
            r["decoded_unicode"] for r in runs[span["run_start"]:span["run_end_exclusive"]]
        )
    records[0]["source_faithful_text"] = "damaged"
    damaged = tmp_path / "damaged.jsonl.gz"
    with gzip.open(damaged, "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    with pytest.raises(ValueError, match="source-faithful text mismatch"):
        audit(root, damaged)


def test_incomplete_canonical_snapshot_fails_before_writing_output(tmp_path: Path):
    root = tmp_path / "canonical"
    for volume in (2, 3, 4):
        folder = root / f"volume_{volume}"
        folder.mkdir(parents=True)
        (folder / "canonical_pages.tsv").write_text(
            "page_id\tprinted_page\tcanonical_object\tvisible_body_sha256\n" +
            ("missing\t1\tpages/missing.json.gz\thash\n" if volume == 3 else ""),
            encoding="utf-8",
        )
    output = tmp_path / "output"
    with pytest.raises(FileNotFoundError, match="indexed canonical object missing"):
        build(root, output)
    assert not output.exists()
