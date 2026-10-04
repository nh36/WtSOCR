"""Small synthetic tests for positioned PDF structural parsing."""

from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from parse_badw_pdf_articles import _candidates, _structure, build, parse_article, reindex_article


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _run(index: int, text: str, x: float, y: float, font: str = "roman") -> dict:
    return {"run_index": index, "decoded_unicode": text, "font_id": font, "x": x, "y": y,
            "glyphs": [{"cid_hex": f"{ord(char):04x}", "unicode": char, "x": x + offset * 0.5,
                        "y": y, "unknown": False} for offset, char in enumerate(text)]}


def _fixture() -> tuple[dict, dict]:
    runs = [
        _run(0, "ཁ་།", 1, 10, "tibetan"),
        _run(1, "kha", 2, 10, "italic"),
        _run(2, "1", 1, 9), _run(3, "1", 1.027, 9.027),
        _run(4, ".", 1.5, 9), _run(5, " Mund „Mund“ (Siddh 11.2)", 2, 9),
        _run(6, "2. ↑kha dog als Zeichen", 1, 8),
    ]
    source_text = "".join(run["decoded_unicode"] for run in runs)
    page = {"page_id": "page-one", "visible_body_sha256": "a" * 64,
            "representative_fonts": [
                {"font_id": "tibetan", "family": "RabtenTibetan", "style": "regular"},
                {"font_id": "italic", "family": "TGaramond", "style": "italic"},
                {"font_id": "roman", "family": "TGaramond", "style": "regular"}],
            "positioned_page": {"positioned_text_runs": runs}}
    span = {"canonical_object": "volume_2/pages/page-one.json.gz", "page_id": "page-one",
            "visible_body_sha256": "a" * 64, "representative_pdf_url": "https://example.test/pdf/kha",
            "representative_pdf_sha256": "b" * 64, "source_text_sha256": _hash(source_text),
            "source_faithful_text": source_text, "run_start": 0, "run_end_exclusive": len(runs),
            "printed_page": 1}
    article = {"contract_version": "badw-pdf-article-witness-v1", "id": "badw:pdf:page-one:0",
               "volume": 2, "loc_headword": "kha", "tibetan_headword": "ཁ་།", "homonym": "",
               "ending_status": "bounded_by_next_heading", "source_faithful_text": source_text,
               "entry_start_source_span": {"tibetan_run_indices": [0], "loc_run_indices": [1],
                                           "homonym_run_indices": []}, "source_spans": [span]}
    return article, page


def test_numbered_senses_and_candidates_preserve_source() -> None:
    article, page = _fixture()
    parsed = parse_article(article, lambda _: page)
    assert parsed["loc_headword"] == "kha"
    assert parsed["tibetan_headword"] == "ཁ་།"
    assert [part["label"] for part in parsed["divisions"]] == ["1", "2"]
    assert parsed["visual_lines"][0]["text"] == "1. Mund „Mund“ (Siddh 11.2)"
    assert parsed["diagnostics"]["visual_overprint_impressions_removed"] == 1
    assert parsed["candidates"]["german_quotes"][0]["text"] == "Mund"
    assert parsed["candidates"]["parenthetical_citations"][0]["siglum_candidate"] == "Siddh"
    assert parsed["candidates"]["adjacent_quote_citation_pairs"] == [{
        "quote_index": 0, "citation_index": 0, "division_index": 0,
        "status": "typographic_candidate"}]
    assert parsed["divisions"][0]["start_line_index"] == 0
    assert parsed["divisions"][0]["end_line_index_exclusive"] == 1
    assert parsed["candidates"]["cross_references"][0]["target_label_candidate"] == "kha"
    assert parsed["source_objects"][0]["source_text_sha256"] == _hash(article["source_faithful_text"])
    assert parsed["source_faithful_text"] == article["source_faithful_text"]
    assert all("style_spans" in line for line in parsed["visual_lines"])
    assert parsed["visual_lines"][0]["style_spans"][0]["first_run_index"] == 2


def test_nonsequential_labels_are_not_promoted() -> None:
    article, page = _fixture()
    page["positioned_page"]["positioned_text_runs"][6] = _run(6, "4. continuation", 1, 8)
    text = "".join(run["decoded_unicode"] for run in page["positioned_page"]["positioned_text_runs"])
    article["source_spans"][0]["source_faithful_text"] = text
    article["source_spans"][0]["source_text_sha256"] = _hash(text)
    article["source_faithful_text"] = text
    parsed = parse_article(article, lambda _: page)
    assert [part["label"] for part in parsed["divisions"]] == ["1"]
    assert parsed["diagnostics"]["unpromoted_number_labels"] == 1
    assert "4. continuation" in parsed["divisions"][0]["text"]


def test_wrapped_locator_is_not_a_numbered_sense() -> None:
    lines = [_candidate_line("1. Bedeutung."),
             _candidate_line("1.3.34c); mtsho la ~ bab pa „Schnee“ (Pd-K 4).")]
    divisions, counts = _structure(lines)
    assert [division["label"] for division in divisions] == ["1"]
    assert counts["numbered_senses"] == 1
    assert "1.3.34c)" in divisions[0]["text"]


def test_offline_reindex_preserves_source_and_is_deterministic() -> None:
    article, page = _fixture()
    previous = parse_article(article, lambda _: page)
    previous["contract_version"] = "badw-pdf-structural-parser-v6"
    first = reindex_article(previous)
    assert first == reindex_article(previous)
    assert first["source_objects"] == previous["source_objects"]
    assert first["source_faithful_text"] == previous["source_faithful_text"]
    assert first["visual_lines"] == previous["visual_lines"]
    assert first["contract_version"] == "badw-pdf-structural-parser-v7"
    assert first['extraction_version'] == 'badw-source-components-v1'
    previous["source_faithful_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        reindex_article(previous)


def test_multiline_quote_and_citation_have_end_line_provenance() -> None:
    article, page = _fixture()
    runs = page["positioned_page"]["positioned_text_runs"]
    runs[5] = _run(5, " Mund „langer", 2, 9)
    runs[6] = _run(6, "Ausdruck“ (Siddh", 1, 8)
    runs.append(_run(7, " 11.2)", 1, 7))
    text = "".join(run["decoded_unicode"] for run in runs)
    article["source_spans"][0].update(source_faithful_text=text,
        source_text_sha256=_hash(text), run_end_exclusive=len(runs))
    article["source_faithful_text"] = text
    parsed = parse_article(article, lambda _: page)
    quote = parsed["candidates"]["german_quotes"][0]
    citation = parsed["candidates"]["parenthetical_citations"][0]
    assert quote["text"] == "langer\nAusdruck"
    assert (quote["start_line_index"], quote["end_line_index"]) == (0, 1)
    assert citation["text"] == "(Siddh\n 11.2)"
    assert (citation["start_line_index"], citation["end_line_index"]) == (1, 2)
    assert parsed["candidates"]["adjacent_quote_citation_pairs"][0]["division_index"] == 0


def test_quote_and_citation_are_not_paired_across_prose_or_divisions() -> None:
    article, page = _fixture()
    runs = page["positioned_page"]["positioned_text_runs"]
    runs[5] = _run(5, " Mund „Mund“ mit Kommentar (Siddh 11.2)", 2, 9)
    runs[6] = _run(6, "2. „Mund“", 1, 8)
    runs.append(_run(7, "(Siddh 11.3)", 1, 7))
    text = "".join(run["decoded_unicode"] for run in runs)
    article["source_spans"][0].update(source_faithful_text=text,
        source_text_sha256=_hash(text), run_end_exclusive=len(runs))
    article["source_faithful_text"] = text
    parsed = parse_article(article, lambda _: page)
    assert parsed["candidates"]["adjacent_quote_citation_pairs"] == [{
        "quote_index": 1, "citation_index": 1, "division_index": 1,
        "status": "typographic_candidate"}]


def _candidate_line(text: str, italic_start: int | None = None,
                    italic_end: int | None = None) -> dict:
    spans = [{"start": 0, "end": len(text), "style": "regular"}]
    if italic_start is not None and italic_end is not None:
        spans = []
        if italic_start:
            spans.append({"start": 0, "end": italic_start, "style": "regular"})
        spans.append({"start": italic_start, "end": italic_end, "style": "italic"})
        if italic_end < len(text):
            spans.append({"start": italic_end, "end": len(text), "style": "regular"})
    return {"text": text, "style_spans": spans, "span_index": 0, "page_id": "p",
            "printed_page": 1, "run_start": 0, "run_end_exclusive": 1}


def _candidate_division(count: int) -> list[dict]:
    return [{"start_line_index": 0, "end_line_index_exclusive": count}]


def test_regular_reference_fallback_skips_newline_and_homonym() -> None:
    lines = [_candidate_line('↑'), _candidate_line('3'), _candidate_line('ce')]
    ref = _candidates(lines, _candidate_division(3))['cross_references'][0]
    assert ref['target_label_candidate'] == '\n3\nce'
    assert ref['visual_end'] == len('↑\n3\nce')


def test_sanskrit_requires_explicit_label_not_italics():
    line = _candidate_line('Kontinuum (skt. saṃtāna) und Aggregat', 16, 23)
    other = _candidate_line('bod skad', 0, 8)
    result = _candidates([line, other], _candidate_division(2))
    field = result['sanskrit'][0]
    assert field['source_text'] == 'saṃtāna'
    assert line['text'][field['visual_start']:field['visual_end']] == 'saṃtāna'
    assert [s['source_text'] for s in result['unclassified_italic_spans']] == ['bod skad']
    assert result['language_diagnostics'] == []
    regular = _candidate_line('skt. saṃtāna')
    result = _candidates([regular], _candidate_division(1))
    assert result['sanskrit'] == []
    assert len(result['language_diagnostics']) == 1


def test_pdf_lexical_clauses_preserve_full_tail_and_nested_delimiters():
    text = 'Lex. ka (r.ka; r. kha) „Wort; Sache“ (Dagy); skt. śa (brDa).'
    lines = [_candidate_line(text)]
    divisions, _ = _structure(lines)
    candidates = _candidates(lines, divisions)
    block = candidates['lexical_blocks'][0]
    assert block['source_text'] == text
    assert block['extent_status'] == 'to_source_division_end'
    assert [c['source_text'] for c in block['clauses']] == [
        'ka (r.ka; r. kha) „Wort; Sache“ (Dagy)', 'skt. śa (brDa).']
    assert block['diagnostics'] == []
    assert block['clauses'][0]['german_quotation_candidates'][0]['source_text'] == '„Wort; Sache“'
    for clause in block['clauses']:
        assert text[clause['visual_start']:clause['visual_end']] == clause['source_text']
        assert clause['status'] == 'unassociated_source_clause'


def test_empty_pdf_lex_label_remains_a_source_block():
    lines = [_candidate_line('Lex.')]
    divisions, _ = _structure(lines)
    block = _candidates(lines, divisions)['lexical_blocks'][0]
    assert block['source_text'] == 'Lex.'
    assert block['clauses'] == []


def test_v7_offline_reindex_retains_source_and_adds_language_candidates():
    article, page = _fixture()
    previous = parse_article(article, lambda _: page)
    previous['contract_version'] = 'badw-pdf-structural-parser-v7'
    result = reindex_article(previous)
    assert result['contract_version'] == 'badw-pdf-structural-parser-v7'
    assert result['extraction_version'] == 'badw-source-components-v1'
    assert result['visual_lines'] == previous['visual_lines']
    assert result['source_objects'] == previous['source_objects']
    assert 'unclassified_italic_spans' in result['candidates']


def test_multiword_italic_reference_uses_typographic_boundary() -> None:
    line = _candidate_line("vgl. ↑’khon gcugs. anschliessend", 6, 17)
    candidate = _candidates([line], _candidate_division(1))["cross_references"][0]
    assert candidate["target_label_candidate"] == "’khon gcugs"
    assert (candidate["visual_start"], candidate["visual_end"]) == (5, 17)
    assert line["text"][candidate["visual_start"]:candidate["visual_end"]] == "↑’khon gcugs"


def test_italic_reference_continues_over_line_without_swallowing_punctuation() -> None:
    lines = [_candidate_line("vgl. ↓thog tu", 6, 13),
             _candidate_line("khel, danach", 0, 4)]
    lines[0]["style_spans"][1]["font_id"] = "same-font"
    lines[1]["style_spans"][0]["font_id"] = "same-font"
    candidate = _candidates(lines, _candidate_division(2))["cross_references"][0]
    assert candidate["target_label_candidate"] == "thog tu\nkhel"
    assert candidate["end_line_index"] == 1


def test_terminal_period_stops_italic_reference_before_next_example() -> None:
    lines = [_candidate_line("vgl. ↓rin po che sna bdun.", 6, 26),
             _candidate_line("~ mgon med zas sbyin", 0, 21)]
    lines[0]["style_spans"][1]["font_id"] = "same-font"
    lines[1]["style_spans"][0]["font_id"] = "same-font"
    candidate = _candidates(lines, _candidate_division(2))["cross_references"][0]
    assert candidate["target_label_candidate"] == "rin po che sna bdun"
    assert candidate["end_line_index"] == 0


def test_italic_reference_does_not_cross_font_change() -> None:
    lines = [_candidate_line("vgl. ↓thog tu", 6, 13),
             _candidate_line("khel, danach", 0, 4)]
    lines[0]["style_spans"][1]["font_id"] = "first-font"
    lines[1]["style_spans"][0]["font_id"] = "other-font"
    candidate = _candidates(lines, _candidate_division(2))["cross_references"][0]
    assert candidate["target_label_candidate"] == "thog tu"


def test_italic_terminal_period_is_not_part_of_reference_target() -> None:
    line = _candidate_line("↑ñin. །", 1, 5)
    candidate = _candidates([line], _candidate_division(1))["cross_references"][0]
    assert candidate["target_label_candidate"] == "ñin"


def test_reference_with_separate_homonym_line_preserves_exact_span() -> None:
    lines = [_candidate_line("pf. zu ↓"), _candidate_line("1"), _candidate_line("’chos.།", 0, 5)]
    candidate = _candidates(lines, _candidate_division(3))["cross_references"][0]
    assert candidate["target_label_candidate"] == "\n1\n’chos"
    assert (candidate["start_line_index"], candidate["end_line_index"]) == (0, 2)


def test_comma_reference_list_preserves_second_target_and_homonym() -> None:
    lines = [_candidate_line('↓tal la, ', 1, 7), _candidate_line('2'),
             _candidate_line('tal tsam.།', 0, 8)]
    for line in lines:
        for span in line['style_spans']:
            if span['style'] == 'italic':
                span['font_id'] = 'same-font'
    ref = _candidates(lines, _candidate_division(3))['cross_references'][0]
    assert ref['target_label_candidate'] == 'tal la, \n2\ntal tsam'
    assert [t['source_text'] for t in ref['target_candidates']] == [
        'tal la', '2\ntal tsam']


def test_comma_reference_list_does_not_cross_font_page_or_division() -> None:
    for barrier in ('font', 'page', 'division', 'regular'):
        lines = [_candidate_line('↓ka, ', 1, 3), _candidate_line('kha', 0, 3)]
        lines[0]['style_spans'][1]['font_id'] = 'first'
        lines[1]['style_spans'][0]['font_id'] = 'first'
        divisions = _candidate_division(2)
        if barrier == 'font':
            lines[1]['style_spans'][0]['font_id'] = 'second'
        elif barrier == 'page':
            lines[1]['page_id'] = 'other'
        elif barrier == 'division':
            divisions = [{'start_line_index': 0, 'end_line_index_exclusive': 1},
                         {'start_line_index': 1, 'end_line_index_exclusive': 2}]
        else:
            lines[1]['style_spans'][0]['style'] = 'regular'
        ref = _candidates(lines, divisions)['cross_references'][0]
        assert ref['target_label_candidate'] == 'ka'
        assert len(ref['target_candidates']) == 1


def test_arrow_inside_italic_span_and_unstyled_fallback() -> None:
    lines = [_candidate_line("vgl. ↑khyim 2.", 5, 11),
             _candidate_line("↑kha dog als Zeichen")]
    candidates = _candidates(lines, _candidate_division(2))["cross_references"]
    assert [item["target_label_candidate"] for item in candidates] == ["khyim", "kha"]


def test_locatorless_citation_whitelist_does_not_promote_prose() -> None:
    line = _candidate_line("(brDa) (Dagy) (TTC) (vgl. das) (Andere) (TTC?) (Mil 74,4)")
    citations = _candidates([line], _candidate_division(1))["parenthetical_citations"]
    assert [item["siglum_candidate"] for item in citations] == [
        "brDa", "Dagy", "TTC", "Mil"]


def test_qualified_locatorless_and_reviewed_mixed_case_siglum() -> None:
    lines = [_candidate_line("(brDa, ähnl. Dagy) (gZer 563,4)"),
             _candidate_line("(brDa,\nähnl. Dagy) (gZer?)")]
    citations = _candidates(lines, _candidate_division(2))["parenthetical_citations"]
    assert [(item["text"], item["siglum_candidate"]) for item in citations] == [
        ("(brDa, ähnl. Dagy)", "brDa"), ("(gZer 563,4)", "gZer"),
        ("(brDa,\nähnl. Dagy)", "brDa")]


def test_reviewed_source_forms_exclude_correction_and_prose() -> None:
    line = _candidate_line(
        "(Bca Kolophon) (Pś Kolophon) (PT1083 Siegelabdruck) "
        "(ChFr67) (Ctr14) (PW) (SWTF) (r. źi) (Kolophon) (vergleichbar)")
    citations = _candidates([line], _candidate_division(1))["parenthetical_citations"]
    assert [item["siglum_candidate"] for item in citations] == [
        "Bca", "Pś", "PT1083", "ChFr67", "Ctr14", "PW", "SWTF"]


def test_exact_reviewed_pdf_citations_preserve_questioned_siglum() -> None:
    line = _candidate_line(
        "„gloss“ (Vḍk2? 362,6) (KanL Kol.) (Siddh Kol.) "
        "(M.I.vi.2a b2) (BHSD) (Vḍk2? prose) (KanL Kolophon) "
        "(r.ka) (r. ka)")
    candidates = _candidates([line], _candidate_division(1))
    citations = candidates["parenthetical_citations"]
    assert [(item["text"], item["siglum_candidate"]) for item in citations] == [
        ("(Vḍk2? 362,6)", "Vḍk2?"), ("(KanL Kol.)", "KanL"),
        ("(Siddh Kol.)", "Siddh"), ("(M.I.vi.2a b2)", "M.I"),
        ("(BHSD)", "BHSD")]
    assert candidates["adjacent_quote_citation_pairs"] == [{
        "quote_index": 0, "citation_index": 0, "division_index": 0,
        "status": "typographic_candidate"}]


def test_correctly_decoded_vdk_colon_is_a_citation_without_changing_text() -> None:
    line = _candidate_line(
        "„gloss“ (Vḍk2: 362,6) (Vḍk2: prose) (r. ka) (r.ka)")
    candidates = _candidates([line], _candidate_division(1))
    assert [(item["text"], item["siglum_candidate"])
            for item in candidates["parenthetical_citations"]] == [
        ("(Vḍk2: 362,6)", "Vḍk2")]
    assert len(candidates["adjacent_quote_citation_pairs"]) == 1


def test_md_zod_g_wrapped_locator_is_citation_not_arbitrary_parenthesis() -> None:
    lines = [_candidate_line("„Bedeutung“ (mDzodG"), _candidate_line("64,3). (ordinary prose)")]
    citations = _candidates(lines, _candidate_division(2))["parenthetical_citations"]
    assert [(item["text"], item["siglum_candidate"]) for item in citations] == [
        ("(mDzodG\n64,3)", "mDzodG")]


def test_balanced_nested_and_loc_sigla_are_source_candidates_only() -> None:
    line = _candidate_line(
        "(K841(2) 204b2) (’Dzam 21,22) (gZi-Sn 92,37) "
        "(sBa 62,14) (1PL 19,4) (in Mvy 226,1) "
        "(r. preṣitaḥ „ausgesandt“!) (zw.) (ordinary prose 12)")
    citations = _candidates([line], _candidate_division(1))["parenthetical_citations"]
    assert [(item["text"], item["siglum_candidate"]) for item in citations] == [
        ("(K841(2) 204b2)", "K841"), ("(’Dzam 21,22)", "’Dzam"),
        ("(gZi-Sn 92,37)", "gZi-Sn"), ("(sBa 62,14)", "sBa"),
        ("(1PL 19,4)", "1PL"), ("(in Mvy 226,1)", "Mvy")]


def test_slash_locator_and_numeric_dates_are_distinguished() -> None:
    lines = [_candidate_line("„erhalten“ (MTH3/5/26 2) (1711-1799)"),
             _candidate_line("„aufbewahrt“ (MTH3/\n5/30 b10)")]
    citations = _candidates(lines, _candidate_division(2))["parenthetical_citations"]
    assert [(item["text"], item["siglum_candidate"]) for item in citations] == [
        ("(MTH3/5/26 2)", "MTH3"), ("(MTH3/\n5/30 b10)", "MTH3")]


def test_source_mismatch_fails_closed() -> None:
    article, page = _fixture()
    article["source_spans"][0]["source_text_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source text mismatch"):
        parse_article(article, lambda _: page)


def test_glyph_run_unicode_mismatch_fails_closed() -> None:
    article, page = _fixture()
    page["positioned_page"]["positioned_text_runs"][5]["glyphs"][0]["unicode"] = "X"
    with pytest.raises(ValueError, match="glyph/run Unicode mismatch"):
        parse_article(article, lambda _: page)


def test_article_aggregate_mismatch_fails_closed() -> None:
    article, page = _fixture()
    article["source_faithful_text"] += "not present in source"
    with pytest.raises(ValueError, match="article source text mismatch"):
        parse_article(article, lambda _: page)


def test_deterministic_offline_build(tmp_path: Path) -> None:
    article, page = _fixture()
    root = tmp_path / "canonical"
    page_path = root / article["source_spans"][0]["canonical_object"]
    page_path.parent.mkdir(parents=True)
    with gzip.open(page_path, "wt", encoding="utf-8") as handle:
        json.dump(page, handle, ensure_ascii=False)
    witness_path = tmp_path / "witnesses.jsonl.gz"
    with gzip.open(witness_path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(article, ensure_ascii=False) + "\n")
    first = build(witness_path, root, tmp_path / "first")
    second = build(witness_path, root, tmp_path / "second")
    assert first == second
    assert (tmp_path / "first/pdf_article_structure.jsonl.gz").read_bytes() == (
        tmp_path / "second/pdf_article_structure.jsonl.gz").read_bytes()
    assert first["counts"]["articles"] == 1
    with gzip.open(tmp_path / "first/pdf_article_structure.jsonl.gz", "rt", encoding="utf-8") as handle:
        parsed = json.loads(handle.readline())
    assert parsed["source_objects"][0]["canonical_object_sha256"] == sha256(page_path.read_bytes()).hexdigest()


def test_canonical_roots_must_not_conflict(tmp_path: Path) -> None:
    article, page = _fixture()
    witness_path = tmp_path / "witnesses.jsonl.gz"
    with gzip.open(witness_path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(article, ensure_ascii=False) + "\n")
    roots = [tmp_path / "first-root", tmp_path / "second-root"]
    for root in roots:
        path = root / article["source_spans"][0]["canonical_object"]
        path.parent.mkdir(parents=True)
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            json.dump(page, handle, ensure_ascii=False)
    success = build(witness_path, roots, tmp_path / "success")
    assert success["counts"]["articles"] == 1
    changed = dict(page)
    changed["unrelated_metadata"] = "different bytes"
    path = roots[1] / article["source_spans"][0]["canonical_object"]
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(changed, handle, ensure_ascii=False)
    with pytest.raises(ValueError, match="conflicting canonical page objects"):
        build(witness_path, roots, tmp_path / "failure")


def test_balanced_nested_quotations_preserve_literal_long_outer_span() -> None:
    from parse_badw_pdf_articles import quotation_spans
    text = '„' + 'Wort ' * 120 + '„innere Rede“ und ‚ein Wort‘“'
    quotes, diagnostics = quotation_spans(text)
    assert diagnostics == []
    assert len(quotes) == 1
    assert quotes[0]['visual_end'] == len(text)
    child = quotes[0]['children'][0]
    assert text[child['visual_start']:child['visual_end']] == '„innere Rede“'
    assert len(quotes[0]['children']) == 1


def test_unbalanced_and_repeated_quote_marks_are_not_silently_repaired() -> None:
    from parse_badw_pdf_articles import quotation_spans
    quotes, diagnostics = quotation_spans('„offen')
    assert quotes == []
    assert diagnostics[0]['kind'] == 'unclosed_opening_quote'
    quotes, diagnostics = quotation_spans('„Wort““')
    assert diagnostics == []
    assert quotes[0]['visual_end'] == len('„Wort““')
    assert quotes[0]['diagnostics'] == ['repeated_closing_quote']


def test_unclosed_outer_quote_preserves_independently_closed_later_quotes() -> None:
    from parse_badw_pdf_articles import quotation_spans
    text = '„unclosed translation. Lex. „lexical gloss“ (Dagy). 3. „later example“ (HMrg 51,3).'
    quotes, diagnostics = quotation_spans(text)
    assert [text[q['visual_start']:q['visual_end']] for q in quotes] == [
        '„lexical gloss“', '„later example“',
    ]
    assert diagnostics == [{'kind': 'unclosed_opening_quote', 'visual_start': 0, 'visual_end': len(text)}]


def test_exact_malformed_nested_quote_review_preserves_literal_and_rejects_stale():
    from hashlib import sha256
    from parse_badw_pdf_articles import reviewed_quotation_spans
    import pytest

    text = '„,ja!“ sagte er“'
    row = {"visual_sha256": sha256(text.encode()).hexdigest(),
           "visual_start": "0", "visual_end": str(len(text)),
           "quote_sha256": sha256(text.encode()).hexdigest(),
           "inner_start": "1", "inner_end": "6", "basis": "synthetic_visible_review"}
    quotes, diagnostics = reviewed_quotation_spans(text, "test", {"test": [row]})
    assert quotes[0]["visual_end"] == len(text)
    assert quotes[0]["children"][0]["visual_start"] == 1
    assert quotes[0]["children"][0]["text"] == "ja!"
    assert diagnostics[0]["review_basis"] == "synthetic_visible_review"
    other, _ = reviewed_quotation_spans(text, "other", {"test": [row]})
    assert other[0]["visual_end"] == 6
    with pytest.raises(ValueError, match="stale"):
        reviewed_quotation_spans(text + "!", "test", {"test": [row]})
