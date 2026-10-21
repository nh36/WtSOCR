import copy
import hashlib
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


def test_reviewed_editorial_href_preserves_original_and_requires_exact_review():
    r = reference('https://wts-digital.badw.de/lemma/%3Ctib%3Eka/1')
    index = EntryIndex([entry()])
    assert index.resolve_manifestation(r)['canonical_resolution']['status'] == 'unresolved'
    review = reviewed(r, homonym='1', source_target_url=r['target_url'],
        annotation_id='review-1', binding={'hash': 'frozen'}, physical_selectors=[{'raw': 'source'}],
        ranges=[{'start': 2, 'end': 4, 'literal': '↑ka'}])
    before = copy.deepcopy(r)
    result = index.resolve_reviewed_editorial_target(r, review)
    assert r == before
    assert {k: v for k, v in result.items() if k != 'canonical_resolution'} == before
    assert result['canonical_resolution']['target_entry_id'] == 'entry-1'
    assert result['canonical_resolution']['method'] == 'reviewed_exact_editorial_target'
    assert result['canonical_resolution']['target_review'] == review
    assert EntryIndex([]).resolve_reviewed_editorial_target(r, review)['canonical_resolution']['status'] == 'unresolved'
    for field in ('source_target_url', 'literal', 'occurrence_id', 'source_spans', 'annotation_id', 'binding', 'physical_selectors', 'ranges'):
        bad = copy.deepcopy(review)
        bad[field] = None
        with pytest.raises(ValueError, match='bound'):
            index.resolve_reviewed_editorial_target(r, bad)
    with pytest.raises(ValueError, match='accepted'):
        index.resolve_reviewed_editorial_target(reference(), review)
    frozen = copy.deepcopy(r)
    frozen['canonical_resolution'] = dict(status='resolved', target_entry_id='previous')
    with pytest.raises(ValueError, match='accepted'):
        index.resolve_reviewed_editorial_target(frozen, review)


def test_deterministic_index_and_resolution():
    a,b=entry(),entry("entry-2",lemma="kha",url="https://example/lemma/kha/1")
    assert EntryIndex([a,b]).resolve(reference()) == EntryIndex([b,a,a]).resolve(reference())
    with pytest.raises(ValueError,match="provenance"):
        EntryIndex([a]).resolve(dict(record_type="cross_reference"))


def test_reviewed_nested_href_uses_full_exact_identity_without_widening_partial_label():
    r = reference('https://wts-digital.badw.de/lemma/%3Cspan%20class=')
    r['target_label'] = 'dkar'
    review = reviewed(r, homonym='1', source_target_url=r['target_url'],
        annotation_id='nested-review', binding={'hash': 'frozen'},
        physical_selectors=[{'raw': 'source'}], ranges=[{'start': 2, 'end': 4, 'literal': '↑dkar'}])
    review['lemma'] = 'dkar nag'
    before = copy.deepcopy(r)
    index = EntryIndex([entry('partial', lemma='dkar'), entry('full', lemma='dkar nag'),
                        entry('homonym', lemma='dkar nag', homonym='2')])
    assert index.resolve_manifestation(r)['canonical_resolution']['status'] == 'unresolved'
    result = index.resolve_reviewed_editorial_target(r, review)
    assert result['canonical_resolution']['target_entry_id'] == 'full'
    assert {k: v for k, v in result.items() if k != 'canonical_resolution'} == before
    assert r == before
    assert EntryIndex([entry('partial', lemma='dkar')]).resolve_reviewed_editorial_target(r, review)['canonical_resolution']['status'] == 'unresolved'


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


def plural_fixture(target_text="ka, kha", *, members=None, source_binding=True,
                   geometry=True, article_id="source-pdf-article",
                   source_hash=None):
    text = "↑" + target_text
    if members is None:
        members = ["ka", "kha"]
    targets = []
    for literal in members:
        start = text.find(literal)
        targets.append(dict(visual_start=start, visual_end=start + len(literal),
                            source_text=literal))
    style_spans = []
    for target in targets:
        style_spans.append(dict(start=target["visual_start"], end=target["visual_end"],
                                style="italic", font_id="italic-font"))
    line = dict(text=text, page_id="page-1", printed_page=1, first_x=100.0, y=500.0,
                style_spans=style_spans)
    if not geometry:
        line.pop("first_x")
    actual_hash = source_hash or "a" * 64
    structure = dict(article_id=article_id, source_faithful_sha256=actual_hash,
                     review_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                     visual_lines=[line])
    occurrence = dict(record_type="cross_reference", id="source:ref", entry_id="source",
                      marker="↑", target_label=target_text,
                      source_candidate=dict(visual_start=0, visual_end=len(text),
                                            target_label_candidate=target_text,
                                            target_candidates=targets),
                      source_spans=[dict(visual_start=0, visual_end=len(text),
                                         target_label_candidate=target_text)])
    binding = dict(identity=article_id, text_sha256=actual_hash) if source_binding else None
    return occurrence, structure, text, binding


def plural_index(*lemmas):
    return EntryIndex([entry(f"entry-{i}", lemma=lemma,
                             url=f"https://example/lemma/{lemma}/1")
                       for i, lemma in enumerate(lemmas, 1)])


def resolve_plural(index, fixture):
    occurrence, structure, text, binding = fixture
    return index.resolve_source_candidate_with_members(
        occurrence, structure=structure, text=text, source_binding=binding)


def test_comma_separated_targets_are_one_occurrence_with_ordered_exact_members():
    # Source-shaped spelling from the reviewed mkhar ’gro occurrence.  This
    # deliberately tests two target members within one printed reference.
    fixture = plural_fixture("mkha’ ’gro, mkha’ ’gro ma",
                             members=["mkha’ ’gro", "mkha’ ’gro ma"])
    occurrence, _, _, _ = fixture
    before = copy.deepcopy(occurrence)
    result = resolve_plural(plural_index("mkha’ ’gro", "mkha’ ’gro ma"), fixture)
    resolution = result["canonical_resolution"]
    assert result["id"] == occurrence["id"]
    assert result["canonical_resolution"]["status"] == "unresolved"
    assert resolution["target_members_status"] == "complete"
    assert "target_entry_id" not in resolution
    assert "target_lexical_entity" not in resolution
    assert [m["ordinal"] for m in resolution["target_members"]] == [0, 1]
    assert [m["literal"] for m in resolution["target_members"]] == ["mkha’ ’gro", "mkha’ ’gro ma"]
    assert [m["source_span"] for m in resolution["target_members"]] == [
        dict(start=1, end=11), dict(start=13, end=26)]
    assert [m["preceding_separator"] for m in resolution["target_members"]] == [None, ", "]
    assert all(m["resolution_status"] == "resolved" for m in resolution["target_members"])
    assert occurrence == before


@pytest.mark.parametrize('members', [('sku bźi', 'sku gsum'), ('bkroṅ', 'bkroṅs')])
def test_parser_continuous_italic_members_pass_independent_source_gates(members):
    from parse_badw_pdf_articles import _candidates
    occurrence, structure, text, binding = plural_fixture(', '.join(members), members=members)
    line = structure['visual_lines'][0]
    line['style_spans'] = [dict(start=1, end=len(text), style='italic', font_id='one-run')]
    line.update(span_index=0, run_start=0, run_end_exclusive=1)
    occurrence['source_candidate'] = _candidates(
        [line], [dict(start_line_index=0, end_line_index_exclusive=1)])['cross_references'][0]
    result = resolve_plural(plural_index(*members), (occurrence, structure, text, binding))
    resolution = result['canonical_resolution']
    assert resolution['status'] == 'unresolved'
    assert 'target_entry_id' not in resolution
    assert resolution['target_members_status'] == 'complete'
    assert [m['literal'] for m in resolution['target_members']] == list(members)
    assert all(m['resolution_status'] == 'resolved' for m in resolution['target_members'])
    # Even exact names and typography cannot bypass a mismatched source binding.
    wrong_binding = dict(binding, text_sha256='b' * 64)
    rejected = resolve_plural(plural_index(*members), (occurrence, structure, text, wrong_binding))
    assert 'target_members' not in rejected['canonical_resolution']


def test_three_members_and_explicit_arrows_preserve_source_order_and_separators():
    three = plural_fixture("ka, kha und ga", members=["ka", "kha", "ga"])
    result = resolve_plural(plural_index("ka", "kha", "ga"), three)
    members = result["canonical_resolution"]["target_members"]
    assert [m["literal"] for m in members] == ["ka", "kha", "ga"]
    assert [m["preceding_separator"] for m in members] == [None, ", ", " und "]
    arrows = plural_fixture("ka↑kha", members=["ka", "kha"])
    result = resolve_plural(plural_index("ka", "kha"), arrows)
    assert [m["preceding_separator"] for m in
            result["canonical_resolution"]["target_members"]] == [None, "↑"]


def test_homonym_member_and_exact_index_are_kept_separate_from_literal():
    text = "↑ka, \n2\nkheṅs"
    starts = [text.index("ka"), text.index("2")]
    targets = [
        dict(visual_start=starts[0], visual_end=starts[0] + 2, source_text="ka"),
        dict(visual_start=starts[1], visual_end=len(text), source_text="2\nkheṅs"),
    ]
    lines = [
        dict(text="↑ka, ", page_id="p", printed_page=1, first_x=100, y=500,
             style_spans=[dict(start=0, end=1, style="regular", font_id="roman"),
                          dict(start=1, end=3, style="italic", font_id="i")]),
        dict(text="2", page_id="p", printed_page=1, first_x=101, y=496,
             style_spans=[dict(start=0, end=1, style="italic", font_id="n")]),
        dict(text="kheṅs", page_id="p", printed_page=1, first_x=104, y=491,
             style_spans=[dict(start=0, end=5, style="italic", font_id="i")]),
    ]
    structure = dict(article_id="source-pdf-article", source_faithful_sha256="a" * 64,
                     review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                     visual_lines=lines)
    occurrence = dict(record_type="cross_reference", id="source:ref", entry_id="source",
                      marker="↑", target_label=text[1:],
                      source_candidate=dict(visual_start=0, visual_end=len(text),
                                            target_label_candidate=text[1:], target_candidates=targets),
                      source_spans=[dict(visual_start=0, visual_end=len(text),
                                         target_label_candidate=text[1:])])
    fixture = (occurrence, structure, text,
               dict(identity="source-pdf-article", text_sha256="a" * 64))
    index = EntryIndex([entry("ka", "ka"),
                        entry("kheṅs-1", "kheṅs", "1", "https://example/lemma/kheṅs/1"),
                        entry("kheṅs-2", "kheṅs", "2", "https://example/lemma/kheṅs/2")])
    before = copy.deepcopy(occurrence)
    result = resolve_plural(index, fixture)
    members = result["canonical_resolution"]["target_members"]
    assert result["canonical_resolution"]["target_members_status"] == "complete"
    assert members[1]["literal"] == "2\nkheṅs"
    assert members[1]["printed_target"]["homonym"] == "2"
    assert members[1]["printed_target"]["lexical_target"] == "kheṅs"
    assert members[1]["homonym_qualifier"] == "2"
    assert members[1]["target_entry_id"] == "kheṅs-2"
    assert occurrence == before


def test_partial_list_and_multiple_manifestations_do_not_choose_arbitrary_entry():
    fixture = plural_fixture()
    result = resolve_plural(plural_index("ka"), fixture)
    resolution = result["canonical_resolution"]
    assert resolution["target_members_status"] == "partial"
    assert [m["resolution_status"] for m in resolution["target_members"]] == ["resolved", "unresolved"]
    assert resolution["target_members"][0]["target_entry_id"] == "entry-1"
    assert resolution["target_members"][1]["exact_index_candidate_ids"] == []
    assert resolution["target_members"][1]["residual_reason"] == "exact_target_absent_from_acquired_index"
    manifests = EntryIndex([
        entry("entry-1", "ka", url="https://example/lemma/ka/1"),
        entry("entry-2", "kha", url="https://example/lemma/kha/1"),
        entry("entry-kha-2", "kha", url="https://example/lemma/kha/2"),
    ])
    result = resolve_plural(manifests, fixture)
    member = result["canonical_resolution"]["target_members"][1]
    assert member["resolution_status"] == "resolved"
    assert member["exact_index_candidate_ids"] == ["entry-2", "entry-kha-2"]
    assert "target_entry_id" not in member
    assert len(member["target_lexical_entity"]["witness_entry_ids"]) == 2


@pytest.mark.parametrize("mutation", [
    "bare_line_break", "overlap", "wrong_literal", "altered_hash", "missing_binding",
    "missing_geometry", "outside_parent",
])
def test_unproven_plural_boundaries_fall_back_to_unchanged_singular_contract(mutation):
    fixture = list(plural_fixture("ka, kha"))
    occurrence, structure, text, binding = fixture
    targets = occurrence["source_candidate"]["target_candidates"]
    if mutation == "bare_line_break":
        text = "↑ka\nkha"
        structure["visual_lines"] = [
            dict(text="↑ka", page_id="page-1", printed_page=1, first_x=100, y=500,
                 style_spans=[dict(start=0, end=1, style="regular", font_id="roman"),
                              dict(start=1, end=3, style="italic", font_id="i")]),
            dict(text="kha", page_id="page-1", printed_page=1, first_x=100, y=490,
                 style_spans=[dict(start=0, end=3, style="italic", font_id="i")]),
        ]
        occurrence["target_label"] = "ka\nkha"
        occurrence["source_candidate"].update(visual_end=len(text),
                                                target_label_candidate="ka\nkha")
        targets[1].update(visual_start=4, visual_end=7)
        structure["review_text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    elif mutation == "overlap":
        targets[1].update(visual_start=2, visual_end=3, source_text="a")
    elif mutation == "wrong_literal":
        targets[1]["source_text"] = "xyz"
    elif mutation == "altered_hash":
        binding["text_sha256"] = "b" * 64
    elif mutation == "missing_binding":
        fixture[3] = None
    elif mutation == "missing_geometry":
        structure["visual_lines"][0].pop("first_x")
    elif mutation == "outside_parent":
        occurrence["source_candidate"]["visual_end"] = targets[1]["visual_start"]
        occurrence["target_label"] = text[1:targets[1]["visual_start"]]
        occurrence["source_candidate"]["target_label_candidate"] = occurrence["target_label"]
    fixture = (occurrence, structure, text, fixture[3])
    result = resolve_plural(plural_index("ka", "kha"), fixture)
    assert "target_members" not in result["canonical_resolution"]
    expected = plural_index("ka", "kha").resolve_source_candidate(
        occurrence, structure=structure, text=text)
    assert result == expected


def test_single_target_output_is_byte_equivalent_to_existing_resolver_contract():
    text = "↑ka"
    structure = dict(article_id="source-pdf-article", source_faithful_sha256="a" * 64,
                     review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                     visual_lines=[dict(text=text, page_id="page-1", printed_page=1,
                                        first_x=100, y=500,
                                        style_spans=[dict(start=0, end=1, style="regular", font_id="r"),
                                                     dict(start=1, end=3, style="italic", font_id="i")])])
    occurrence = dict(record_type="cross_reference", id="source:ref", entry_id="source",
                      marker="↑", target_label="ka",
                      source_candidate=dict(visual_start=1, visual_end=3,
                                            target_label_candidate="ka",
                                            target_candidates=[dict(visual_start=1, visual_end=3,
                                                                    source_text="ka")]),
                      source_spans=[dict(source_id="source-pdf-article", source_sha256="a" * 64,
                                         start=1, end=3)])
    binding = dict(identity="source-pdf-article", text_sha256="a" * 64)
    index = plural_index("ka")
    old = index.resolve_source_candidate(occurrence, structure=structure, text=text)
    new = index.resolve_source_candidate_with_members(occurrence, structure=structure,
                                                      text=text, source_binding=binding)
    assert new == old
