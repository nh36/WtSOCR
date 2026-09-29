"""Offline contract tests for the source-faithful nested PDF candidate layer."""
from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_badw_pdf_nested_candidates import build, project
from extract_badw_pdf_lexical_candidates import extract


def article(with_citation: bool = True) -> dict:
    first = "1. Bedeutung."
    second = "~ mdon (r. ’don) „Übersetzung“ (Quelle 1)."
    text = first + "\n" + second
    quote_start = text.index("„Übersetzung“")
    citation_start = text.index("(Quelle 1)")
    lines = []
    for line, spans in (
        (first, [(0, len(first), "regular")]),
        (second, [(0, 6, "italic"), (6, 11, "regular"),
                  (11, 15, "italic"), (15, len(second), "regular")]),
    ):
        lines.append({"text": line, "page_id": "page-1", "span_index": 0,
                      "printed_page": 17, "run_start": 0,
                      "run_end_exclusive": len(line), "unknown_glyphs": [],
                      "style_spans": [{"start": start, "end": end,
                                       "family": "TGaramond", "style": style}
                                      for start, end, style in spans]})
    citations = ([{"visual_start": citation_start,
                   "visual_end": citation_start + len("(Quelle 1)"),
                   "division_index": 0}] if with_citation else [])
    return {"contract_version": "badw-pdf-structural-parser-v5",
            "article_id": "badw:pdf:test", "volume": 2,
            "loc_headword": "sñags", "tibetan_headword": "སྔགས", "homonym": None,
            "source_objects": [],
            "source_faithful_sha256": sha256(text.encode()).hexdigest(),
            "visual_lines": lines,
            "divisions": [{"kind": "numbered_sense", "label": "1",
                           "start_line_index": 0, "end_line_index_exclusive": 2,
                           "text": text}],
            "candidates": {"german_quotes": [{"visual_start": quote_start,
                                              "visual_end": quote_start + len("„Übersetzung“"),
                                              "division_index": 0,
                                              "start_line_index": 1}],
                           "parenthetical_citations": citations,
                           "adjacent_quote_citation_pairs": (
                               [{"quote_index": 0, "citation_index": 0}]
                               if with_citation else [])}}


def test_nested_belegstelle_preserves_printed_correction_as_apparatus() -> None:
    source = article()
    row = project(source, extract(source))
    division = row["divisions"][0]
    assert division["kind"] == "sense_candidate"
    assert division["source_text"] == "1. Bedeutung.\n~ mdon (r. ’don) „Übersetzung“ (Quelle 1)."
    kinds = [item["kind"] for item in division["items"]]
    assert kinds == ["definition_candidate", "belegstelle_candidate"]
    beleg = division["items"][1]
    assert beleg["components"]["tibetan_examples"]["text"] == "~ mdon (r. ’don)"
    assert beleg["components"]["translations"]["text"] == "„Übersetzung“"
    assert beleg["components"]["citations"]["text"] == "(Quelle 1)"
    assert beleg["corrections"][0]["proposed_reading"] == "’don"
    assert beleg["corrections"][0]["interpretation"] == "printed_apparatus_not_applied"
    assert row["unassigned_source_candidates"] == []


def test_uncited_example_keeps_complete_tibetan_and_correction() -> None:
    source = article(with_citation=False)
    row = project(source, extract(source))
    item = next(item for item in row["divisions"][0]["items"]
                if item["kind"] == "uncited_example_candidate")
    assert item["components"]["tibetan_examples"]["text"] == "~ mdon (r. ’don)"
    assert item["corrections"][0]["proposed_reading"] == "’don"
    assert item["reason"] == "no_adjacent_citation"


def test_variant_gloss_is_separate_from_belegstelle() -> None:
    source = article(with_citation=False)
    first = "auch kha chiṅ „eine Variante“"
    source["visual_lines"] = [{"text": first, "page_id": "page-1", "span_index": 0,
        "printed_page": 17, "run_start": 0, "run_end_exclusive": len(first),
        "unknown_glyphs": [], "style_spans": [
            {"start": 0, "end": 5, "family": "TGaramond", "style": "regular"},
            {"start": 5, "end": 14, "family": "TGaramond", "style": "italic"},
            {"start": 14, "end": len(first), "family": "TGaramond", "style": "regular"}]}]
    source["source_faithful_sha256"] = sha256(first.encode()).hexdigest()
    source["divisions"] = [{"kind": "unsegmented", "label": "",
        "start_line_index": 0, "end_line_index_exclusive": 1, "text": first}]
    source["candidates"] = {"german_quotes": [{"visual_start": first.index("„"),
        "visual_end": len(first), "division_index": 0, "start_line_index": 0}],
        "parenthetical_citations": [], "adjacent_quote_citation_pairs": []}
    row = project(source, extract(source))
    assert [item["kind"] for item in row["divisions"][0]["items"]] == ["variant_gloss_candidate"]
    assert row["divisions"][0]["items"][0]["components"]["variant_glosses"]["cue"] == "auch"


def test_projection_rejects_source_mismatch() -> None:
    source = article()
    lexical = extract(source)
    lexical["source_faithful_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source identity mismatch"):
        project(source, lexical)


def test_quoted_opening_gloss_is_definition_in_its_sense() -> None:
    source = article()
    third = "2. „deutsche Definition“"
    source["visual_lines"].append({
        "text": third, "page_id": "page-1", "span_index": 0,
        "printed_page": 17, "run_start": 0, "run_end_exclusive": len(third),
        "unknown_glyphs": [], "style_spans": [{
            "start": 0, "end": len(third), "family": "TGaramond",
            "style": "regular"}]})
    prior = source["divisions"][0]["text"]
    source["divisions"].append({"kind": "numbered_sense", "label": "2",
                                "start_line_index": 2,
                                "end_line_index_exclusive": 3, "text": third})
    source["source_faithful_sha256"] = sha256((prior + "\n" + third).encode()).hexdigest()
    quote_start = len(prior) + 1 + third.index("„")
    source["candidates"]["german_quotes"].append({
        "visual_start": quote_start,
        "visual_end": quote_start + len("„deutsche Definition“"),
        "division_index": 1, "start_line_index": 2})
    row = project(source, extract(source))
    second = row["divisions"][1]
    assert second["kind"] == "sense_candidate"
    assert next(item for item in second["items"] if item["kind"] == "definition_candidate")[
        "components"]["translations"]["text"] == "„deutsche Definition“"
    assert not any(item["kind"] == "belegstelle_candidate" for item in second["items"])


def test_corpus_build_is_byte_reproducible(tmp_path: Path) -> None:
    source = article()
    lexical = extract(source)
    source_path = tmp_path / "source.jsonl.gz"
    lexical_path = tmp_path / "lexical.jsonl.gz"
    for path, row in ((source_path, source), (lexical_path, lexical)):
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    first = build(source_path, lexical_path, tmp_path / "first.gz", tmp_path / "first.jsonl")
    second = build(source_path, lexical_path, tmp_path / "second.gz", tmp_path / "second.jsonl")
    assert first == second
    assert (tmp_path / "first.gz").read_bytes() == (tmp_path / "second.gz").read_bytes()
    assert (tmp_path / "first.jsonl").read_bytes() == (tmp_path / "second.jsonl").read_bytes()
