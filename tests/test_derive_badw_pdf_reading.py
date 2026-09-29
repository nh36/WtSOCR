"""Offline tests for the reversible BAdW PDF reading layer."""
from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from derive_badw_pdf_reading import build, derive_item, project
from extract_badw_pdf_lexical_candidates import extract


def _line(text: str, index: int, page: str = "page-1") -> dict:
    return {"text": text, "page_id": page, "span_index": 0,
            "printed_page": 5, "run_start": index, "run_end_exclusive": index + 1,
            "unknown_glyphs": [], "style_spans": [{"start": 0, "end": len(text),
                "family": "TGaramond", "style": "regular"}]}


def _article() -> dict:
    lines = [_line("für", 0), _line("skt. Alpha-", 1), _line("bet", 2)]
    visual = "\n".join(line["text"] for line in lines)
    return {"contract_version": "badw-pdf-structural-parser-v5",
            "article_id": "badw:pdf:synthetic", "volume": 2,
            "loc_headword": "test", "source_faithful_sha256": sha256(visual.encode()).hexdigest(),
            "visual_lines": lines, "divisions": [{"kind": "unsegmented", "label": "",
                "start_line_index": 0, "end_line_index_exclusive": len(lines)}],
            "candidates": {"german_quotes": [], "parenthetical_citations": [],
                           "adjacent_quote_citation_pairs": []}}


def test_space_default_and_hyphen_review_keep_source_and_offsets() -> None:
    article = _article()
    lexical = extract(article)
    item = project(article, lexical)["annotations"]["definitions"][0]
    assert item["source_text"] == "für\nskt. Alpha-\nbet"
    assert item["reading_text"] == "für skt. Alpha-\nbet"
    assert [(boundary["kind"], boundary["replacement"], boundary["source_visual_offset"])
            for boundary in item["boundaries"]] == [
                ("same_item_space", " ", 3), ("hyphen_boundary_review", "\n", 15)]
    assert article["visual_lines"][0]["text"] == "für"
    assert lexical["definitions"][0]["text"] == item["source_text"]


def test_existing_space_and_page_break_are_not_double_joined() -> None:
    source = "für \nskt.\nnext"
    lines = [{"line_index": 0, "page_id": "one"},
             {"line_index": 1, "page_id": "one"},
             {"line_index": 2, "page_id": "two"}]
    item = derive_item(source, 12, lines)
    assert item["reading_text"] == "für skt.\nnext"
    assert [b["kind"] for b in item["boundaries"]] == [
        "same_item_space", "page_boundary_review"]
    assert item["boundaries"][0]["replacement"] == ""


def test_capital_fragment_in_a_name_is_left_for_review() -> None:
    lines = [{"line_index": 0, "page_id": "one"},
             {"line_index": 1, "page_id": "one"}]
    item = derive_item("(H\nAHN 1996)", 12, lines)
    assert item["reading_text"] == "(H\nAHN 1996)"
    assert item["boundaries"][0]["kind"] == "capital_fragment_boundary_review"
    assert item["boundaries"][0]["replacement"] == "\n"
    ordinary = derive_item("für\nskt.", 12, lines)
    assert ordinary["reading_text"] == "für skt."


def test_numeric_fragments_remain_literal_for_superscript_review() -> None:
    lines = [{"line_index": 0, "page_id": "one"},
             {"line_index": 1, "page_id": "one"}]
    item = derive_item("10\n51", 12, lines)
    assert item["reading_text"] == "10\n51"
    assert item["boundaries"][0]["kind"] == "numeric_fragment_boundary_review"
    citation = derive_item("(PT1287\n495)", 12, lines)
    assert citation["reading_text"] == "(PT1287 495)"
    assert citation["boundaries"][0]["kind"] == "same_item_space"
    slash_citation = derive_item("(MTH3/5/10\n45)", 12, lines)
    assert slash_citation["reading_text"] == "(MTH3/5/10 45)"
    assert slash_citation["boundaries"][0]["kind"] == "same_item_space"
    three_lines = lines + [{"line_index": 2, "page_id": "one"}]
    exponent = derive_item("10\n51\n,", 12, three_lines)
    assert exponent["reading_text"] == "10\n51\n,"
    assert all(b["kind"] == "numeric_fragment_boundary_review"
               for b in exponent["boundaries"])


@pytest.mark.parametrize("closer", ["“", ")", ";", "?", "!"])
def test_line_break_before_closing_punctuation_does_not_insert_space(closer: str) -> None:
    lines = [{"line_index": 0, "page_id": "one"},
             {"line_index": 1, "page_id": "one"}]
    item = derive_item(f"Wort\n{closer}", 4, lines)
    assert item["reading_text"] == f"Wort{closer}"
    assert item["boundaries"][0]["kind"] == "right_closer_join"
    assert item["source_text"] == f"Wort\n{closer}"


def test_line_break_before_low_opening_quote_or_tibetan_initial_keeps_space() -> None:
    lines = [{"line_index": 0, "page_id": "one"},
             {"line_index": 1, "page_id": "one"}]
    for following in (",Unglück", "’dzum"):
        item = derive_item(f"Wort\n{following}", 4, lines)
        assert item["reading_text"] == f"Wort {following}"
        assert item["boundaries"][0]["kind"] == "same_item_space"


def test_bad_source_anchor_rejected() -> None:
    article = _article()
    lexical = extract(article)
    lexical["definitions"][0]["text"] = "silently changed"
    with pytest.raises(ValueError, match="source anchor"):
        project(article, lexical)


def test_different_cached_source_object_rejected() -> None:
    article = _article()
    lexical = extract(article)
    lexical["source_objects"] = [{"sha256": "different"}]
    with pytest.raises(ValueError, match="source identity"):
        project(article, lexical)


def test_offline_build_is_byte_deterministic(tmp_path: Path) -> None:
    article = _article()
    lexical = extract(article)
    source = tmp_path / "structure.jsonl.gz"
    flat = tmp_path / "lexical.jsonl.gz"
    for path, record in ((source, article), (flat, lexical)):
        with path.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write((json.dumps(record, ensure_ascii=False) + "\n").encode())
    first = tmp_path / "first.jsonl.gz"
    second = tmp_path / "second.jsonl.gz"
    assert build(source, flat, first) == build(source, flat, second)
    assert first.read_bytes() == second.read_bytes()
