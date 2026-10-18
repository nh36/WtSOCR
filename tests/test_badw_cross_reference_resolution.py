import copy
import json
import subprocess
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from resolve_badw_cross_references import EntryIndex, printed_target


def entry(identifier="entry-1", lemma="ka", homonym="1", url="https://example/lemma/ka/1"):
    return dict(record_type="entry", id=identifier, stable_url=url,
                headword=dict(loc=lemma), homonym=homonym)


def reference(url="https://example/lemma/ka/1"):
    r = dict(record_type="cross_reference", id="ref-1", entry_id="source-entry",
             marker="↑", target_label="ka", resolution_status="resolved" if url else "unresolved",
             source_spans=[dict(source_id="source", source_sha256="a"*64, start=2, end=4)])
    if url:
        r["target_url"] = url
    return r


def reviewed(r, **kwargs):
    return dict(occurrence_id=r["id"],source_spans=r["source_spans"],literal=r["target_label"],
                lemma="ka",review=dict(reviewer="reviewer",reviewed_at="2026-10-05",evidence="Exact printed target inspected"),**kwargs)


def test_url_capture_and_canonical_resolution_separate_and_immutable():
    r = reference()
    before = copy.deepcopy(r)
    result = EntryIndex([entry()]).resolve(r)
    assert r == before
    assert {k:v for k,v in result.items() if k!="canonical_resolution"} == before
    assert result["canonical_resolution"]["target_entry_id"] == "entry-1"
    absent = EntryIndex([]).resolve(r)
    assert absent["resolution_status"] == "resolved"  # source URL is still captured
    assert absent["canonical_resolution"]["status"] == "unresolved"
    assert "target_entry_id" not in absent["canonical_resolution"]


def test_ambiguous_url_and_conflicting_entry_identity_fail_closed():
    assert EntryIndex([entry(),entry("entry-2")]).resolve(reference())["canonical_resolution"]["status"] == "ambiguous"
    with pytest.raises(ValueError, match="conflicting"):
        EntryIndex([entry(),entry(lemma="kha")])


def test_no_url_normalization_or_fallback_to_label():
    r = reference("https://example/lemma/ka/1/")
    assert EntryIndex([entry()]).resolve(r)["canonical_resolution"]["status"] == "unresolved"


def test_printed_homonyms_require_evidence_and_never_nearest_choice():
    r = reference(None)
    index = EntryIndex([entry(),entry("entry-2",homonym="2",url="https://example/lemma/ka/2")])
    assert index.resolve(r)["canonical_resolution"]["status"] == "unresolved"
    assert index.resolve(r,reviewed_target=reviewed(r))["canonical_resolution"]["status"] == "ambiguous"
    assert index.resolve(r,reviewed_target=reviewed(r,homonym="2"))["canonical_resolution"]["target_entry_id"] == "entry-2"


def test_review_bound_to_literal_and_source():
    r = reference(None)
    for field,value in [("literal","kha"),("source_spans",[]),("occurrence_id","other")]:
        review = reviewed(r)
        review[field] = value
        with pytest.raises(ValueError,match="bound"):
            EntryIndex([entry()]).resolve(r,reviewed_target=review)


def test_deterministic_index_and_resolution():
    a,b=entry(),entry("entry-2",lemma="kha",url="https://example/lemma/kha/1")
    assert EntryIndex([a,b]).resolve(reference()) == EntryIndex([b,a,a]).resolve(reference())
    with pytest.raises(ValueError,match="provenance"):
        EntryIndex([a]).resolve(dict(record_type="cross_reference"))


def test_cli_offline_unicode_and_byte_identical_replay(tmp_path):
    entries, refs, output = (tmp_path / name for name in ("entries.jsonl", "refs.jsonl", "output.jsonl"))
    entries.write_text(json.dumps(entry(), ensure_ascii=False)+"\n", encoding="utf-8")
    r = reference()
    r["target_label"] = "ka\u2028ཀ"
    refs.write_text(json.dumps(r, ensure_ascii=False)+"\n", encoding="utf-8")
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "resolve_badw_cross_references.py"),
               "--entries", str(entries), "--references", str(refs), "--output", str(output)]
    subprocess.run(command, check=True)
    first = output.read_bytes()
    subprocess.run(command, check=True)
    assert output.read_bytes() == first
    assert json.loads(first)["target_label"] == r["target_label"]


def raised_target_fixture(*, number_style="italic", number_y=556.3, word_y=551.6,
                          number_x=345.9, word_x=349.3, number_page="page-70",
                          word_page="page-70", number_printed_page=70,
                          word_printed_page=70, missing_geometry=False,
                          embedded=False):
    if embedded:
        text = "↑\n2 kheṅs"
        lines = [
            dict(text="↑", page_id="page-70", printed_page=70, first_x=342.3, y=566.5,
                 style_spans=[dict(start=0, end=1, style="regular", font_id="roman")]),
            dict(text="2 kheṅs", page_id="page-70", printed_page=70, first_x=345.9, y=556.3,
                 style_spans=[dict(start=0, end=7, style="italic", font_id="italic")]),
        ]
    else:
        text = "↑\n2\nkheṅs"
        number = dict(text="2", page_id=number_page, printed_page=number_printed_page,
                      first_x=number_x, y=number_y,
                      style_spans=[dict(start=0, end=1, style=number_style, font_id="number-font")])
        word = dict(text="kheṅs", page_id=word_page, printed_page=word_printed_page,
                    first_x=word_x, y=word_y,
                    style_spans=[dict(start=0, end=5, style="italic", font_id="lexical-italic")])
        if missing_geometry:
            number.pop("y")
        lines = [
            dict(text="↑", page_id="page-70", printed_page=70, first_x=342.3, y=566.5,
                 style_spans=[dict(start=0, end=1, style="regular", font_id="roman")]),
            number, word,
        ]
    target = dict(visual_start=1, visual_end=len(text), source_text=text[1:])
    return text, dict(visual_lines=lines), target


def test_isolated_raised_italic_homonym_resolves_exact_index_identity_without_mutation():
    text, structure, target = raised_target_fixture()
    occurrence = dict(record_type="cross_reference", id="source:ref", entry_id="source",
                      marker="↑", target_label=target["source_text"],
                      source_candidate=dict(target_candidates=[target]),
                      source_spans=[dict(source_id="source", source_sha256="b" * 64,
                                         start=target["visual_start"], end=target["visual_end"])])
    before = copy.deepcopy(occurrence)
    parsed = printed_target(target, structure, text)
    assert parsed["valid"] is True
    assert parsed["homonym"] == "2"
    assert parsed["lexical_target"] == "kheṅs"
    assert parsed["qualifier_span"] == dict(start=2, end=3)
    assert parsed["lexical_span"] == dict(start=4, end=9)
    result = EntryIndex([
        entry("kheṅs-1", lemma="kheṅs", homonym="1", url="https://example/lemma/kheṅs/1"),
        entry("kheṅs-2", lemma="kheṅs", homonym="2", url="https://example/lemma/kheṅs/2"),
        entry("nearby", lemma="kheṅ", homonym="2", url="https://example/lemma/kheṅ/2"),
    ]).resolve_source_candidate(occurrence, structure=structure, text=text)
    assert result["canonical_resolution"]["status"] == "resolved"
    assert result["canonical_resolution"]["candidate_entry_ids"] == ["kheṅs-2"]
    assert result["canonical_resolution"]["target_entry_id"] == "kheṅs-2"
    assert result["canonical_resolution"]["parsed_target"]["homonym"] == "2"
    assert result["canonical_resolution"]["parsed_target"]["lexical_target"] == "kheṅs"
    assert occurrence == before
    assert result["target_label"] == "\n2\nkheṅs"
    assert target["source_text"] == "\n2\nkheṅs"


def test_existing_regular_raised_homonym_path_is_preserved():
    text, structure, target = raised_target_fixture(number_style="regular")
    parsed = printed_target(target, structure, text)
    assert parsed["valid"] is True
    assert parsed["homonym"] == "2"
    assert parsed["lexical_target"] == "kheṅs"


@pytest.mark.parametrize("changes", [
    {"number_y": 551.6},                         # same baseline
    {"number_x": 351.0},                         # numeral is not left of the word
    {"number_y": 570.0},                         # excessive vertical displacement
    {"missing_geometry": True},                  # missing coordinate
    {"word_page": "different-page"},             # page transition
    {"embedded": True},                          # numeral is part of a lexical line
    {"word_printed_page": 71},                   # printed page transition
])
def test_italic_numeric_qualifier_requires_isolated_raised_same_page_geometry(changes):
    text, structure, target = raised_target_fixture(**changes)
    parsed = printed_target(target, structure, text)
    assert parsed["valid"] is False
    assert parsed["shape"] == "unverified_numeric_qualifier"


def test_italic_qualifier_does_not_select_nearest_homonym_or_other_exact_label():
    text, structure, target = raised_target_fixture()
    occurrence = dict(record_type="cross_reference", id="source:ref", entry_id="source",
                      marker="↑", target_label=target["source_text"],
                      source_candidate=dict(target_candidates=[target]),
                      source_spans=[dict(source_id="source", source_sha256="c" * 64,
                                         start=1, end=len(text))])
    index = EntryIndex([
        entry("wrong-homonym", lemma="kheṅs", homonym="1", url="https://example/lemma/kheṅs/1"),
        entry("near-spelling", lemma="kheṅ", homonym="2", url="https://example/lemma/kheṅ/2"),
    ])
    result = index.resolve_source_candidate(occurrence, structure=structure, text=text)
    assert result["canonical_resolution"]["status"] == "unresolved"
    assert result["canonical_resolution"]["candidate_entry_ids"] == []
    assert result["canonical_resolution"]["parsed_target"]["literal"] == "\n2\nkheṅs"
    assert result["canonical_resolution"]["parsed_target"]["homonym"] == "2"
    assert result["canonical_resolution"]["parsed_target"]["lexical_target"] == "kheṅs"
