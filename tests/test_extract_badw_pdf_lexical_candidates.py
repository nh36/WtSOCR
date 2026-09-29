"""Small synthetic, offline tests for source-faithful PDF lexical candidates."""

from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from extract_badw_pdf_lexical_candidates import build, extract


def _line(text: str, spans: list[tuple[int, int, str]] | None = None) -> dict:
    spans = spans or [(0, len(text), "regular")]
    return {"text": text, "page_id": "source-page", "span_index": 0,
            "printed_page": 17, "run_start": 0, "run_end_exclusive": len(text),
            "unknown_glyphs": [], "style_spans": [
                {"start": start, "end": end, "family": "TGaramond", "style": style}
                for start, end, style in spans]}


def _article(lines: list[dict], divisions: list[dict] | None = None,
             candidates: dict | None = None) -> dict:
    visual = "\n".join(line["text"] for line in lines)
    return {"contract_version": "badw-pdf-structural-parser-v3",
            "article_id": "badw:pdf:test", "volume": 2, "loc_headword": "sñags",
            "source_faithful_sha256": sha256(visual.encode()).hexdigest(),
            "visual_lines": lines,
            "divisions": divisions or [{"kind": "unsegmented", "label": "",
                                        "start_line_index": 0,
                                        "end_line_index_exclusive": len(lines)}],
            "candidates": candidates or {"german_quotes": [],
                                          "parenthetical_citations": [],
                                          "adjacent_quote_citation_pairs": []}}


def test_numbered_wrapped_definition_retains_exact_unicode_and_coordinates() -> None:
    lines = [_line(" 2. dritter Buchstabe des tibetischen Alpha-"), _line("bets.")]
    divisions = [{"kind": "numbered_sense", "label": "2", "start_line_index": 0,
                  "end_line_index_exclusive": 2}]
    result = extract(_article(lines, divisions))
    definition = result["definitions"][0]
    assert definition["text"] == "dritter Buchstabe des tibetischen Alpha-\nbets."
    assert result["visual_sha256"] == sha256("\n".join(line["text"] for line in lines).encode()).hexdigest()
    assert definition["source_lines"][1]["line_index"] == 1
    assert "\n".join(line["text"] for line in lines)[definition["visual_start"]:definition["visual_end"]] == definition["text"]


def test_morphology_reference_does_not_swallow_following_definition() -> None:
    first = " pf. zu ↑sgum ’thu aufpik-"
    lines = [_line(first, [(0, 9, "regular"), (9, 18, "italic"),
                           (18, len(first), "regular")]), _line("ken, auflesen."),
             _line("Lex. bza’ bya bsdogs pa (brDa).")]
    result = extract(_article(lines))
    assert [item["text"] for item in result["definitions"]] == ["aufpik-\nken, auflesen."]
    second = " pf. zu ↓rjes su dpog"
    lines = [_line(second, [(0, 9, "regular"), (9, len(second), "italic")]),
             _line("schlußfolgern, ermessen.")]
    assert extract(_article(lines))["definitions"][0]["text"] == "schlußfolgern, ermessen."


def test_variant_preamble_is_not_a_definition_but_numbered_sense_is() -> None:
    first = "auch thugs yi dam."
    lines = [_line(first, [(0, 5, "regular"), (5, len(first), "italic")]),
             _line("1. Gelöbnis.")]
    divisions = [{"kind": "unsegmented", "label": "", "start_line_index": 0,
                  "end_line_index_exclusive": 1},
                 {"kind": "numbered_sense", "label": "1", "start_line_index": 1,
                  "end_line_index_exclusive": 2}]
    assert [item["text"] for item in extract(_article(lines, divisions))["definitions"]] == ["Gelöbnis."]


def test_mixed_font_definition_continues_after_line_final_tilde() -> None:
    first = "1. Gelöbnis, Gelübde, Versprechen, ~"
    second = "mdzad geloben, ~ bźes Gelübde ablegen."
    lines = [_line(first, [(0, len(first) - 1, "regular"),
                           (len(first) - 1, len(first), "italic")]),
             _line(second, [(0, 5, "italic"), (5, 14, "regular"),
                            (14, 21, "italic"), (21, len(second), "regular")])]
    divisions = [{"kind": "numbered_sense", "label": "1", "start_line_index": 0,
                  "end_line_index_exclusive": 2}]
    assert extract(_article(lines, divisions))["definitions"][0]["text"] == (
        "Gelöbnis, Gelübde, Versprechen, ~\nmdzad geloben, ~ bźes Gelübde ablegen.")


def test_parenthetical_correction_does_not_create_partial_example() -> None:
    first = "~ kha lhor blta (r. lta) ba źig na phug ro gcig"
    second = "„translation“ (Siddh 11,2)."
    lines = [_line(first, [(0, 17, "italic"), (17, 21, "regular"),
                           (21, 24, "italic"), (24, 25, "regular"),
                           (25, len(first), "italic")]), _line(second)]
    visual = "\n".join(line["text"] for line in lines)
    quote_start = visual.index("„translation“")
    cite_start = visual.index("(Siddh 11,2)")
    candidates = {"german_quotes": [{"visual_start": quote_start,
                   "visual_end": quote_start + len("„translation“"),
                   "division_index": 0, "start_line_index": 1}],
                  "parenthetical_citations": [{"visual_start": cite_start,
                   "visual_end": cite_start + len("(Siddh 11,2)"),
                   "division_index": 0}],
                  "adjacent_quote_citation_pairs": [{"quote_index": 0,
                   "citation_index": 0}]}
    result = extract(_article(lines, candidates=candidates))
    assert result["tibetan_examples"] == []
    assert result["belegstellen"] == []
    assert result["unresolved_quotes"] == [{"quote_index": 0,
        "reason": "mixed_style_parenthetical_correction"}]


def test_tibetan_example_and_belegstelle_are_distinct_from_lexicon_quote() -> None:
    lines = [_line("Bedeutung."),
             _line("sñags pa „translation“ (Siddh 11,2).",
                   [(0, 8, "italic"), (8, 36, "regular")]),
             _line("Lex. sñags „dictionary gloss“ (brDa).",
                   [(0, 5, "regular"), (5, 10, "italic"), (10, 37, "regular")])]
    visual = "\n".join(line["text"] for line in lines)
    quote1 = visual.index("„translation“")
    cite1 = visual.index("(Siddh 11,2)")
    quote2 = visual.index("„dictionary gloss“")
    cite2 = visual.index("(brDa)")
    candidates = {"german_quotes": [
        {"visual_start": quote1, "visual_end": quote1 + len("„translation“"),
         "division_index": 0, "start_line_index": 1},
        {"visual_start": quote2, "visual_end": quote2 + len("„dictionary gloss“"),
         "division_index": 0, "start_line_index": 2}],
        "parenthetical_citations": [
            {"visual_start": cite1, "visual_end": cite1 + len("(Siddh 11,2)")},
            {"visual_start": cite2, "visual_end": cite2 + len("(brDa)")}],
        "adjacent_quote_citation_pairs": [
            {"quote_index": 0, "citation_index": 0},
            {"quote_index": 1, "citation_index": 1}]}
    result = extract(_article(lines, candidates=candidates))
    assert result["definitions"][0]["text"] == "Bedeutung."
    assert [item["text"] for item in result["tibetan_examples"]] == ["sñags pa", "sñags"]
    assert [item["lexical_region"] for item in result["tibetan_examples"]] == [False, True]
    assert len(result["belegstellen"]) == 1
    assert result["belegstellen"][0]["text"] == "sñags pa „translation“ (Siddh 11,2)"
    assert result["unresolved_quotes"] == [{"quote_index": 1, "reason": "lexicon_region"}]


def test_unknown_glyph_and_contract_failure_are_explicit() -> None:
    line = _line("⟦UNKNOWN:TGaramond⟧")
    line["unknown_glyphs"] = [{"cid": 9}]
    assert extract(_article([line]))["definitions"] == []
    bad = _article([_line("text")])
    bad["contract_version"] = "other"
    with pytest.raises(ValueError, match="unsupported PDF structure"):
        extract(bad)


def test_cached_source_replay_is_byte_deterministic(tmp_path: Path) -> None:
    article = _article([_line("deutsche Bedeutung.")])
    source = tmp_path / "articles.jsonl.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(article, ensure_ascii=False) + "\n")
    one = tmp_path / "one.jsonl.gz"
    two = tmp_path / "two.jsonl.gz"
    first = build(source, one)
    second = build(source, two)
    assert one.read_bytes() == two.read_bytes()
    assert first["logical_sha256"] == second["logical_sha256"]
    assert first["counts"]["articles"] == 1
