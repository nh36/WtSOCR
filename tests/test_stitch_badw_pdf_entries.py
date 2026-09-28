"""Small synthetic tests for source-faithful BAdW PDF article stitching."""

from __future__ import annotations

from hashlib import sha256
import csv
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from badw_canonical_pages import stable_json_bytes
from stitch_badw_pdf_entries import _linked, stitch_volume, verify_output, build


def fixture_page(number: int, body: list[str], starts: list[int], *, predecessor: int | None = None,
                 successor: int | None = None, overlap: bool = True, section: bool = False):
    page_id = f"page-{number}"
    runs = [
        {"run_index": index, "decoded_unicode": text, "y": 700.0 - index,
         "font_id": "f", "glyphs": []}
        for index, text in enumerate(body)
    ]
    runs += [
        {"run_index": len(runs), "decoded_unicode": str(number), "y": 600.0,
         "font_id": "f", "glyphs": []},
        {"run_index": len(runs) + 1, "decoded_unicode": "header", "y": 815.0,
         "font_id": "f", "glyphs": []},
    ]
    body_text = "".join(run["decoded_unicode"] for run in runs)
    body_hash = sha256(body_text.encode()).hexdigest()
    row = {
        "page_id": page_id, "volume": "2", "printed_page": str(number),
        "predecessor_page_id": f"page-{predecessor}" if predecessor else "",
        "successor_page_id": f"page-{successor}" if successor else "",
        "predecessor_overlap_observations": "1" if predecessor and overlap else "0",
        "successor_overlap_observations": "1" if successor and overlap else "0",
        "canonical_object": f"pages/{page_id}.json.gz", "visible_body_sha256": body_hash,
    }
    page = {
        "page_id": page_id, "volume": 2, "printed_page": number,
        "positioned_page": {"positioned_text_runs": runs},
        "representative_source": {"canonical_url": f"https://example.invalid/{number}",
                                  "source_sha256": "a" * 64},
        "visible_body_sha256": body_hash,
    }
    entries = []
    for ordinal, start in enumerate(starts):
        end = starts[ordinal + 1] if ordinal + 1 < len(starts) else len(body)
        entries.append({
            "id": f"entry-{number}-{ordinal}", "page_id": page_id, "volume": 2,
            "printed_page": number, "loc_headword": f"word-{number}-{ordinal}",
            "loc_headword_reading": f"word-{number}-{ordinal}",
            "tibetan_headword": "ཀ", "homonym": "",
            "source_faithful_text": "".join(body[start:end]),
            "source_span": {"run_start": start, "run_end_exclusive": end,
                            "canonical_object": row["canonical_object"],
                            "visible_body_sha256": body_hash,
                            "representative_pdf_sha256": "a" * 64},
        })
    diagnostic = {
        "page_id": page_id, "body_run_end": str(len(body)),
        "entry_count": str(len(entries)),
        "leading_unassigned_runs": str(starts[0] if starts else len(body)),
        "section_headers": "1" if section else "0",
    }
    return row, page, entries, diagnostic


def test_join_page_leading_text_and_preserve_exact_spans():
    first = fixture_page(1, ["HEAD", " tail"], [0], successor=2)
    second = fixture_page(2, [" continued", "NEW"], [1], predecessor=1)
    articles, unassigned, counts = stitch_volume([first, second])
    assert len(articles) == 2 and not unassigned
    assert articles[0]["source_faithful_text"] == "HEAD tail continued"
    assert articles[0]["ending_status"] == "bounded_by_next_heading"
    assert [(s["printed_page"], s["run_start"], s["run_end_exclusive"])
            for s in articles[0]["source_spans"]] == [(1, 0, 2), (2, 0, 1)]
    assert articles[0]["source_spans"][1]["join_method"] == "observed_pdf_overlap"
    assert counts["joined_observed_pdf_overlap"] == 1


def test_gap_keeps_previous_entry_open_and_leading_fragment_unassigned():
    first = fixture_page(1, ["HEAD"], [0])
    third = fixture_page(3, ["orphan", "NEW"], [1])
    articles, unassigned, counts = stitch_volume([first, third])
    assert articles[0]["ending_status"] == "open_at_page_gap"
    assert [(s["printed_page"], s["source_faithful_text"]) for s in unassigned] == [(3, "orphan")]
    assert counts["unassigned_leading_fragments"] == 1


def test_reciprocal_adjacency_without_pdf_overlap_is_explicit():
    first = fixture_page(1, ["HEAD"], [0], successor=2, overlap=False)
    second = fixture_page(2, ["tail", "NEXT"], [1], predecessor=1, overlap=False)
    articles, _, counts = stitch_volume([first, second])
    assert articles[0]["source_faithful_text"] == "HEADtail"
    assert articles[0]["source_spans"][1]["join_method"] == "reciprocal_print_page_adjacency"
    assert counts["joined_reciprocal_print_page_adjacency"] == 1
    assert _linked(first[0], second[0]) == "reciprocal_print_page_adjacency"


def test_section_divider_is_not_attached_to_previous_article():
    first = fixture_page(1, ["HEAD"], [0], successor=2)
    second = fixture_page(2, ["ཁ", "NEXT"], [1], predecessor=1, section=True)
    articles, unassigned, counts = stitch_volume([first, second])
    assert not unassigned
    assert articles[0]["source_faithful_text"] == "HEAD"
    assert articles[0]["ending_status"] == "bounded_by_section_divider"
    assert counts["section_divider_pages"] == 1


def test_source_identity_mismatch_fails_closed():
    page = fixture_page(1, ["HEAD"], [0])
    page[2][0]["source_span"]["representative_pdf_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="source identity mismatch"):
        stitch_volume([page])


def test_entry_coverage_gap_fails_closed():
    page = fixture_page(1, ["HEAD", "TAIL"], [0])
    page[2][0]["source_span"]["run_end_exclusive"] = 1
    with pytest.raises(ValueError, match="uncovered article text"):
        stitch_volume([page])


def test_offline_output_verifier_checks_spans_and_logical_hash(tmp_path):
    article = stitch_volume([fixture_page(1, ["HEAD"], [0])])[0][0]
    article_blob = stable_json_bytes(article) + b"\n"
    for filename, blob in (
        ("pdf_article_witnesses.jsonl.gz", article_blob),
        ("unassigned_page_fragments.jsonl.gz", b""),
    ):
        with gzip.open(tmp_path / filename, "wb") as handle:
            handle.write(blob)
    summary = {
        "contract_version": "badw-pdf-article-witness-v1",
        "article_logical_sha256": sha256(article_blob).hexdigest(),
        "unassigned_logical_sha256": sha256(b"").hexdigest(),
        "counts": {
            "article_source_spans": 1, "article_unknown_glyph_occurrences": 0,
            "unassigned_leading_fragments": 0,
            "volume_2_articles": 1, "volume_3_articles": 0, "volume_4_articles": 0,
        },
    }
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert verify_output(tmp_path)["articles"] == 1
    del summary["counts"]["unassigned_leading_fragments"]
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert verify_output(tmp_path)["articles"] == 1
    article["source_spans"][0]["source_text_sha256"] = "0" * 64
    tampered_blob = stable_json_bytes(article) + b"\n"
    with gzip.open(tmp_path / "pdf_article_witnesses.jsonl.gz", "wb") as handle:
        handle.write(tampered_blob)
    summary["article_logical_sha256"] = sha256(tampered_blob).hexdigest()
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="source span hash mismatch"):
        verify_output(tmp_path)


def test_stitch_rejects_mismatched_extraction_snapshot_before_writing(tmp_path):
    canonical = tmp_path / "canonical"
    entries = tmp_path / "entries"
    entries.mkdir()
    hashes = {}
    for volume in (2, 3, 4):
        folder = canonical / f"volume_{volume}"
        folder.mkdir(parents=True)
        index = folder / "canonical_pages.tsv"
        index.write_text("page_id\tprinted_page\n", encoding="utf-8")
        hashes[f"volume_{volume}/canonical_pages.tsv"] = sha256(index.read_bytes()).hexdigest()
    hashes["volume_3/canonical_pages.tsv"] = "0" * 64
    (entries / "summary.json").write_text(
        json.dumps({"canonical_index_sha256": hashes}), encoding="utf-8"
    )
    output = tmp_path / "stitched"
    with pytest.raises(ValueError, match="snapshot mismatch: volume_3"):
        build(canonical, entries, output)
    assert not output.exists()


def test_continuation_attribution_must_match_verified_article_span(tmp_path):
    first = fixture_page(1, ["HEAD"], [0], successor=2)
    second = fixture_page(2, ["tail"], [], predecessor=1)
    article = stitch_volume([first, second])[0][0]
    article_blob = stable_json_bytes(article) + b"\n"
    with gzip.open(tmp_path / "pdf_article_witnesses.jsonl.gz", "wb") as handle:
        handle.write(article_blob)
    with gzip.open(tmp_path / "unassigned_page_fragments.jsonl.gz", "wb") as handle:
        handle.write(b"")
    span = article["source_spans"][1]
    row = {
        "article_id": article["id"], "loc_headword": article["loc_headword"],
        "start_printed_page": article["start_printed_page"],
        "continuation_page": span["printed_page"], "continuation_page_id": span["page_id"],
        "run_start": span["run_start"], "run_end_exclusive": span["run_end_exclusive"],
        "join_method": span["join_method"], "source_text_sha256": span["source_text_sha256"],
    }
    attribution_path = tmp_path / "continuation_attributions.tsv"
    with attribution_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row), delimiter="\t")
        writer.writeheader()
        writer.writerow(row)
    summary = {
        "contract_version": "badw-pdf-article-witness-v1",
        "article_logical_sha256": sha256(article_blob).hexdigest(),
        "unassigned_logical_sha256": sha256(b"").hexdigest(),
        "continuation_attributions_sha256": sha256(attribution_path.read_bytes()).hexdigest(),
        "counts": {"article_source_spans": 2, "article_unknown_glyph_occurrences": 0,
                   "volume_2_articles": 1, "volume_3_articles": 0, "volume_4_articles": 0},
    }
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert verify_output(tmp_path)["continuation_attributions"] == 1
    row["article_id"] = "wrong-entry"
    with attribution_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row), delimiter="\t")
        writer.writeheader()
        writer.writerow(row)
    summary["continuation_attributions_sha256"] = sha256(attribution_path.read_bytes()).hexdigest()
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="attributions do not match"):
        verify_output(tmp_path)
