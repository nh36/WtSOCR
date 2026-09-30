"""Small synthetic, offline tests for source-faithful PDF lexical candidates."""

from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from extract_badw_pdf_lexical_candidates import build, extract, validate


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
    return {"contract_version": "badw-pdf-structural-parser-v6",
            "article_id": "badw:pdf:test", "volume": 2, "loc_headword": "sñags",
            "source_faithful_sha256": sha256(visual.encode()).hexdigest(),
            "visual_lines": lines,
            "divisions": divisions or [{"kind": "unsegmented", "label": "",
                                        "start_line_index": 0,
                                        "end_line_index_exclusive": len(lines)}],
            "candidates": candidates or {"german_quotes": [],
                                          "parenthetical_citations": [],
                                          "adjacent_quote_citation_pairs": []}}


def _example_article(lines: list[dict]) -> dict:
    """One synthetic quotation/citation, with exact source coordinates."""
    text = "\n".join(line["text"] for line in lines)
    qstart, qend = text.index("„"), text.index("“") + 1
    cstart, cend = text.index("(Source 1)"), text.index("(Source 1)") + 10
    return _article(lines, candidates={
        "german_quotes": [{"visual_start": qstart, "visual_end": qend,
                           "division_index": 0,
                           "start_line_index": text[:qstart].count("\n")}],
        "parenthetical_citations": [{"visual_start": cstart, "visual_end": cend,
                                     "division_index": 0}],
        "adjacent_quote_citation_pairs": [{"quote_index": 0, "citation_index": 0}]})


@pytest.mark.parametrize("apparatus", ["(v. l. kha)", "(Gl. kha (r. ka))", "{kha}"])
def test_roman_apparatus_between_italic_runs_preserves_full_example(apparatus: str) -> None:
    text = f"ka {apparatus} ga „translation“ (Source 1)"
    tail = text.index("ga „")
    article = _example_article([_line(text, [(0, 2, "italic"), (2, tail, "regular"),
                                           (tail, tail + 2, "italic"),
                                           (tail + 2, len(text), "regular")])])
    result = extract(article)
    assert result["tibetan_examples"][0]["text"] == f"ka {apparatus} ga"
    assert len(result["belegstellen"]) == 1
    validate(article, result)


def test_page_boundary_inside_balanced_correction_recovers_prefix() -> None:
    first, second = "ka (r.", "kha) ga „translation“ (Source 1)"
    lines = [_line(first, [(0, 2, "italic"), (2, len(first), "regular")]),
             _line(second, [(0, 3, "italic"), (3, 5, "regular"),
                            (5, 7, "italic"), (7, len(second), "regular")])]
    lines[1]["page_id"] = "next-source-page"
    lines[1]["printed_page"] = 18
    article = _example_article(lines)
    result = extract(article)
    assert result["tibetan_examples"][0]["text"] == "ka (r.\nkha) ga"
    assert len(result["tibetan_examples"][0]["source_lines"]) == 2
    validate(article, result)


def test_leading_gloss_is_not_truncated_to_italic_tail() -> None:
    text = "(Gl. ka) ga „translation“ (Source 1)"
    article = _example_article([_line(text, [(0, 5, "regular"), (5, 7, "italic"),
                                           (7, 9, "regular"), (9, 11, "italic"),
                                           (11, len(text), "regular")])])
    result = extract(article)
    assert result["tibetan_examples"][0]["text"] == "(Gl. ka) ga"
    validate(article, result)


@pytest.mark.parametrize("token,accepted", [
    ("⟦UNKNOWN:Arial:regular:0003:ebbba6ed181c⟧", True),
    ("⟦UNKNOWN:TGaramond:italic:00E2:960b47bc4fc7⟧", False),
])
def test_unknowns_remain_literal_and_only_verified_layout_is_exempt(token: str, accepted: bool) -> None:
    text = f"ka {token} „translation“ (Source 1)"
    line = _line(text, [(0, 2, "italic"), (2, len(text), "regular")])
    line["unknown_glyphs"] = [{"cid": 3}]
    article = _example_article([line])
    result = extract(article)
    assert bool(result["belegstellen"]) == accepted
    assert len(result["nonprinting_layout_tokens"]) == int(accepted)
    if accepted:
        assert token in result["tibetan_examples"][0]["text"]
        result["nonprinting_layout_tokens"][0]["text"] = " "
        with pytest.raises(ValueError, match="source span does not replay"):
            validate(article, result)


def test_unknown_inside_apparatus_blocks_even_when_boundary_mask_allows_it() -> None:
    token = "⟦UNKNOWN:TGaramond:italic:00E2:960b47bc4fc7⟧"
    text = f"ka (r. {token}) ga „translation“ (Source 1)"
    tail = text.index("ga „")
    article = _example_article([_line(text, [(0, 2, "italic"), (2, tail, "regular"),
                                           (tail, tail + 2, "italic"),
                                           (tail + 2, len(text), "regular")])])
    result = extract(article)
    assert not result["belegstellen"]
    assert result["unresolved_quotes"][0]["reason"] == "empty_or_unknown_loc_span"


def test_leading_gloss_expansion_cannot_bypass_unknown_barrier() -> None:
    token = "⟦UNKNOWN:TGaramond:regular:001F:abcdef123456⟧"
    text = f"(Gl. {token} ka) ga „translation“ (Source 1)"
    start = text.index("ka)")
    tail = text.index("ga „")
    article = _example_article([_line(text, [
        (0, start, "regular"), (start, start + 2, "italic"),
        (start + 2, tail, "regular"), (tail, tail + 2, "italic"),
        (tail + 2, len(text), "regular")])])
    result = extract(article)
    assert not result["tibetan_examples"]
    assert not result["belegstellen"]
    assert result["unresolved_quotes"][0]["reason"] == "empty_or_unknown_loc_span"


def test_italic_opening_quote_is_not_part_of_tibetan_example() -> None:
    text = "ka „translation“ (Source 1)"
    article = _example_article([_line(text, [(0, 4, "italic"), (4, len(text), "regular")])])
    result = extract(article)
    assert result["tibetan_examples"][0]["text"] == "ka"
    validate(article, result)


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


def test_gloss_can_end_with_exact_compare_reference() -> None:
    lines = [_line("pf. zu ↑sñog.།"), _line("1. folgen, vgl. ↓bsñegs.")]
    divisions = [{"kind": "unsegmented", "label": "", "start_line_index": 0,
                  "end_line_index_exclusive": 1},
                 {"kind": "numbered_sense", "label": "1", "start_line_index": 1,
                  "end_line_index_exclusive": 2}]
    assert [item["text"] for item in extract(_article(lines, divisions))["definitions"]] == [
        "folgen, vgl. ↓bsñegs."]
    assert extract(_article([_line("vgl. ↓bsñegs.")]))["definitions"] == []


def test_inflection_preamble_is_not_a_gloss_and_multiword_reference_is() -> None:
    lines = [_line("pf., vgl. ↓gñul.།"),
             _line("1. umherwandern; vgl. ↓myul myul."),
             _line("2. verputzen.")]
    divisions = [{"kind": "unsegmented", "label": "", "start_line_index": 0,
                  "end_line_index_exclusive": 1},
                 {"kind": "numbered_sense", "label": "1", "start_line_index": 1,
                  "end_line_index_exclusive": 2},
                 {"kind": "numbered_sense", "label": "2", "start_line_index": 2,
                  "end_line_index_exclusive": 3}]
    result = extract(_article(lines, divisions))
    assert [item["text"] for item in result["definitions"]] == [
        "umherwandern; vgl. ↓myul myul.", "verputzen."]
    validate(_article(lines, divisions), result)


def test_reference_only_line_continues_a_semicolon_terminated_gloss() -> None:
    lines = [_line("1. Intrige; khon ~ das Schüren von Haß;"),
             _line("vgl. ↑’khon gcugs.")]
    divisions = [{"kind": "numbered_sense", "label": "1", "start_line_index": 0,
                  "end_line_index_exclusive": 2}]
    result = extract(_article(lines, divisions))
    assert result["definitions"][0]["text"] == (
        "Intrige; khon ~ das Schüren von Haß;\nvgl. ↑’khon gcugs.")
    validate(_article(lines, divisions), result)


def test_hyphenated_german_gloss_continues_into_inline_references() -> None:
    lines = [_line("Bez. für Schatztexte beson-"),
             _line("ders der rÑiṅ-ma-pa, im Unter-"),
             _line("schied zu ↑bka’ ma; vgl. ↑bka’ gter.")]
    result = extract(_article(lines))
    assert [item["text"] for item in result["definitions"]] == [
        "Bez. für Schatztexte beson-\n"
        "ders der rÑiṅ-ma-pa, im Unter-\n"
        "schied zu ↑bka’ ma; vgl. ↑bka’ gter."]
    validate(_article(lines), result)


def test_sanskrit_title_wrapped_after_hyphen_is_not_truncated() -> None:
    first = "3. ein buddh. Text, skt. Mahābalamahā-"
    second = "yānasūtra (Toh 757)."
    lines = [_line(first, [(0, 25, "regular"), (25, len(first), "italic")]),
             _line(second, [(0, 9, "italic"), (9, len(second), "regular")])]
    divisions = [{"kind": "numbered_sense", "label": "3", "start_line_index": 0,
                  "end_line_index_exclusive": 2}]
    result = extract(_article(lines, divisions))
    assert result["definitions"][0]["text"] == (
        "ein buddh. Text, skt. Mahābalamahā-\nyānasūtra (Toh 757).")
    validate(_article(lines, divisions), result)


def test_variant_preamble_is_not_a_definition_but_numbered_sense_is() -> None:
    first = "auch thugs yi dam."
    lines = [_line(first, [(0, 5, "regular"), (5, len(first), "italic")]),
             _line("1. Gelöbnis.")]
    divisions = [{"kind": "unsegmented", "label": "", "start_line_index": 0,
                  "end_line_index_exclusive": 1},
                 {"kind": "numbered_sense", "label": "1", "start_line_index": 1,
                  "end_line_index_exclusive": 2}]
    assert [item["text"] for item in extract(_article(lines, divisions))["definitions"]] == ["Gelöbnis."]


def test_same_line_variant_followed_by_german_gloss() -> None:
    first = "auch thig gu Schnur, Seil, Faden;"
    lines = [_line(first, [(0, 5, "regular"), (5, 12, "italic"),
                           (12, len(first), "regular")])]
    definition = extract(_article(lines))["definitions"][0]
    assert definition["text"] == "Schnur, Seil, Faden;"
    assert first[definition["visual_start"]:definition["visual_end"]] == definition["text"]


def test_regular_quoted_division_opening_is_gloss_not_unresolved_example() -> None:
    first = "1. „fünfgesichtig“, Löwe."
    start = first.index("„")
    article = _article([_line(first)], divisions=[{
        "kind": "numbered_sense", "label": "1", "start_line_index": 0,
        "end_line_index_exclusive": 1}], candidates={
        "german_quotes": [{"visual_start": start,
                           "visual_end": start + len("„fünfgesichtig“"),
                           "division_index": 0, "start_line_index": 0}],
        "parenthetical_citations": [], "adjacent_quote_citation_pairs": []})
    result = extract(article)
    assert [item["text"] for item in result["definitions"]] == ["„fünfgesichtig“"]
    assert result["definitions"][0]["status"] == "unverified_quoted_gloss_candidate"
    assert result["unresolved_quotes"] == []
    assert result["quote_dispositions"][0]["kind"] == "quoted_definition_candidate"
    validate(article, result)


def test_regular_quote_after_tibetan_and_citation_stays_out_of_gloss_rule() -> None:
    first = "~ kha la „mouth“ (Siddh 4)."
    quote_start = first.index("„")
    citation_start = first.index("(Siddh")
    article = _article([_line(first)], candidates={
        "german_quotes": [{"visual_start": quote_start,
                           "visual_end": quote_start + len("„mouth“"),
                           "division_index": 0, "start_line_index": 0}],
        "parenthetical_citations": [{"visual_start": citation_start,
                                      "visual_end": citation_start + len("(Siddh 4)"),
                                      "division_index": 0}],
        "adjacent_quote_citation_pairs": [{"quote_index": 0, "citation_index": 0}]})
    result = extract(article)
    assert result["definitions"] == []
    assert result["quote_dispositions"][0]["kind"] == "unresolved"


def test_italic_run_may_include_only_opening_german_quote() -> None:
    line = "~ kha la „mouth“ (Siddh 4)."
    quote_start = line.index("„")
    citation_start = line.index("(Siddh")
    article = _article([_line(line, [(0, quote_start + 1, "italic"),
                                    (quote_start + 1, len(line), "regular")])],
                       candidates={
        "german_quotes": [{"visual_start": quote_start,
                           "visual_end": quote_start + len("„mouth“"),
                           "division_index": 0, "start_line_index": 0}],
        "parenthetical_citations": [{"visual_start": citation_start,
                                      "visual_end": citation_start + len("(Siddh 4)"),
                                      "division_index": 0}],
        "adjacent_quote_citation_pairs": [{"quote_index": 0, "citation_index": 0}]})
    result = extract(article)
    assert [item["text"] for item in result["tibetan_examples"]] == ["~ kha la"]
    assert result["unresolved_quotes"] == []
    assert result["quote_dispositions"][0]["kind"] == "belegstelle_candidate"
    validate(article, result)


def test_variant_without_same_line_gloss_is_not_promoted() -> None:
    first = "auch thig gu"
    lines = [_line(first, [(0, 5, "regular"), (5, len(first), "italic")])]
    assert extract(_article(lines))["definitions"] == []


def test_quoted_variant_gloss_is_not_an_uncited_belegstelle() -> None:
    line = "auch kha chiṅ „eine Variante“"
    italic_start = line.index("kha chiṅ")
    quote_start = line.index("„")
    article = _article([_line(line, [(0, italic_start, "regular"),
                                  (italic_start, quote_start - 1, "italic"),
                                  (quote_start - 1, len(line), "regular")])], candidates={
        "german_quotes": [{"visual_start": quote_start, "visual_end": len(line),
                            "division_index": 0, "start_line_index": 0}],
        "parenthetical_citations": [], "adjacent_quote_citation_pairs": []})
    result = extract(article)
    assert result["tibetan_examples"] == []
    assert result["unresolved_quotes"] == []
    assert result["variant_glosses"][0]["loc_text"] == "kha chiṅ"
    assert result["variant_glosses"][0]["cue"] == "auch"
    assert result["quote_dispositions"][0]["kind"] == "variant_gloss_candidate"
    validate(article, result)


def test_quoted_uncited_example_without_explicit_variant_cue_remains_unresolved() -> None:
    line = "~ bcad pa „ein Beispiel“"
    quote_start = line.index("„")
    article = _article([_line(line, [(0, quote_start - 1, "italic"),
                                  (quote_start - 1, len(line), "regular")])], candidates={
        "german_quotes": [{"visual_start": quote_start, "visual_end": len(line),
                            "division_index": 0, "start_line_index": 0}],
        "parenthetical_citations": [], "adjacent_quote_citation_pairs": []})
    result = extract(article)
    assert result["variant_glosses"] == []
    assert result["unresolved_quotes"] == [{"quote_index": 0, "reason": "no_adjacent_citation"}]


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


def test_parenthetical_correction_preserves_complete_example() -> None:
    first = "~ kha lhor blta (r. lta) ba źig na phug ro gcig"
    second = "„translation“ (Siddh 11,2)."
    lines = [_line(first, [(0, 16, "italic"), (16, 20, "regular"),
                           (20, 23, "italic"), (23, 24, "regular"),
                           (24, len(first), "italic")]), _line(second)]
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
    assert [item["text"] for item in result["tibetan_examples"]] == [first]
    assert result["belegstellen"][0]["text"] == first + "\n" + second[:-1]
    assert result["unresolved_quotes"] == []
    correction = result["correction_apparatus"][0]
    assert (correction["literal_text"], correction["target_text"],
            correction["proposed_reading"]) == ("(r. lta)", "blta", "lta")
    assert correction["status"] == "anchored_printed_proposal"
    assert result["belegstellen"][0]["correction_indices"] == [0]
    assert result["belegstellen"][0]["translation_index"] == 0
    assert result["citations"][0]["text"] == "(Siddh 11,2)"
    assert result["tibetan_examples"][0]["text"] == first


def test_wrapped_parenthetical_correction_preserves_complete_example() -> None:
    first = "~ phuṅ (r."
    second = "phyugs) po ’grub mi ’gyur (metr.)"
    lines = [_line(first, [(0, 7, "italic"), (7, len(first), "regular")]),
             _line(second, [(0, 6, "italic"), (6, 8, "regular"),
                            (8, 26, "italic"), (26, len(second), "regular")]),
             _line("„translation“ (Pd-K 134c).")]
    visual = "\n".join(line["text"] for line in lines)
    quote_start = visual.index("„translation“")
    cite_start = visual.index("(Pd-K 134c)")
    candidates = {"german_quotes": [{"visual_start": quote_start,
                   "visual_end": quote_start + len("„translation“"),
                   "division_index": 0, "start_line_index": 2}],
                  "parenthetical_citations": [{"visual_start": cite_start,
                   "visual_end": cite_start + len("(Pd-K 134c)"),
                   "division_index": 0}],
                  "adjacent_quote_citation_pairs": [{"quote_index": 0,
                   "citation_index": 0}]}
    result = extract(_article(lines, candidates=candidates))
    assert result["tibetan_examples"][0]["text"] == first + "\n" + second[:26].rstrip()
    assert result["belegstellen"][0]["text"] == first + "\n" + second + "\n„translation“ (Pd-K 134c)"
    assert result["unresolved_quotes"] == []
    assert result["correction_apparatus"][0]["target_text"] == "phuṅ"
    assert result["correction_apparatus"][0]["proposed_reading"] == "phyugs"


@pytest.mark.parametrize("lines,spans,expected", [
    (["~ mdon (r. ’don) „translation“ (Source 1)."],
     [[(0, 6, "italic"), (6, 11, "regular"), (11, 15, "italic"),
       (15, 40, "regular")]], "~ mdon (r. ’don)"),
    (["~ rtsal (r. stsal)", "(metr.) „translation“ (Source 1)."],
     [[(0, 7, "italic"), (7, 12, "regular"), (12, 17, "italic"),
       (17, 18, "regular")], [(0, 33, "regular")]],
     "~ rtsal (r. stsal)"),
    (["~ mdon (r.ka) „translation“ (Source 1)."],
     [[(0, 6, "italic"), (6, 10, "regular"), (10, 12, "italic"),
       (12, len("~ mdon (r.ka) „translation“ (Source 1)."), "regular")]],
     "~ mdon (r.ka)"),
])
def test_final_printed_correction_is_part_of_complete_example(
        lines: list[str], spans: list[list[tuple[int, int, str]]],
        expected: str) -> None:
    source_lines = [_line(line, line_spans)
                    for line, line_spans in zip(lines, spans)]
    visual = "\n".join(lines)
    quote_start = visual.index("„translation“")
    cite_start = visual.index("(Source 1)")
    quote_line = next(i for i, line in enumerate(lines) if "„translation“" in line)
    article = _article(source_lines, candidates={
        "german_quotes": [{"visual_start": quote_start,
                           "visual_end": quote_start + len("„translation“"),
                           "division_index": 0, "start_line_index": quote_line}],
        "parenthetical_citations": [{"visual_start": cite_start,
                                     "visual_end": cite_start + len("(Source 1)"),
                                     "division_index": 0}],
        "adjacent_quote_citation_pairs": [{"quote_index": 0,
                                            "citation_index": 0}]})
    result = extract(article)
    assert result["unresolved_quotes"] == []
    assert result["tibetan_examples"][0]["text"] == expected
    assert result["belegstellen"][0]["correction_indices"] == [0]
    assert result["correction_apparatus"][0]["example_index"] == 0
    assert result["correction_apparatus"][0]["interpretation"] == "printed_apparatus_not_applied"


@pytest.mark.parametrize("barrier", ["unrelated prose", "other (r. ’don)", "(r. ’don) extra"])
def test_printed_correction_rule_rejects_other_intervening_text(barrier: str) -> None:
    first = "~ mdon " + barrier + " „translation“"
    line = _line(first, [(0, 6, "italic"), (6, len(first), "regular")])
    result = extract(_article([line], candidates={
        "german_quotes": [{"visual_start": first.index("„translation“"),
                           "visual_end": len(first), "division_index": 0,
                           "start_line_index": 0}],
        "parenthetical_citations": [], "adjacent_quote_citation_pairs": []}))
    assert result["belegstellen"] == []
    assert result["tibetan_examples"] == []
    assert result["unresolved_quotes"][0]["reason"] == "no_adjacent_italic_loc_span"


@pytest.mark.parametrize("barrier", ["different_page", "unknown_glyph"])
def test_printed_correction_rule_rejects_unsafe_source_boundary(barrier: str) -> None:
    first = "~ mdon (r. ’don)"
    second = "„translation“ (Source 1)."
    lines = [_line(first, [(0, 6, "italic"), (6, len(first), "regular")]),
             _line(second)]
    if barrier == "different_page":
        lines[1]["page_id"] = "different-source-page"
    else:
        lines[0]["unknown_glyphs"] = [{"cid": 999}]
    visual = first + "\n" + second
    quote_start = visual.index("„translation“")
    result = extract(_article(lines, candidates={
        "german_quotes": [{"visual_start": quote_start,
                           "visual_end": quote_start + len("„translation“"),
                           "division_index": 0, "start_line_index": 1}],
        "parenthetical_citations": [], "adjacent_quote_citation_pairs": []}))
    assert result["belegstellen"] == []
    assert result["tibetan_examples"] == []
    assert result["unresolved_quotes"][0]["reason"] == "no_adjacent_italic_loc_span"


def test_correction_without_italic_target_stays_unresolved() -> None:
    first = "mchu (r. sgros) ’gros"
    lines = [_line(first, [(0, len(first), "regular")]),
             _line("„translation“ (Source 1).")]
    visual = "\n".join(line["text"] for line in lines)
    quote_start = visual.index("„translation“")
    cite_start = visual.index("(Source 1)")
    article = _article(lines, candidates={"german_quotes": [{
        "visual_start": quote_start, "visual_end": quote_start + len("„translation“"),
        "division_index": 0, "start_line_index": 1}],
        "parenthetical_citations": [{"visual_start": cite_start,
        "visual_end": cite_start + len("(Source 1)"), "division_index": 0}],
        "adjacent_quote_citation_pairs": []})
    # The source apparatus is inventoried even though no Tibetan example is
    # admitted without an eligible italic source span.
    result = extract(article)
    assert result["tibetan_examples"] == []
    assert result["correction_apparatus"][0]["status"] == "unresolved_target"
    assert result["correction_apparatus"][0]["example_index"] is None


def test_multiword_printed_proposal_does_not_guess_one_token_target() -> None:
    first = "ka ca (r. skad cha) sñan pa"
    result = extract(_article([_line(first, [(0, 6, "italic"),
                                             (6, 20, "regular"),
                                             (20, len(first), "italic")])]))
    correction = result["correction_apparatus"][0]
    assert correction["proposed_reading"] == "skad cha"
    assert correction["status"] == "multiword_target_scope_unresolved"
    assert "target_text" not in correction
    assert "target_span" not in correction


def test_source_replay_validator_rejects_mutated_fields_and_links() -> None:
    article = _article([_line("Bedeutung.")])
    result = extract(article)
    result["definitions"][0]["text"] = "Berichtigung."
    with pytest.raises(ValueError, match="source span does not replay"):
        validate(article, result)
    result = extract(article)
    result["divisions"][0]["definition_indices"] = []
    with pytest.raises(ValueError, match="division link mismatch"):
        validate(article, result)
    result = extract(article)
    result["article_id"] = "other-article"
    with pytest.raises(ValueError, match="article source identity mismatch"):
        validate(article, result)


def test_nested_parenthetical_correction_keeps_complete_example() -> None:
    first = "~ koṅ co (Gl. mun śen (r. śeṅ)) bźes pas "
    lines = [_line(first, [(0, 21, "italic"), (21, 25, "regular"),
                           (25, 29, "italic"), (29, 31, "regular"),
                           (31, len(first), "italic")]),
             _line("„translation“ (Nel 7b5).")]
    visual = "\n".join(line["text"] for line in lines)
    quote_start = visual.index("„translation“")
    cite_start = visual.index("(Nel 7b5)")
    candidates = {"german_quotes": [{"visual_start": quote_start,
                   "visual_end": quote_start + len("„translation“"),
                   "division_index": 0, "start_line_index": 1}],
                  "parenthetical_citations": [{"visual_start": cite_start,
                   "visual_end": cite_start + len("(Nel 7b5)"),
                   "division_index": 0}],
                  "adjacent_quote_citation_pairs": [{"quote_index": 0,
                   "citation_index": 0}]}
    result = extract(_article(lines, candidates=candidates))
    assert result["tibetan_examples"][0]["text"] == first.strip()
    assert len(result["belegstellen"]) == 1
    assert result["unresolved_quotes"] == []


def test_compact_mixed_style_correction_joins_the_complete_loc_example() -> None:
    first = "dṅos rigs ~ yod med la ma ltos pa’i mi ño"
    second = "dka’ (r.ka) med ’bam tshoṅ "
    correction_start = second.index("(r.ka)")
    proposal_start = second.index("ka)")
    lines = [_line(first, [(0, len(first), "italic")]),
             _line(second, [(0, correction_start, "italic"),
                            (correction_start, proposal_start, "regular"),
                            (proposal_start, proposal_start + 2, "italic"),
                            (proposal_start + 2, proposal_start + 3, "regular"),
                            (proposal_start + 3, len(second), "italic")]),
             _line("„translation“ (Source 12).")]
    visual = "\n".join(line["text"] for line in lines)
    quote_start = visual.index("„translation“")
    cite_start = visual.index("(Source 12)")
    article = _article(lines, candidates={
        "german_quotes": [{"visual_start": quote_start,
                           "visual_end": quote_start + len("„translation“"),
                           "division_index": 0, "start_line_index": 2}],
        "parenthetical_citations": [{"visual_start": cite_start,
                                      "visual_end": cite_start + len("(Source 12)"),
                                      "division_index": 0}],
        "adjacent_quote_citation_pairs": [{"quote_index": 0,
                                           "citation_index": 0}]})
    result = extract(article)
    assert result["unresolved_quotes"] == []
    assert result["tibetan_examples"][0]["text"] == first + "\n" + second.rstrip()
    assert result["belegstellen"][0]["text"] == (
        first + "\n" + second + "\n„translation“ (Source 12)")
    correction = result["correction_apparatus"][0]
    assert correction["proposed_reading"] == "ka"
    assert correction["target_text"] == "dka’"
    validate(article, result)


@pytest.mark.parametrize("first,spans", [
    ("~ dkar po ... bzuṅ ", [(0, 9, "italic"), (9, 14, "regular"),
                             (14, 19, "italic")]),
    ("~ bźi ⟨b⟩sgril gyi sgrog rgyab la ",
     [(0, 6, "italic"), (6, 9, "regular"), (9, 35, "italic")]),
])
def test_literal_italic_interruptions_preserve_whole_example(first: str,
                                                               spans: list[tuple[int, int, str]]) -> None:
    lines = [_line(first, spans), _line("„translation“ (Source 12).")]
    visual = "\n".join(line["text"] for line in lines)
    quote_start = visual.index("„translation“")
    cite_start = visual.index("(Source 12)")
    candidates = {"german_quotes": [{"visual_start": quote_start,
                   "visual_end": quote_start + len("„translation“"),
                   "division_index": 0, "start_line_index": 1}],
                  "parenthetical_citations": [{"visual_start": cite_start,
                   "visual_end": cite_start + len("(Source 12)"),
                   "division_index": 0}],
                  "adjacent_quote_citation_pairs": [{"quote_index": 0,
                   "citation_index": 0}]}
    result = extract(_article(lines, candidates=candidates))
    assert result["tibetan_examples"][0]["text"] == first.rstrip()
    assert result["belegstellen"][0]["text"] == first + "\n„translation“ (Source 12)"


@pytest.mark.parametrize("line_break", [False, True])
def test_roman_lemma_placeholder_after_italic_loc_is_part_of_example(
        line_break: bool) -> None:
    first = "bod "
    rest = "~ (metr.) „translation“ (Source 12)"
    lines = ([_line(first, [(0, len(first), "italic")]), _line(rest)]
             if line_break else [_line(first + rest, [(0, len(first), "italic"),
                                                    (len(first), len(first + rest), "regular")])])
    visual = "\n".join(line["text"] for line in lines)
    quote_start = visual.index("„translation“")
    cite_start = visual.index("(Source 12)")
    result = extract(_article(lines, candidates={
        "german_quotes": [{"visual_start": quote_start,
                           "visual_end": quote_start + len("„translation“"),
                           "division_index": 0, "start_line_index": len(lines) - 1}],
        "parenthetical_citations": [{"visual_start": cite_start,
                                      "visual_end": cite_start + len("(Source 12)"),
                                      "division_index": 0}],
        "adjacent_quote_citation_pairs": [{"quote_index": 0,
                                           "citation_index": 0}]}))
    assert result["unresolved_quotes"] == []
    assert result["tibetan_examples"][0]["text"] == ("bod \n~ (metr.)" if line_break
                                                     else "bod ~ (metr.)")
    assert len(result["belegstellen"]) == 1


def test_unrelated_mixed_style_gap_is_not_merged_into_example() -> None:
    first = "other (editorial) Tibetan „translation“"
    lines = [_line(first, [(0, 5, "italic"), (5, 17, "regular"),
                           (17, 25, "italic"), (25, len(first), "regular")])]
    quote_start = first.index("„translation“")
    candidates = {"german_quotes": [{"visual_start": quote_start,
                   "visual_end": len(first), "division_index": 0,
                   "start_line_index": 0}],
                  "parenthetical_citations": [],
                  "adjacent_quote_citation_pairs": []}
    result = extract(_article(lines, candidates=candidates))
    assert [item["text"] for item in result["tibetan_examples"]] == ["Tibetan"]


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
    assert [item["text"] for item in result["tibetan_examples"]] == ["sñags pa"]
    assert result["lexicographic_parallels"][0]["loc_text"] == "sñags"
    assert result["lexicographic_parallels"][0]["citation_index"] == 1
    assert len(result["belegstellen"]) == 1
    assert result["belegstellen"][0]["text"] == "sñags pa „translation“ (Siddh 11,2)"
    assert result["unresolved_quotes"] == []
    assert [item["kind"] for item in result["quote_dispositions"]] == [
        "belegstelle_candidate", "lexicographic_parallel_candidate"]


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
