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


@pytest.mark.parametrize('url,lemma', [
    ('https://wts-digital.badw.de/lemma/pe%C2%A0%C3%B1a%20ba/1', 'pe ña ba'),
    ('https://wts-digital.badw.de/lemma/%20%E2%80%99drog/1', '’drog'),
    ('https://wts-digital.badw.de/lemma/ye%C2%A0%C5%9Bes%20l%E1%B9%85a/1', 'ye śes lṅa'),
    ('https://wts-digital.badw.de/lemma/gru%C2%A0%E2%80%99dzin/1', 'gru ’dzin'),
])
def test_whitespace_href_requires_review_and_keeps_explicit_homonym(url, lemma):
    from urllib.parse import quote
    r = reference(url)
    r['target_label'] = lemma
    destination = entry(lemma=lemma, url='https://wts-digital.badw.de/lemma/'+quote(lemma, safe='')+'/1')
    index = EntryIndex([destination])
    before = copy.deepcopy(r)
    assert index.resolve_manifestation(r)['canonical_resolution']['status'] == 'unresolved'
    review = reviewed(r, homonym='1', source_target_url=url,
        annotation_id='exact-source-review', binding={'hash': 'frozen'},
        physical_selectors=[{'raw': 'source'}], ranges=[{'start': 2, 'end': 4, 'literal': '↑'+lemma}])
    review['lemma'] = lemma
    result = index.resolve_reviewed_editorial_target(r, review)['canonical_resolution']
    assert result['status'] == 'resolved' and result['target_entry_id'] == destination['id']
    assert r == before
    assert EntryIndex([]).resolve_reviewed_editorial_target(r, review)['canonical_resolution']['status'] == 'unresolved'
    # An exact lexical spelling does not establish the URL's numbered identity.
    unnumbered = dict(destination, homonym='', stable_url='https://example/unnumbered')
    assert EntryIndex([unnumbered]).resolve_reviewed_editorial_target(r, review)['canonical_resolution']['status'] == 'unresolved'
    alternative = dict(destination, id='second-witness', stable_url='https://example/second')
    choice = EntryIndex([destination, alternative]).resolve_reviewed_editorial_target(r, review)['canonical_resolution']
    assert choice.get('target_entry_id') is None
    assert set(choice['candidate_entry_ids']) == {destination['id'], alternative['id']}


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


def test_reviewed_split_anchor_keeps_homonyms_ambiguous_and_witness_selection():
    r = reference('https://wts-digital.badw.de/lemma/%E2%80%99/1')
    r['target_label'] = '’'
    review = reviewed(r, homonym=None, source_target_url=r['target_url'],
        annotation_id='split-review', binding={'hash': 'frozen'},
        physical_selectors=[{'raw': 'source'}], ranges=[
            {'start': 2, 'end': 4, 'literal': '↑’'}, {'start': 4, 'end': 8, 'literal': 'dren'}])
    review['lemma'] = '’dren'
    one = entry('one', lemma='’dren', url='https://example/lemma/’dren/1')
    two = entry('two', lemma='’dren', homonym='2', url='https://example/lemma/’dren/2')
    witness = entry('witness', lemma='’dren', url='https://example/pdf/’dren')
    def resolve(rows):
        return EntryIndex(rows).resolve_reviewed_editorial_target(r, review)['canonical_resolution']
    assert resolve([])['status'] == 'unresolved'
    assert resolve([one])['target_entry_id'] == 'one'
    assert resolve([one, two])['status'] == 'ambiguous'
    selection = resolve([one, witness])
    assert selection['status'] == 'resolved' and not selection.get('target_entry_id')
    assert set(selection['candidate_entry_ids']) == {'one', 'witness'}


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


def substitution_fixture():
    fixture = plural_fixture('bag la ~', members=['bag la ~'])
    occurrence, structure, text, binding = fixture
    structure['loc_headword'] = 'ñal'
    occurrence['source_spans'] = [copy.deepcopy(occurrence['source_candidate'])]
    review = dict(occurrence_id=occurrence['id'], source_spans=occurrence['source_spans'],
        literal='bag la ~', source_target_url=None, source_headword='ñal', lemma='bag la ñal',
        homonym=None, basis='reviewed_printed_headword_substitution', annotation_id='review-1',
        binding=dict(text_sha256=hashlib.sha256(text.encode()).hexdigest()),
        physical_selectors=[dict(page_id='page-1')],
        ranges=[dict(start=0,end=len(text),literal=text)],
        review=dict(reviewer='synthetic reviewer', reviewed_at='2026-10-21', evidence='Synthetic facsimile review'))
    return fixture, review


def substitute(index, fixture, review):
    occurrence, structure, text, binding = fixture
    return index.resolve_reviewed_printed_substitution(occurrence, review,
        structure=structure, text=text, source_binding=binding)


def test_reviewed_printed_abbreviation_preserves_source_and_homonym_uncertainty():
    fixture, review = substitution_fixture()
    before = copy.deepcopy((fixture, review))
    index = EntryIndex([entry(lemma='bag la ñal')])
    result = substitute(index, fixture, review)
    assert result['canonical_resolution']['target_entry_id'] == 'entry-1'
    assert result['canonical_resolution']['parsed_target']['lexical_target'] == 'bag la ~'
    assert {k:v for k,v in result.items() if k!='canonical_resolution'} == fixture[0]
    assert (fixture, review) == before
    missing = substitute(EntryIndex([]), fixture, review)['canonical_resolution']
    assert missing['status']=='unresolved' and not missing['candidate_entry_ids']
    assert missing['residual_reason']=='reviewed_expanded_target_absent_from_acquired_index'
    ambiguous = substitute(EntryIndex([entry('a',lemma='bag la ñal',homonym='1'),
        entry('b',lemma='bag la ñal',homonym='2')]), fixture, review)['canonical_resolution']
    assert ambiguous['status']=='ambiguous' and 'target_entry_id' not in ambiguous
    witnesses = substitute(EntryIndex([entry('a',lemma='bag la ñal'),
        entry('b',lemma='bag la ñal')]), fixture, review)['canonical_resolution']
    assert witnesses['status']=='resolved' and 'target_entry_id' not in witnesses
    assert witnesses['witness_status']=='multiple_exact_manifestations'


@pytest.mark.parametrize('fault', ['binding','headword','lemma','span','geometry','typography','source','accepted','plural'])
def test_reviewed_printed_abbreviation_fails_closed(fault):
    fixture, review = substitution_fixture()
    occurrence, structure, text, binding = fixture
    index = EntryIndex([entry(lemma='bag la ñal')])
    if fault=='binding': review['binding']['text_sha256']='b'*64
    if fault=='headword': structure['loc_headword']='other'
    if fault=='lemma': review['lemma']='other'
    if fault=='span': review['ranges'][0]['start']=1
    if fault=='geometry': structure['visual_lines'][0].pop('first_x')
    if fault=='typography': structure['visual_lines'][0]['style_spans'][0]['style']='regular'
    if fault=='source': fixture=(occurrence,structure,text,None)
    if fault=='accepted': index=EntryIndex([entry(lemma='bag la ~')])
    if fault=='plural': fixture=plural_fixture()
    with pytest.raises(ValueError): substitute(index, fixture, review)


def wrapped_destination_fixture(compound=False):
    label = 'ka-kha' if compound else 'ka kha'
    lemma = 'ka kha' if compound else 'ka\nkha'
    fixture = plural_fixture(label, members=[label])
    occurrence, _, text, _ = fixture
    occurrence['source_spans'] = [copy.deepcopy(occurrence['source_candidate'])]
    destination = entry('wrapped', lemma=lemma, homonym='')
    destination.update(source_kind='pdf', entry_start_source_span=dict(run_start=0, loc_run_indices=[1, 2]))
    destination['headword']['source_loc'] = 'kakha'
    proof = {k: copy.deepcopy(destination[k]) for k in ('headword', 'homonym', 'entry_start_source_span')}
    proof.update(entry_id='wrapped', canonical_object_sha256='b'*64, printed_page=1)
    review = dict(occurrence_id=occurrence['id'], source_spans=occurrence['source_spans'],
        literal=label, source_target_url=None, lemma=lemma, homonym=None,
        basis='reviewed_printed_compound_headword' if compound else 'reviewed_printed_wrapped_headword', destination_heading=proof, annotation_id='review-wrapped',
        binding=dict(text_sha256=hashlib.sha256(text.encode()).hexdigest()),
        physical_selectors=[dict(page_id='page-1')], ranges=[dict(start=0,end=len(text),literal=text)],
        review=dict(reviewer='synthetic reviewer', reviewed_at='2026-10-21', evidence='Synthetic facsimile review'))
    return fixture, review, destination


@pytest.mark.parametrize('compound', [False, True])
def test_reviewed_wrapped_heading_preserves_source_and_requires_exact_index_proof(compound):
    fixture, review, destination = wrapped_destination_fixture(compound)
    before = copy.deepcopy((fixture, review, destination))
    index = EntryIndex([destination])
    old = resolve_plural(index, fixture)['canonical_resolution']
    assert old['status'] == 'unresolved' and not old['candidate_entry_ids']
    result = substitute(index, fixture, review)
    resolution = result['canonical_resolution']
    assert resolution['status'] == 'resolved' and resolution['target_entry_id'] == 'wrapped'
    assert resolution['method'] == ('reviewed_exact_printed_compound' if compound else 'reviewed_exact_wrapped_headword')
    assert resolution['parsed_target']['lexical_target'] == ('ka-kha' if compound else 'ka kha')
    assert resolution['target_lexical_entity']['headword'] == ('ka kha' if compound else 'ka\nkha')
    assert {k:v for k,v in result.items() if k!='canonical_resolution'} == fixture[0]
    assert (fixture, review, destination) == before
    # The reviewed source's literal key does not become a general alias.
    assert resolve_plural(index, fixture)['canonical_resolution'] == old


@pytest.mark.parametrize('compound', [False, True])
def test_wrapped_heading_keeps_witness_selection_and_homonym_ambiguity(compound):
    fixture, review, destination = wrapped_destination_fixture(compound)
    other = copy.deepcopy(destination);other['id'] = 'another-witness'
    resolution = substitute(EntryIndex([destination, other]), fixture, review)['canonical_resolution']
    assert resolution['status'] == 'resolved' and 'target_entry_id' not in resolution
    assert resolution['witness_status'] == 'multiple_exact_manifestations'
    assert resolution['candidate_entry_ids'] == ['another-witness', 'wrapped']
    other['homonym'] = '1'
    resolution = substitute(EntryIndex([destination, other]), fixture, review)['canonical_resolution']
    assert resolution['status'] == 'ambiguous' and 'target_entry_id' not in resolution


@pytest.mark.parametrize('fault', ['entry', 'kind', 'headword', 'span', 'homonym', 'proof',
    'lemma', 'binding', 'range', 'geometry', 'typography', 'qualifier', 'url', 'source', 'accepted', 'plural'])
@pytest.mark.parametrize('compound', [False, True])
def test_wrapped_heading_resolution_fails_closed(fault, compound):
    fixture, review, destination = wrapped_destination_fixture(compound)
    occurrence, structure, text, binding = fixture
    if fault=='entry': destination['id']='other'
    if fault=='kind': destination['source_kind']='html'
    if fault=='headword': destination['headword']['source_loc']='other'
    if fault=='span': destination['entry_start_source_span']['run_start']=1
    if fault=='homonym': destination['homonym']='1'
    if fault=='proof': review.pop('destination_heading')
    if fault=='lemma': review['lemma']='ka\nkha other'
    if fault=='binding': review['binding']['text_sha256']='b'*64
    if fault=='range': review['ranges'][0]['end']-=1
    if fault=='geometry': structure['visual_lines'][0].pop('first_x')
    if fault=='typography': structure['visual_lines'][0]['style_spans'][0]['style']='regular'
    if fault=='qualifier': review['homonym']='1'
    if fault=='url': review['source_target_url']='https://example/lemma/ka/1'
    if fault=='source': fixture=(occurrence,structure,text,None)
    if fault=='accepted': destination['headword']['loc']='ka-kha' if compound else 'ka kha'
    if fault=='plural': fixture=plural_fixture()
    with pytest.raises(ValueError): substitute(EntryIndex([destination]), fixture, review)


def nonprinting_reference(monkeypatch):
    from test_parse_badw_pdf_articles import nonprinting_fixture, _candidates
    lines, divisions, sources, _ = nonprinting_fixture(monkeypatch)
    candidate, = _candidates(lines,divisions,nonprinting_sources=sources)['cross_references']
    structure=dict(visual_lines=lines,divisions=divisions)
    text='\n'.join(l['text'] for l in lines)
    occurrence=dict(record_type='cross_reference',id='ref',entry_id='source',
                    target_label=candidate['target_label_candidate'],source_candidate=candidate)
    return occurrence, structure, text


def test_nonprinting_derived_target_requires_replay_and_exact_unique_identity(monkeypatch):
    ref, structure, text=nonprinting_reference(monkeypatch)
    original=copy.deepcopy(ref)
    index=EntryIndex([entry('target',lemma='’go ba’i lha',homonym='')])
    result=index.resolve_source_candidate(ref,structure=structure,text=text)['canonical_resolution']
    assert result['status']=='resolved' and result['target_entry_id']=='target'
    assert result['parsed_target']['literal']==ref['target_label']
    assert result['parsed_target']['lexical_target']=='’go ba’i lha'
    assert ref==original
    ambiguous=EntryIndex([entry('a',lemma='’go ba’i lha',homonym='1'),entry('b',lemma='’go ba’i lha',homonym='2')])
    assert ambiguous.resolve_source_candidate(ref,structure=structure,text=text)['canonical_resolution']['status']=='ambiguous'
    assert EntryIndex([]).resolve_source_candidate(ref,structure=structure,text=text)['canonical_resolution']['status']=='unresolved'
    ref['source_candidate']['target_candidates'][0]['nonprinting_bridge']['lexical_target']='ka'
    assert index.resolve_source_candidate(ref,structure=structure,text=text)['canonical_resolution']['status']=='unresolved'


@pytest.mark.parametrize('destinations,expected', [(0,'unresolved'),(1,'resolved'),(2,'ambiguous')])
def test_reviewed_upright_extent_uses_ordinary_exact_identity_rules(monkeypatch,destinations,expected):
    from test_parse_badw_pdf_articles import upright_space_fixture, _candidates
    _,lines,divisions,sources,_=upright_space_fixture(monkeypatch)
    candidate,=_candidates(lines,divisions,upright_space_sources=sources)['cross_references']
    text=lines[0]['text']
    records=[entry('target-'+str(i),lemma='smyug ma',homonym=str(i+1)) for i in range(destinations)]
    records.append(entry('near-label',lemma='smyug',homonym=''))
    index=EntryIndex(records)
    result=index.resolve_source_candidate(dict(target_label=candidate['target_label_candidate'],source_candidate=candidate),
        structure=dict(visual_lines=lines,divisions=divisions),text=text)
    assert result['canonical_resolution']['status']==expected
    if destinations!=1: assert result['canonical_resolution'].get('target_entry_id') is None
    else: assert result['canonical_resolution']['target_entry_id']=='target-0'


@pytest.mark.parametrize('count,status',[(0,'unresolved'),(1,'resolved'),(2,'ambiguous')])
def test_reviewed_cross_page_target_requires_exact_identity(monkeypatch,count,status):
    from test_parse_badw_pdf_articles import page_continuation_fixture,_candidates
    _,lines,divisions,sources,_=page_continuation_fixture(monkeypatch)
    candidate,=_candidates(lines,divisions,page_continuation_sources=sources)['cross_references']
    index=EntryIndex([entry('destination'+str(i),lemma='pha rol tu phyin pa',homonym=str(i+1)) for i in range(count)]+[entry('near',lemma='pha',homonym='')])
    result=index.resolve_source_candidate(dict(target_label=candidate['target_label_candidate'],source_candidate=candidate),structure=dict(visual_lines=lines,divisions=divisions),text='\n'.join(l['text'] for l in lines))['canonical_resolution']
    assert result['status']==status
    if count!=1: assert result.get('target_entry_id') is None


@pytest.mark.parametrize('literal,lemma', [('kiṅ śị', 'kiṅ śi'), ('dug-mo-ñuṅ', 'dug mo ñuṅ'), ('mu-stegs-pa', 'mu stegs pa')])
def test_editorial_headword_variant_is_occurrence_bound_not_a_spelling_rule(literal, lemma):
    r = reference(f'https://wts-digital.badw.de/lemma/{literal}/1')
    r['target_label'] = literal
    destination = entry(lemma=lemma, url=f'https://wts-digital.badw.de/lemma/{lemma}/1')
    review = reviewed(r, homonym='1', source_target_url=r['target_url'],
        annotation_id='exact-source-review', binding={'hash': 'frozen'},
        physical_selectors=[{'raw': 'source'}], ranges=[{'start': 2, 'end': 4}],
        basis='reviewed_editorial_headword_variant', destination_heading={
            'sha256': 'b'*64, 'object_path': 'verified-object', 'source_url': destination['stable_url']})
    review['lemma'] = lemma
    before = copy.deepcopy(r)
    index = EntryIndex([destination])
    assert index.resolve_manifestation(r)['canonical_resolution']['status'] == 'unresolved'
    linked = index.resolve_reviewed_editorial_target(r, review)
    assert linked['canonical_resolution']['target_entry_id'] == destination['id']
    assert linked['target_url'] == r['target_url'] and linked['target_label'] == literal
    assert r == before
    assert EntryIndex([]).resolve_reviewed_editorial_target(r, review)['canonical_resolution']['status'] == 'unresolved'
    unnumbered = dict(destination, homonym='', stable_url='https://example/unnumbered')
    assert EntryIndex([unnumbered]).resolve_reviewed_editorial_target(r, review)['canonical_resolution']['status'] == 'unresolved'
    for field, value in [('occurrence_id', 'other'), ('literal', lemma), ('source_spans', [])]:
        bad = copy.deepcopy(review)
        bad[field] = value
        with pytest.raises(ValueError):
            index.resolve_reviewed_editorial_target(r, bad)
    # Multiple witnesses of the established identity require a reader choice.
    second = dict(destination, id='second', stable_url='https://example/second')
    choice = EntryIndex([destination, second]).resolve_reviewed_editorial_target(r, review)['canonical_resolution']
    assert choice['status'] == 'resolved' and 'target_entry_id' not in choice
    assert set(choice['candidate_entry_ids']) == {destination['id'], 'second'}


def misplaced_arrow_fixture():
    fixture=plural_fixture('fut. bkru',members=['fut'])
    o,s,text,binding=fixture
    c=o['source_candidate'];c.update(visual_end=4,target_label_candidate='fut')
    o['target_label']='fut';o['source_spans']=[copy.deepcopy(c)]
    s['loc_headword']='’khrud'
    s['visual_lines'][0].update(run_start=0,run_end_exclusive=10,style_spans=[
        dict(start=0,end=6,style='regular',family='TGaramond',font_id='regular'),
        dict(start=6,end=10,style='italic',family='TGaramond',font_id='italic')])
    review=dict(occurrence_id=o['id'],source_spans=copy.deepcopy(o['source_spans']),literal='fut',source_target_url=None,source_headword='’khrud',lemma='bkru',homonym=None,basis='reviewed_printed_misplaced_arrow',annotation_id='review-arrow',review=dict(reviewer='synthetic reviewer',reviewed_at='2026-10-23',evidence='Synthetic facsimile review'),binding=dict(text_sha256=hashlib.sha256(text.encode()).hexdigest()),physical_selectors=[dict(page_id='page-1')],ranges=[dict(start=0,end=4,literal='↑fut'),dict(start=6,end=10,literal='bkru')],destination_heading=dict(source_url='https://example/lemma/bkru/1',sha256='b'*64))
    dest=entry(lemma='bkru',url='https://example/lemma/bkru/1')
    dest['source_spans']=[dict(source_sha256='b'*64)]
    return fixture,review,dest


def misplaced(index,fixture,review):
    o,s,text,b=fixture
    return index.resolve_reviewed_printed_misplaced_arrow(o,review,structure=s,text=text,source_binding=b)


def test_printed_misplaced_arrow_is_separate_from_preserved_source_and_ambiguity():
    fixture,review,dest=misplaced_arrow_fixture()
    before=copy.deepcopy((fixture,review))
    result=misplaced(EntryIndex([dest]),fixture,review)
    r=result['canonical_resolution']
    assert r['status']=='resolved' and r['target_entry_id']=='entry-1'
    assert r['editorial_interpretation']=='fut. ↑bkru'
    assert r['method']=='reviewed_printed_misplaced_arrow'
    assert {k:v for k,v in result.items() if k!='canonical_resolution'}==fixture[0]
    assert (fixture,review)==before
    other=entry('homonym-2',lemma='bkru',homonym='2')
    r=misplaced(EntryIndex([dest,other]),fixture,review)['canonical_resolution']
    assert r['status']=='ambiguous' and 'target_entry_id' not in r
    with pytest.raises(ValueError): misplaced(EntryIndex([]),fixture,review)


@pytest.mark.parametrize('fault',['binding','headword','range','geometry','font','candidate','proof','accepted'])
def test_printed_misplaced_arrow_fails_closed(fault):
    fixture,review,dest=misplaced_arrow_fixture()
    o,s,_,_=fixture
    index=EntryIndex([dest])
    if fault=='binding':review['binding']['text_sha256']='f'*64
    elif fault=='headword':s['loc_headword']='other'
    elif fault=='range':review['ranges'][1]['start']-=1
    elif fault=='geometry':s['visual_lines'][0].pop('first_x')
    elif fault=='font':s['visual_lines'][0]['style_spans'][1]['style']='regular'
    elif fault=='candidate':o['source_candidate']['visual_end']+=1
    elif fault=='proof':review['destination_heading']['sha256']='f'*64
    else:index=EntryIndex([dest,entry('old',lemma='fut')])
    with pytest.raises(ValueError):misplaced(index,fixture,review)


@pytest.mark.parametrize('label', ['ka kha', 'ka--kha', 'ka- kha', 'ka-\nkha', '~kha'])
def test_printed_compound_review_cannot_be_reused_for_another_literal(label):
    fixture, review, destination = wrapped_destination_fixture(compound=True)
    other = plural_fixture(label, members=[label])
    other[0]['source_spans'] = [copy.deepcopy(other[0]['source_candidate'])]
    review.update(literal=label, source_spans=other[0]['source_spans'],
                  binding=dict(text_sha256=hashlib.sha256(other[2].encode()).hexdigest()),
                  ranges=[dict(start=0,end=len(other[2]),literal=other[2])])
    with pytest.raises(ValueError):
        substitute(EntryIndex([destination]), other, review)


def reciprocal_destination_fixture():
    fixture,review,destination = wrapped_destination_fixture()
    occurrence,structure,_,binding=fixture
    text=' pf. zu ↓ka zusammenziehen.'
    candidate=dict(visual_start=8,visual_end=11,target_label_candidate='ka',
        target_candidates=[dict(visual_start=9,visual_end=11,source_text='ka')])
    occurrence.update(marker='↓',target_label='ka',source_candidate=candidate,source_spans=[candidate])
    structure.update(loc_headword='bcum', review_text_sha256=hashlib.sha256(text.encode()).hexdigest())
    structure['visual_lines'][0].update(text=text, style_spans=[dict(start=9,end=11,style='italic',font_id='italic-font')])
    destination.update(homonym='1',headword=dict(loc='ka',source_loc='ka'))
    proof=review['destination_heading']
    proof.update(homonym='1',headword=copy.deepcopy(destination['headword']),
        reciprocal_passage=dict(run_start=3,run_end_exclusive=4,literal=' pf. ↑bcum '))
    review.update(source_headword='bcum',literal='ka',lemma='ka',homonym='1',
        basis='reviewed_printed_reciprocal_perfect',source_spans=[candidate],
        binding=dict(text_sha256=structure['review_text_sha256']),ranges=[dict(start=8,end=11,literal='↓ka')])
    return (occurrence,structure,text,binding),review,destination


@pytest.mark.parametrize("homonym", ["1", "2"])
def test_reciprocal_perfect_selects_only_individually_reviewed_homonym(homonym):
    fixture,review,destination=reciprocal_destination_fixture()
    destination['homonym'] = review['homonym'] = review['destination_heading']['homonym'] = homonym
    other=copy.deepcopy(destination);other.update(id='second',homonym='2' if homonym=='1' else '1')
    index=EntryIndex([destination,other])
    before=copy.deepcopy((fixture,review,destination,other))
    assert resolve_plural(index,fixture)['canonical_resolution']['status']=='ambiguous'
    resolved=substitute(index,fixture,review)['canonical_resolution']
    assert resolved['status']=='resolved' and resolved['target_entry_id']=='wrapped'
    assert resolved['method']=='reviewed_exact_reciprocal_perfect'
    assert resolved['target_lexical_entity']['homonym']==homonym
    assert resolve_plural(index,fixture)['canonical_resolution']['status']=='ambiguous'
    assert (fixture,review,destination,other)==before
    witness=copy.deepcopy(destination);witness['id']='another'
    resolved=substitute(EntryIndex([destination,other,witness]),fixture,review)['canonical_resolution']
    assert resolved['status']=='resolved' and 'target_entry_id' not in resolved
    assert resolved['witness_status']=='multiple_exact_manifestations'


@pytest.mark.parametrize('fault',['hash','range','source','heading','span','homonym','unnumbered','reciprocal','missing_source','accepted'])
def test_reciprocal_perfect_resolution_fails_closed(fault):
    fixture,review,destination=reciprocal_destination_fixture()
    if fault=='hash': review['binding']['text_sha256']='0'*64
    if fault=='range': review['ranges'][0]['end']-=1
    if fault=='source': review['source_headword']='other'
    if fault=='heading': destination['headword']['source_loc']='other'
    if fault=='span': destination['entry_start_source_span']['run_start']=10
    if fault=='homonym': review['homonym']='2'
    if fault=='unnumbered': destination['homonym']=''
    if fault=='reciprocal': review['destination_heading']['reciprocal_passage']['literal']=' pf. ↑other '
    if fault=='missing_source': review.pop('source_headword')
    index=EntryIndex([destination,entry('second',lemma='ka',homonym='2')])
    if fault=='accepted': index=EntryIndex([destination])
    with pytest.raises(ValueError): substitute(index,fixture,review)
