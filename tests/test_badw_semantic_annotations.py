"""Synthetic evidence only: no downloaded HTML/PDF fixtures or network calls."""
import copy
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import badw_semantic_annotations as annotations


def put(root, body):
    sha = hashlib.sha256(body).hexdigest()
    path = root / "objects" / "sha256" / sha[:2] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return sha, str(path.relative_to(root))


def packet(tmp_path, kind="html"):
    sha, path = put(tmp_path, b"synthetic source bytes, not a real PDF")
    text = "Viṣṇus für\nulkā ཀ"
    source = {"source_object": {"sha256": sha, "object_path": path},
              "article_source_text": text, "dom_full_text": text}
    if kind == "pdf":
        page = tmp_path / "page.json.gz"
        page.write_bytes(b"synthetic positioned provenance")
        source = {"source_objects": [{"pdf_sha256": sha, "page_id": "page-1",
                    "canonical_object": page.name, "canonical_object_sha256":
                    hashlib.sha256(page.read_bytes()).hexdigest()}],
                  "source_faithful_text": text, "visual_lines": []}
        for index, line in enumerate(text.split("\n")):
            source["visual_lines"].append({"page_id": "page-1", "text": line,
                "run_start": index*10, "run_end_exclusive": index*10+1,
                "style_spans": [{"start": 0, "end": len(line), "font_id": "synthetic-font",
                                  "family": "synthetic", "style": "italic"}]})
    return {"contract_version": annotations.PACKET_VERSION, "identity": "witness-1",
            "source_kind": kind, "source": source, "review_text": text,
            "review_text_sha256": annotations.digest(text)}


def claim(p, *, kind="language_span", ranges=None, status="accepted", id="claim-1"):
    ranges = ranges or [{"start": 11, "end": 15, "literal": "ulkā"}]
    return {"contract_version": annotations.VERSION, "annotation_id": id,
        "identity": p["identity"], "binding": annotations.binding(p), "ranges": ranges,
        "physical_selectors": annotations.physical_selectors(p, ranges), "kind": kind,
        "claim": {"language": "sa"} if kind == "language_span" else {
            "base_form": "Viṣṇu", "base_language": "sa", "context_language": "de",
            "relation": "inflected_name_mention"}, "status": status,
        "review": {"reviewer": "synthetic reviewer", "reviewed_at": "2026-10-04T12:00:00+00:00",
                   "mode": "same_agent_source_review", "method_version": "synthetic-v1",
                   "evidence": "Synthetic context reviewed, not independent gold."}, "supersedes": []}


def run(tmp_path, p, claims):
    return annotations.validate([p], claims, cache=tmp_path, canonical_root=tmp_path)


@pytest.mark.parametrize("kind", ["html", "pdf"])
def test_source_bound_unicode_reproducibility(tmp_path, kind):
    p = packet(tmp_path, kind)
    a = claim(p)
    original = copy.deepcopy(p)
    first = run(tmp_path, p, [a])
    assert first == run(tmp_path, p, [a])
    assert first[0]["ranges"][0]["literal"] == "ulkā"
    assert first[0]["effective_status"] == "accepted"
    assert p == original


def test_discontinuous_ranges_preserve_literal_and_order(tmp_path):
    p = packet(tmp_path, "pdf")
    a = claim(p, ranges=[{"start": 0, "end": 6, "literal": "Viṣṇus"},
                         {"start": 11, "end": 15, "literal": "ulkā"}])
    assert len(run(tmp_path, p, [a])[0]["physical_selectors"]) == 2


def test_inflected_name_is_not_language_rewrite(tmp_path):
    p = packet(tmp_path)
    a = claim(p, kind="form_mention", ranges=[{"start": 0, "end": 6, "literal": "Viṣṇus"}])
    row = run(tmp_path, p, [a])[0]
    assert row["ranges"][0]["literal"] == "Viṣṇus"
    assert row["claim"]["base_form"] == "Viṣṇu"
    assert "language" not in row["claim"]


def test_candidates_never_promote_and_ids_sort(tmp_path):
    p = packet(tmp_path)
    result = run(tmp_path, p, [claim(p, id="z", status="candidate"), claim(p, id="a", status="rejected")])
    assert [(r["annotation_id"], r["effective_status"]) for r in result] == [("a", "rejected"), ("z", "candidate")]


def prediction(p):
    return dict(identity=p['identity'], nodes=[dict(id='root', kind='source_division',
        start=0, end=len(p['review_text']), parent=None)], edges=[])


@pytest.mark.parametrize('url,lemma', [
    ('https://wts-digital.badw.de/lemma/%3Ctib%3Eulk%C4%81/1', 'ulkā'),
    ('https://wts-digital.badw.de/lemma/%3Cspan%20class=', 'ulkā nag'),
])
def test_reviewed_editorial_target_is_bound_and_does_not_rewrite_observations(tmp_path, url, lemma):
    p = packet(tmp_path)
    base = prediction(p)
    ref = dict(record_type='cross_reference', id='xref', target_label='ulkā',
               target_url=url,
               source_spans=[dict(source_id=p['identity'], start=11, end=15)])
    base['original_records'] = [ref]
    base['nodes'].append(dict(id='refnode', kind='cross_reference', start=11, end=15,
                             parent='root', lexical_record_id='xref'))
    a = claim(p)
    a['kind'] = 'cross_reference_target'
    a['claim'] = dict(occurrence_id='xref', source_target_url=ref['target_url'],
        source_target_label='ulkā', lemma=lemma, homonym='1',
        basis='reviewed_malformed_editorial_href')
    before = copy.deepcopy(base)
    accepted = run(tmp_path, p, [a])
    result = annotations.apply_validated_annotations(p, base, accepted)
    assert base == before
    assert result['original_records'] == before['original_records']
    assert result['nodes'] == before['nodes']
    review = result['reviewed_cross_reference_targets']['xref']
    assert review['source_spans'] == ref['source_spans']
    assert review['annotation_id'] == a['annotation_id']
    for field, value in [('source_target_url', 'other'), ('source_target_label', 'other'), ('occurrence_id', 'other')]:
        bad = copy.deepcopy(a)
        bad['claim'][field] = value
        with pytest.raises(ValueError, match='cross-reference'):
            annotations.apply_validated_annotations(p, base, run(tmp_path, p, [bad]))
    bad = copy.deepcopy(base)
    bad['nodes'][-1]['start'] = 10
    with pytest.raises(ValueError, match='exact source occurrence'):
        annotations.apply_validated_annotations(p, bad, accepted)
    for status in ('candidate', 'rejected'):
        inactive = copy.deepcopy(a)
        inactive['status'] = status
        assert not annotations.apply_validated_annotations(p, base, run(tmp_path, p, [inactive]))['reviewed_cross_reference_targets']


def split_anchor_packet(tmp_path, continuation='<tib>dren</tib>.'):
    from badw_article_parser import parse_database_article
    body = ('<div class="text"><span class="link">↑<a class="link lemma" '
            'href="/lemma/’/1">’</a></span>' + continuation + '</div>').encode()
    sha, path = put(tmp_path, body)
    obj = dict(sha256=sha, object_path=path,
               final_url='https://wts-digital.badw.de/lemma/’drend/1')
    article = parse_database_article(body, source_metadata=dict(obj,
        delivery_type='database_article', valid_resource=True))
    text = article['article_source_text']
    p = dict(contract_version=annotations.PACKET_VERSION, identity='split-witness',
             source_kind='html', source=dict(source_object=obj, article_source_text=text),
             review_text=text, review_text_sha256=annotations.digest(text))
    a = claim(p, kind='cross_reference_target', ranges=[
        dict(start=0, end=2, literal='↑’'), dict(start=2, end=6, literal='dren')])
    a['claim'] = dict(occurrence_id='xref', source_target_url=article['cross_references'][0]['target_url'],
        source_target_label='’', lemma='’dren', homonym=None, basis='reviewed_split_editorial_anchor')
    return p, a, article


def test_split_anchor_review_preserves_original_and_does_not_inherit_url_homonym(tmp_path):
    p, a, article = split_anchor_packet(tmp_path)
    assert article['cross_references'][0]['split_target_evidence']['lemma'] == '’dren'
    assert article['cross_references'][0]['target_homonym'] == '1'
    ref = dict(record_type='cross_reference', id='xref', target_label='’',
        target_url=a['claim']['source_target_url'], source_spans=[dict(start=0, end=2)])
    base = prediction(p)
    base['original_records'] = [ref]
    base['nodes'].append(dict(id='refnode', kind='cross_reference', start=0, end=2,
                             parent='root', lexical_record_id='xref'))
    before = copy.deepcopy(base)
    result = annotations.apply_validated_annotations(p, base, run(tmp_path, p, [a]))
    assert base == before and result['original_records'] == before['original_records']
    assert result['nodes'] == before['nodes']
    review = result['reviewed_cross_reference_targets']['xref']
    assert review['homonym'] is None and review['lemma'] == '’dren'
    assert review['source_spans'] == ref['source_spans'] and review['ranges'] == a['ranges']
    assert review['literal'] == '’' and review['source_target_url'] == ref['target_url']
    for field, value in [('homonym', '1'), ('lemma', '’drend'), ('source_target_label', 'dren'),
                         ('source_target_url', 'https://other/lemma/’/1')]:
        bad = copy.deepcopy(a)
        bad['claim'][field] = value
        with pytest.raises(ValueError, match='split editorial anchor'):
            run(tmp_path, p, [bad])


@pytest.mark.parametrize('continuation', [
    ' <tib>dren</tib>.', '<i>dren</i>.', '<tib>dren</tib> und mehr',
    '<tib>dren (?)</tib>.', '<tib><a href="/lemma/dren/2">dren</a></tib>.',
    '<tib>dren</tib>', '<tib>dren2</tib>.', '<tib>dren, ga</tib>.'])
def test_split_anchor_needs_contiguous_typed_unqualified_dom_evidence(tmp_path, continuation):
    p, a, article = split_anchor_packet(tmp_path, continuation)
    assert 'split_target_evidence' not in article['cross_references'][0]
    # The claim must fail even if its ranges are made to agree with this text.
    a['ranges'][1] = dict(start=2, end=len(p['review_text']), literal=p['review_text'][2:])
    a['physical_selectors'] = annotations.physical_selectors(p, a['ranges'])
    with pytest.raises(ValueError, match='split editorial anchor'):
        run(tmp_path, p, [a])


def relationship(p, relation='gloss_of', status='accepted'):
    a = claim(p, ranges=[dict(start=0, end=len(p['review_text']), literal=p['review_text'])],
              status=status)
    a['kind'] = 'relationship'
    a['claim'] = dict(relation=relation, basis='reviewed_parallel_text',
        **{'from': dict(kind='translation', start=0, end=6),
           'to': [dict(kind='sanskrit', start=11, end=15)]})
    return a


def relationship_prediction(p):
    base = prediction(p)
    base['nodes'].extend([
        dict(id='lex', kind='lexical_parallel', start=0, end=17, parent='root'),
        dict(id='german', kind='translation', start=0, end=6, parent='lex'),
        dict(id='original', kind='sanskrit', start=11, end=15, parent='root')])
    return base


@pytest.mark.parametrize('kind', ['html', 'pdf'])
@pytest.mark.parametrize('extent', [(0, 3), (0, 15), (11, 17)])
def test_citable_subspan_and_mixed_passage_do_not_split_observations(tmp_path, kind, extent):
    p = packet(tmp_path, kind)
    a, b = extent
    passage = claim(p, kind='citable_passage', id='passage',
                    ranges=[dict(start=a, end=b, literal=p['review_text'][a:b])])
    passage['claim'] = {}
    rel = relationship(p)
    rel['claim'] = dict(relation='citation_of', basis='reviewed_parallel_text',
        **{'from': dict(kind='citation', start=15, end=17),
           'to': [dict(kind='citable_passage', start=a, end=b)]})
    base = relationship_prediction(p)
    base['nodes'].append(dict(id='citation', kind='citation', start=15, end=17, parent='lex'))
    before = copy.deepcopy(base)
    validated = run(tmp_path, p, [rel, passage])
    result = annotations.apply_validated_annotations(p, base, validated)
    assert base == before
    assert result['nodes'] == base['nodes']
    assert result['edges'] == base['edges']
    assert result['citable_passages'][0]['literal'] == p['review_text'][a:b]
    assert result['semantic_relationships'][0]['to'][0]['passage_id'] == 'passage:passage'
    assert result == annotations.apply_validated_annotations(p, result, validated)
    for status in ('candidate', 'rejected'):
        inactive = copy.deepcopy(passage)
        inactive['status'] = status
        with pytest.raises(ValueError, match='endpoint absent'):
            annotations.apply_validated_annotations(p, base, run(tmp_path, p, [rel, inactive]))
    with pytest.raises(ValueError, match='endpoint absent'):
        annotations.apply_validated_annotations(p, base, run(tmp_path, p, [rel]))


def test_passage_extent_must_be_unique_and_contiguous(tmp_path):
    p = packet(tmp_path)
    a = claim(p, kind='citable_passage')
    a['claim'] = {}
    b = copy.deepcopy(a)
    b['annotation_id'] = 'duplicate'
    with pytest.raises(ValueError, match='duplicate accepted'):
        annotations.apply_validated_annotations(p, prediction(p), run(tmp_path, p, [a, b]))
    a['ranges'].append(dict(start=16, end=17, literal=p['review_text'][16:17]))
    a['physical_selectors'] = annotations.physical_selectors(p, a['ranges'])
    with pytest.raises(ValueError, match='one exact range'):
        run(tmp_path, p, [a])


@pytest.mark.parametrize('kind', ['html', 'pdf'])
def test_reviewed_relationship_has_exact_endpoints_and_provenance(tmp_path, kind):
    p = packet(tmp_path, kind)
    base = relationship_prediction(p)
    validated = run(tmp_path, p, [relationship(p)])
    result = annotations.apply_validated_annotations(p, base, validated)
    edge = result['semantic_relationships'][0]
    assert edge['relation'] == 'gloss_of'
    assert edge['from']['node_id'] == 'german'
    assert edge['to'][0]['node_id'] == 'original'
    assert edge['binding'] == annotations.binding(p)
    assert edge['physical_selectors'] == validated[0]['physical_selectors']
    assert edge['review'] == validated[0]['review']
    assert result['nodes'] == base['nodes']  # Ownership never reparents source nodes.
    assert result['edges'] == []
    assert result == annotations.apply_validated_annotations(p, result, validated)


@pytest.mark.parametrize('status', ['candidate', 'rejected'])
def test_inactive_relationship_never_assigns_ownership(tmp_path, status):
    p = packet(tmp_path)
    result = annotations.apply_validated_annotations(p, relationship_prediction(p),
        run(tmp_path, p, [relationship(p, status=status)]))
    assert result['semantic_relationships'] == []
    assert result['semantic_annotations'][0]['effective_status'] == status


@pytest.mark.parametrize('ambiguous', [False, True])
def test_relationship_fails_closed_on_missing_or_ambiguous_node(tmp_path, ambiguous):
    p = packet(tmp_path)
    base = relationship_prediction(p)
    if ambiguous:
        base['nodes'].append(dict(base['nodes'][-1], id='duplicate'))
    else:
        base['nodes'].pop()
    with pytest.raises(ValueError, match='endpoint absent or ambiguous'):
        annotations.apply_validated_annotations(p, base, run(tmp_path, p, [relationship(p)]))


def test_citation_can_have_multiple_explicit_reviewed_targets(tmp_path):
    p = packet(tmp_path)
    base = prediction(p)
    base['nodes'].extend([
        dict(id='cite', kind='citation', start=0, end=6, parent='root'),
        dict(id='first', kind='lexical_parallel', start=0, end=15, parent='root'),
        dict(id='second', kind='lexical_parallel', start=0, end=17, parent='root')])
    a = relationship(p)
    a['claim'] = dict(relation='citation_of', basis='lex_item_punctuation',
        **{'from': dict(kind='citation', start=0, end=6),
           'to': [dict(kind='lexical_parallel', start=0, end=15),
                  dict(kind='lexical_parallel', start=0, end=17)]})
    result = annotations.apply_validated_annotations(p, base, run(tmp_path, p, [a]))
    assert [t['node_id'] for t in result['semantic_relationships'][0]['to']] == ['first', 'second']
    assert result['nodes'][1]['parent'] == 'root'
    assert base.get('semantic_relationships') is None


@pytest.mark.parametrize('mutation', ['type', 'outside', 'duplicate', 'basis'])
def test_invalid_relationship_contract_rejected(tmp_path, mutation):
    p = packet(tmp_path)
    a = relationship(p)
    if mutation == 'type':
        a['claim']['to'][0]['kind'] = 'definition'
    elif mutation == 'outside':
        a['claim']['to'][0]['end'] = 100
    elif mutation == 'duplicate':
        a['claim']['to'].append(dict(a['claim']['to'][0]))
    else:
        a['claim']['basis'] = 'nearest_text'
    with pytest.raises(ValueError):
        run(tmp_path, p, [a])


def test_overlay_is_source_bound_deterministic_and_idempotent(tmp_path):
    p = packet(tmp_path, 'pdf')
    original = prediction(p)
    validated = run(tmp_path, p, [claim(p)])
    result = annotations.apply_validated_annotations(p, original, validated)
    assert len(original['nodes']) == 1
    assert result['nodes'][-1]['kind'] == 'sanskrit'
    assert result['nodes'][-1]['parent'] == 'root'
    assert result['edges'] == []
    assert result == annotations.apply_validated_annotations(p, result, validated)
    assert result == annotations.apply_validated_annotations(p, original, validated)
    stale = copy.deepcopy(validated)
    stale[0]['binding']['review_text_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='binding'):
        annotations.apply_validated_annotations(p, original, stale)
    with pytest.raises(ValueError, match='validated'):
        annotations.apply_validated_annotations(p, original, [claim(p)])


@pytest.mark.parametrize('literal', ['pradakṣiṇapaṭṭikā', 'cai-\ntyāṅganaḥ', 'ulkā'])
def test_reviewed_sanskrit_preserves_literal_line_breaks_and_unicode(tmp_path, literal):
    p = packet(tmp_path)
    p['review_text'] = literal
    p['review_text_sha256'] = annotations.digest(literal)
    p['source']['article_source_text'] = literal
    p['source']['dom_full_text'] = literal
    a = claim(p, ranges=[dict(start=0, end=len(literal), literal=literal)])
    result = annotations.apply_validated_annotations(p, prediction(p), run(tmp_path, p, [a]))
    node = result['nodes'][-1]
    assert node['kind'] == 'sanskrit'
    assert p['review_text'][node['start']:node['end']] == literal
    assert result['semantic_annotations'][0]['ranges'][0]['literal'] == literal
    assert result['edges'] == []


def test_overlay_does_not_promote_inactive_or_form_claims(tmp_path):
    p = packet(tmp_path)
    old, new = claim(p, id='old'), claim(p, id='new')
    new['supersedes'] = ['old']
    claims = [old, new, claim(p, id='candidate', status='candidate'),
              claim(p, id='rejected', status='rejected'),
              claim(p, id='form', kind='form_mention',
                    ranges=[dict(start=0, end=6, literal='Viṣṇus')])]
    result = annotations.apply_validated_annotations(p, prediction(p), run(tmp_path, p, claims))
    assert len(result['nodes']) == 2
    assert result['nodes'][-1]['semantic_annotation_ids'] == ['new']
    assert len(result['semantic_annotations']) == 5


def test_overlay_discontinuous_tibetan_is_not_a_definition(tmp_path):
    p = packet(tmp_path)
    a = claim(p, ranges=[dict(start=0, end=6, literal='Viṣṇus'),
                         dict(start=16, end=17, literal='ཀ')])
    a['claim'] = dict(language='bo')  # Synthetic claim tests mechanics, not linguistic truth.
    result = annotations.apply_validated_annotations(p, prediction(p), run(tmp_path, p, [a]))
    assert [n['kind'] for n in result['nodes']] == ['source_division', 'tibetan', 'tibetan']
    assert [(n['start'], n['end']) for n in result['nodes'][1:]] == [(0, 6), (16, 17)]
    assert result['edges'] == []


def test_overlay_reuses_exact_typed_node_and_prefers_explicit_lex_parent(tmp_path):
    p = packet(tmp_path)
    base = prediction(p)
    base['nodes'].append(dict(id='lex', kind='lexical_parallel', start=0,
                             end=len(p['review_text']), parent='root'))
    validated = run(tmp_path, p, [claim(p)])
    first = annotations.apply_validated_annotations(p, base, validated)
    assert first['nodes'][-1]['parent'] == 'lex'
    already_typed = copy.deepcopy(base)
    already_typed['nodes'].append(dict(id='source-tag', kind='sanskrit',
                                       start=11, end=15, parent='lex'))
    second = annotations.apply_validated_annotations(p, already_typed, validated)
    assert len(second['nodes']) == 3
    assert second['nodes'][-1]['id'] == 'source-tag'
    assert second['nodes'][-1]['semantic_annotation_ids'] == ['claim-1']
    assert second['edges'] == []


def test_german_language_claim_does_not_invent_definition_or_translation(tmp_path):
    p = packet(tmp_path)
    a = claim(p)
    a['claim']['language'] = 'de'  # Synthetic annotation mechanics only.
    base = prediction(p)
    result = annotations.apply_validated_annotations(p, base, run(tmp_path, p, [a]))
    assert result['nodes'] == base['nodes']
    assert result['semantic_annotations'][0]['claim']['language'] == 'de'


def test_explicit_supersession_retains_old_claim(tmp_path):
    p = packet(tmp_path)
    a, b = claim(p, id="old"), claim(p, id="new")
    b["supersedes"] = ["old"]
    result = run(tmp_path, p, [a, b])
    assert {r["annotation_id"]: r["effective_status"] for r in result} == {"new": "accepted", "old": "superseded"}


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(contract_version="future"),
    lambda a: a.update(kind="citation_owner"),
    lambda a: a.update(identity="canonical-entry-not-source"),
    lambda a: a.update(status="auto_accepted"),
    lambda a: a.update(extra_field=True),
    lambda a: a["binding"].update(view_version="future"),
    lambda a: a["binding"].update(view_sha256="0"*64),
    lambda a: a["ranges"][0].update(start=True),
    lambda a: a["ranges"][0].update(end=1000),
    lambda a: a["ranges"][0].update(literal="ulka"),
    lambda a: a.update(ranges=[]),
    lambda a: a.update(physical_selectors=[]),
    lambda a: a["claim"].update(language="unknown"),
    lambda a: a["review"].update(evidence=""),
    lambda a: a["review"].update(reviewed_at="2026-10-04"),
    lambda a: a["review"].update(mode="automatic_gold"),
    lambda a: a.update(supersedes=["missing"]),
])
def test_fail_closed(tmp_path, mutation):
    p = packet(tmp_path)
    a = claim(p)
    mutation(a)
    with pytest.raises(ValueError):
        run(tmp_path, p, [a])


@pytest.mark.parametrize("ranges", [
    [{"start": 11, "end": 15, "literal": "ulkā"}, {"start": 0, "end": 6, "literal": "Viṣṇus"}],
    [{"start": 0, "end": 6, "literal": "Viṣṇus"}, {"start": 5, "end": 8, "literal": "s f"}],
])
def test_bad_range_order(tmp_path, ranges):
    p = packet(tmp_path)
    with pytest.raises(ValueError):
        run(tmp_path, p, [claim(p, ranges=ranges)])


def test_changed_physical_provenance_invalidates_binding(tmp_path):
    p = packet(tmp_path, "pdf")
    a = claim(p)
    p["source"]["visual_lines"][1]["style_spans"][0]["font_id"] = "another-font"
    with pytest.raises(ValueError, match="stale"):
        run(tmp_path, p, [a])


@pytest.mark.parametrize("kind", ["html", "pdf"])
def test_corrupt_raw_object(tmp_path, kind):
    p = packet(tmp_path, kind)
    obj = p["source"]["source_object"] if kind == "html" else p["source"]["source_objects"][0]
    sha = obj.get("sha256", obj.get("pdf_sha256"))
    (tmp_path / "objects" / "sha256" / sha[:2] / sha).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash mismatch"):
        run(tmp_path, p, [claim(p)])


def test_corrupt_canonical_page(tmp_path):
    p = packet(tmp_path, "pdf")
    (tmp_path / "page.json.gz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash mismatch"):
        run(tmp_path, p, [claim(p)])


def test_supersession_cycle_and_duplicate_ids(tmp_path):
    p = packet(tmp_path)
    a, b = claim(p, id="a"), claim(p, id="b")
    a["supersedes"], b["supersedes"] = ["b"], ["a"]
    with pytest.raises(ValueError, match="cycle"):
        run(tmp_path, p, [a, b])
    with pytest.raises(ValueError, match="duplicate annotation"):
        run(tmp_path, p, [a, a])


def test_path_escape_and_stale_view_text(tmp_path):
    p = packet(tmp_path)
    a = claim(p)
    p["source"]["source_object"]["object_path"] = "../outside"
    with pytest.raises(ValueError, match="escapes"):
        run(tmp_path, p, [a])
    p = packet(tmp_path)
    p["review_text"] += "changed"
    with pytest.raises(ValueError, match="text hash"):
        run(tmp_path, p, [claim(p)])


def test_cross_witness_supersession_rejected(tmp_path):
    first = packet(tmp_path)
    second = copy.deepcopy(first)
    second["identity"] = "witness-2"
    old, new = claim(first, id="old"), claim(second, id="new")
    new["supersedes"] = ["old"]
    with pytest.raises(ValueError, match="same-witness"):
        annotations.validate([first, second], [old, new], cache=tmp_path)


def test_cli_rejects_output_outside_actual_work_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["validator", "--packets", "absent",
        "--annotations", "absent", "--cache", "absent", "--output",
        str(tmp_path / "elsewhere" / "work" / "result.jsonl")])
    with pytest.raises(SystemExit) as error:
        annotations.main()
    assert error.value.code == 2
    assert not (tmp_path / "elsewhere").exists()


def extent_fixture(tmp_path):
    from parse_badw_pdf_articles import _candidates
    p = packet(tmp_path, 'pdf')
    text = '↑ka, kha\nga, ga.'
    lines = p['source']['visual_lines'][:2]
    lines[0].update(text='↑ka, kha', style_spans=[
        dict(start=0,end=1,style='regular'),
        dict(start=1,end=3,style='italic',font_id='same'),
        dict(start=3,end=5,style='regular'),
        dict(start=5,end=8,style='italic',font_id='same')])
    lines[1].update(text='ga, ga.', style_spans=[
        dict(start=0,end=6,style='italic',font_id='same'),dict(start=6,end=7,style='regular')])
    p['source'].update(source_faithful_text=text, visual_lines=lines)
    p.update(review_text=text,review_text_sha256=annotations.digest(text))
    for line in lines: line.update(span_index=0, printed_page=1)
    divisions=[dict(start_line_index=0,end_line_index_exclusive=2)]
    base=prediction(p)
    base['source_kind']='pdf'
    base['nodes'].append(dict(id='ref',kind='cross_reference',start=0,end=8,parent='root'))
    base['original_structure']=dict(article_id=p['identity'],visual_lines=copy.deepcopy(lines),
        divisions=divisions,candidates=_candidates(lines,divisions))
    a=claim(p,kind='cross_reference_extent',ranges=[dict(start=0,end=15,literal=text[:15])])
    a['claim']=dict(node_id='ref',previous_range=dict(start=0,end=8,literal=text[:8]),
        basis='reviewed_printed_extent')
    return p,base,a


def test_reviewed_reference_extent_retains_source_and_requires_exact_typography(tmp_path):
    p,base,a=extent_fixture(tmp_path)
    original=copy.deepcopy(base)
    reviewed=run(tmp_path,p,[a])
    result=annotations.apply_validated_annotations(p,base,reviewed)
    assert base == original
    assert result['nodes'][1]['end'] == 15
    assert result['reviewed_cross_reference_extents'] == reviewed
    targets=result['original_structure']['candidates']['cross_references'][0]['target_candidates']
    assert [t['source_text'] for t in targets] == ['ka','kha\nga','ga']
    assert result['original_structure']['visual_lines'] == p['source']['visual_lines']
    for status in ('candidate','rejected'):
        inactive=copy.deepcopy(a);inactive['status']=status
        assert annotations.apply_validated_annotations(p,base,run(tmp_path,p,[inactive]))['nodes'][1]['end']==8
    for kind in ('node','range','typography','parent','overlap'):
        changed=copy.deepcopy(base)
        if kind=='node': changed['nodes'][1]['id']='wrong'
        elif kind=='range': changed['original_structure']['candidates']['cross_references'][0]['visual_end']=7
        elif kind=='typography': changed['original_structure']['visual_lines'][1]['style_spans'][0]['font_id']='wrong'
        elif kind=='parent': changed['nodes'][0]['end']=12
        else: changed['nodes'].append(dict(id='other',kind='cross_reference',start=10,end=14,parent='root'))
        with pytest.raises(ValueError,match='reviewed cross-reference extent'):
            annotations.apply_validated_annotations(p,changed,reviewed)
    wrong=copy.deepcopy(a);wrong['claim']['previous_range']['literal']='incorrect'
    with pytest.raises(ValueError,match='invalid reviewed cross-reference extent'):
        run(tmp_path,p,[wrong])


def test_reviewed_terminal_letter_requires_explicit_extent_and_source_continuity(tmp_path):
    from parse_badw_pdf_articles import _candidates
    p = packet(tmp_path, 'pdf')
    text = ' ↓kha khyer.'
    line = p['source']['visual_lines'][0]
    line.update(text=text, span_index=0, printed_page=4, style_spans=[
        dict(start=0, end=2, style='regular', family='TGaramond', font_id='regular'),
        dict(start=2, end=10, style='italic', family='TGaramond', font_id='italic', last_run_index=8),
        dict(start=10, end=12, style='regular', family='TGaramond', font_id='regular', first_run_index=9)])
    p['source'].update(source_faithful_text=text, visual_lines=[line])
    p.update(review_text=text, review_text_sha256=annotations.digest(text))
    divisions = [dict(start_line_index=0, end_line_index_exclusive=1)]
    base = prediction(p)
    base['nodes'].append(dict(id='ref', kind='cross_reference', start=1, end=10, parent='root'))
    base['original_structure'] = dict(article_id=p['identity'], visual_lines=copy.deepcopy([line]),
        divisions=divisions, candidates=_candidates([line], divisions))
    a = claim(p, kind='cross_reference_extent', ranges=[dict(start=1, end=11, literal=text[1:11])])
    a['claim'] = dict(node_id='ref', previous_range=dict(start=1, end=10, literal=text[1:10]),
                      basis='reviewed_printed_terminal_letter')
    original = copy.deepcopy(base)
    reviewed = run(tmp_path, p, [a])
    result = annotations.apply_validated_annotations(p, base, reviewed)
    assert base == original
    assert result['nodes'][1]['end'] == 11
    candidate = result['original_structure']['candidates']['cross_references'][0]
    assert candidate['target_label_candidate'] == 'kha khyer'
    assert result['original_structure']['visual_lines'] == p['source']['visual_lines']
    assert _candidates([line], divisions)['cross_references'][0]['visual_end'] == 10
    for status in ('candidate', 'rejected'):
        inactive = copy.deepcopy(a); inactive['status'] = status
        assert annotations.apply_validated_annotations(p, base, run(tmp_path, p, [inactive]))['nodes'][1]['end'] == 10
    old_basis = copy.deepcopy(a); old_basis['claim']['basis'] = 'reviewed_printed_extent'
    with pytest.raises(ValueError, match='exact typographic support'):
        annotations.apply_validated_annotations(p, base, run(tmp_path, p, [old_basis]))
    # Mutations remain rejected even if presented in a newly bound review view.
    for field, value in [('family', 'Arial'), ('font_id', None), ('font_id', 'italic'),
                         ('first_run_index', 10), ('style', 'italic'), ('start', 9)]:
        changed = copy.deepcopy(p)
        changed['source']['visual_lines'][0]['style_spans'][2][field] = value
        changed_base = copy.deepcopy(base)
        changed_base['original_structure']['visual_lines'] = copy.deepcopy(changed['source']['visual_lines'])
        changed_claim = copy.deepcopy(a)
        changed_claim['binding'] = annotations.binding(changed)
        changed_claim['physical_selectors'] = annotations.physical_selectors(changed, a['ranges'])
        with pytest.raises(ValueError, match='exact typographic support'):
            annotations.apply_validated_annotations(changed, changed_base, run(tmp_path, changed, [changed_claim]))
    for suffix in ('rr.', 'r Wort.', '⟦UNKNOWN:x⟧.', 'r\n.'):
        changed = copy.deepcopy(line)
        changed['text'] = text[:10] + suffix
        changed['style_spans'][2]['end'] = len(changed['text'])
        assert _candidates([changed], divisions, reviewed_terminal_letter=True)['cross_references'][0]['visual_end'] == 10


def test_printed_abbreviation_annotation_binds_exact_headword_node_and_candidate(tmp_path):
    p=packet(tmp_path,'pdf')
    text='↑bag la ~'
    p['review_text']=p['source']['source_faithful_text']=text
    p['review_text_sha256']=annotations.digest(text)
    line=p['source']['visual_lines'][0]
    line['text']=text
    line['style_spans'][0]['end']=len(text)
    p['source']['visual_lines']=[line]
    candidate=dict(visual_start=0,visual_end=len(text),target_label_candidate='bag la ~')
    base=prediction(p)
    base['nodes'].append(dict(id='xref',kind='cross_reference',start=0,end=len(text),parent='root'))
    base['original_structure']=dict(loc_headword='ñal',visual_lines=copy.deepcopy(p['source']['visual_lines']),
        candidates=dict(cross_references=[candidate]))
    a=claim(p,kind='cross_reference_target',ranges=[dict(start=0,end=len(text),literal=text)])
    a['claim']=dict(occurrence_id='xref',source_target_url=None,source_target_label='bag la ~',
        source_headword='ñal',lemma='bag la ñal',homonym=None,basis='reviewed_printed_headword_substitution')
    before=copy.deepcopy(base)
    accepted=run(tmp_path,p,[a])
    result=annotations.apply_validated_annotations(p,base,accepted)
    assert base==before
    assert result['nodes']==before['nodes'] and result['original_structure']==before['original_structure']
    assert result['reviewed_cross_reference_targets']['xref']['lemma']=='bag la ñal'
    for field,value in [('source_headword','other'),('lemma','other'),('homonym','1'),('source_target_url','url')]:
        bad=copy.deepcopy(a);bad['claim'][field]=value
        with pytest.raises(ValueError): annotations.apply_validated_annotations(p,base,run(tmp_path,p,[bad]))
    for field,value in [('loc_headword','other'),('visual_lines',[])]:
        bad=copy.deepcopy(base);bad['original_structure'][field]=value
        with pytest.raises(ValueError): annotations.apply_validated_annotations(p,bad,accepted)
    for status in ('candidate','rejected'):
        inactive=copy.deepcopy(a);inactive['status']=status
        assert not annotations.apply_validated_annotations(p,base,run(tmp_path,p,[inactive]))['reviewed_cross_reference_targets']


def wrapped_fixture(tmp_path, compound=False):
    import gzip
    import json
    p = packet(tmp_path, 'pdf')
    text = '↑ka-kha' if compound else '↑ka kha'
    p['review_text'] = p['source']['source_faithful_text'] = text
    p['review_text_sha256'] = annotations.digest(text)
    line = p['source']['visual_lines'][0]
    line['text'] = text
    line['style_spans'][0]['end'] = len(text)
    p['source']['visual_lines'] = [line]
    sha = p['source']['source_objects'][0]['pdf_sha256']
    runs = [dict(run_index=i, decoded_unicode=t, x=12, y=y, unknown_glyphs=0,
                 glyphs=[dict(unknown=False)]) for i, (t, y) in enumerate([('ka', 20), ('kha', 10)])]
    page = dict(page_id='destination', printed_page=12, visible_body_sha256=annotations.digest('kakha'),
                source_faithful_decoded_text='kakha', representative_source=dict(
                    canonical_url='https://example.test/pdf', source_sha256=sha),
                positioned_page=dict(positioned_text_runs=runs))
    path = tmp_path/'destination.json.gz'
    path.write_bytes(gzip.compress(json.dumps(page).encode()))
    span = dict(canonical_object=path.name, representative_pdf_sha256=sha,
                representative_pdf_url=page['representative_source']['canonical_url'],
                visible_body_sha256=page['visible_body_sha256'], loc_run_indices=[0, 1],
                homonym_run_indices=[], run_start=0, run_end_exclusive=2)
    proof = dict(entry_id='badw:pdf:destination:0', headword=dict(loc='ka\nkha', source_loc='kakha'),
                 homonym='', entry_start_source_span=span, printed_page=12,
                 canonical_object_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    a = claim(p, kind='cross_reference_target', ranges=[dict(start=0,end=len(text),literal=text)])
    a['claim'] = dict(occurrence_id='xref', source_target_url=None, source_target_label='ka kha',
                      lemma='ka\nkha', homonym=None, basis='reviewed_printed_wrapped_headword', destination_heading=proof)
    if compound:
        page['positioned_page']['positioned_text_runs'][0]['decoded_unicode'] = 'ka '
        page['positioned_page']['positioned_text_runs'][1]['y'] = 20
        page['source_faithful_decoded_text'] = 'ka kha'
        page['visible_body_sha256'] = annotations.digest('ka kha')
        span['visible_body_sha256'] = page['visible_body_sha256']
        path.write_bytes(gzip.compress(json.dumps(page).encode()))
        proof['canonical_object_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        proof['headword'] = dict(loc='ka kha', source_loc='ka kha')
        a['claim'].update(source_target_label='ka-kha', lemma='ka kha',
                          basis='reviewed_printed_compound_headword')
    base = prediction(p)
    base['nodes'].append(dict(id='xref',kind='cross_reference',start=0,end=len(text),parent='root'))
    base['original_structure'] = dict(loc_headword='other', visual_lines=copy.deepcopy(p['source']['visual_lines']),
        candidates=dict(cross_references=[dict(visual_start=0,visual_end=len(text),target_label_candidate=a['claim']['source_target_label'])]))
    return p, a, base, page, path


@pytest.mark.parametrize('compound', [False, True])
def test_wrapped_heading_validated_overlay_preserves_source_and_identity(tmp_path, compound):
    p, a, base, _, _ = wrapped_fixture(tmp_path, compound)
    before = copy.deepcopy((p, a, base))
    result = annotations.apply_validated_annotations(p, base, run(tmp_path, p, [a]))
    target = result['reviewed_cross_reference_targets']['xref']
    assert target['lemma'] == ('ka kha' if compound else 'ka\nkha')
    assert target['destination_heading'] == a['claim']['destination_heading']
    assert result['nodes'] == base['nodes'] and result['original_structure'] == base['original_structure']
    assert (p, a, base) == before
    for status in ('candidate', 'rejected'):
        inactive = copy.deepcopy(a); inactive['status'] = status
        assert not annotations.apply_validated_annotations(p,base,run(tmp_path,p,[inactive]))['reviewed_cross_reference_targets']


@pytest.mark.parametrize('fault', ['canonical_hash','pdf_hash','entry_id','printed_page','source_loc',
    'heading','homonym','homonym_runs','run_order','run_bounds','index_type','body_hash',
    'source_url','geometry','unknown','run_identity','label','source_homonym','source_url_claim','extra_field'])
@pytest.mark.parametrize('compound', [False, True])
def test_wrapped_heading_proof_fails_closed(tmp_path, fault, compound):
    import gzip
    import json
    p, a, _, page, path = wrapped_fixture(tmp_path, compound)
    c = a['claim']; d = c['destination_heading']; s = d['entry_start_source_span']
    if fault == 'canonical_hash': d['canonical_object_sha256'] = '0'*64
    elif fault == 'pdf_hash': s['representative_pdf_sha256'] = '0'*64
    elif fault == 'entry_id': d['entry_id'] = 'wrong'
    elif fault == 'printed_page': d['printed_page'] = 13
    elif fault == 'source_loc': d['headword']['source_loc'] = 'incorrect'
    elif fault == 'heading': c['lemma'] = d['headword']['loc'] = 'ka\nkhu'
    elif fault == 'homonym': d['homonym'] = '1'
    elif fault == 'homonym_runs': s['homonym_run_indices'] = [0]
    elif fault == 'run_order': s['loc_run_indices'] = [1,0]
    elif fault == 'run_bounds': s['loc_run_indices'] = [0,2]
    elif fault == 'index_type': s['loc_run_indices'] = [False,1]
    elif fault == 'body_hash': s['visible_body_sha256'] = '0'*64
    elif fault == 'source_url': s['representative_pdf_url'] = 'other'
    elif fault == 'label': c['source_target_label'] = 'ka khu'
    elif fault == 'source_homonym': c['homonym'] = '1'
    elif fault == 'source_url_claim': c['source_target_url'] = 'url'
    elif fault == 'extra_field': c['unexpected'] = 'x'
    else:
        r = page['positioned_page']['positioned_text_runs'][0]
        if fault == 'geometry': r.pop('x')
        if fault == 'unknown': r['glyphs'][0]['unknown'] = True
        if fault == 'run_identity': r['run_index'] = 8
        path.write_bytes(gzip.compress(json.dumps(page).encode()))
        d['canonical_object_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises((ValueError, FileNotFoundError)):
        run(tmp_path,p,[a])


def test_reviewed_editorial_member_whitespace_requires_exact_dom_and_preserves_source(tmp_path):
    from badw_article_parser import parse_database_article
    body = ('<div class="text"><span class="link">↑<a class="link lemma" '
            'href="/lemma/ka,%20ga%C2%A0ba/1">ka, ga\u00a0ba</a></span></div>').encode()
    sha, path = put(tmp_path, body)
    obj = dict(sha256=sha, object_path=path, final_url='https://wts-digital.badw.de/lemma/source/1')
    article = parse_database_article(body, source_metadata=dict(obj, delivery_type='database_article', valid_resource=True))
    text = article['article_source_text']
    p = dict(contract_version=annotations.PACKET_VERSION, identity=article['source_identifier'], source_kind='html',
        source=dict(source_object=obj, article_source_text=text), review_text=text,
        review_text_sha256=annotations.digest(text))
    raw = article['cross_references'][0]
    ref = dict(record_type='cross_reference', id='xref', target_label=raw['target_text'],
        target_url=raw['target_url'], source_spans=[dict(start=0, end=len(text))])
    base = prediction(p)
    base['original_records'] = [ref]
    base['nodes'].append(dict(id='refnode', kind='cross_reference', start=0, end=len(text), parent='root', lexical_record_id='xref'))
    a = claim(p, kind='cross_reference_target', ranges=[dict(start=0, end=len(text), literal=text)])
    a['claim'] = dict(occurrence_id='xref', source_target_url=raw['target_url'], source_target_label=raw['target_text'],
        lemma='ga ba', homonym=None, basis='reviewed_editorial_member_whitespace', member_ordinal=1)
    before = copy.deepcopy(base)
    accepted = run(tmp_path, p, [a])
    result = annotations.apply_validated_annotations(p, base, accepted)
    assert base == before and result['original_records'] == before['original_records']
    review = result['reviewed_cross_reference_targets']['xref']
    assert review['member_ordinal'] == 1 and review['homonym'] is None
    assert review['basis'] == a['claim']['basis'] and review['ranges'] == a['ranges']
    for field, value in [('member_ordinal', 0), ('member_ordinal', 2), ('member_ordinal', True),
                         ('lemma', 'ga pa'), ('homonym', '1'), ('source_target_label', 'other'),
                         ('source_target_url', 'https://other/lemma/ka/1')]:
        bad = copy.deepcopy(a)
        bad['claim'][field] = value
        with pytest.raises(ValueError, match='editorial member'):
            run(tmp_path, p, [bad])
    for status in ('candidate', 'rejected'):
        inactive = copy.deepcopy(a)
        inactive['status'] = status
        assert not annotations.apply_validated_annotations(p, base, run(tmp_path, p, [inactive]))['reviewed_cross_reference_targets']


def test_reviewed_nonprinting_extent_requires_bound_source_and_specific_basis(tmp_path, monkeypatch):
    from test_parse_badw_pdf_articles import nonprinting_fixture, _candidates
    import badw_pdf_reference_bridge as bridge
    lines, divisions, sources, runs = nonprinting_fixture(monkeypatch)
    p = packet(tmp_path, 'pdf')
    sources[0].update(p['source']['source_objects'][0], page_id='page')
    monkeypatch.setattr(bridge, 'page_runs', lambda *args: runs)
    text = '\n'.join(l['text'] for l in lines)
    p['source'].update(source_objects=sources, source_faithful_text=text, visual_lines=lines)
    p.update(review_text=text, review_text_sha256=annotations.digest(text))
    base = prediction(p)
    base['nodes'].append(dict(id='ref', kind='cross_reference', start=0, end=2, parent='root'))
    base['original_structure'] = dict(article_id=p['identity'], visual_lines=copy.deepcopy(lines),
        divisions=divisions, candidates=_candidates(lines, divisions))
    a = claim(p, kind='cross_reference_extent', ranges=[dict(start=0,end=len(text)-1,literal=text[:-1])])
    a['claim'] = dict(node_id='ref', previous_range=dict(start=0,end=2,literal='↓’'),
                      basis='reviewed_printed_nonprinting_bridge')
    original = copy.deepcopy(base)
    accepted = run(tmp_path,p,[a])
    result = annotations.apply_validated_annotations(p,base,accepted)
    assert base == original
    assert result['nodes'][1]['end'] == len(text)-1
    candidate, = result['original_structure']['candidates']['cross_references']
    assert candidate['target_candidates'][0]['nonprinting_bridge']['lexical_target'] == '’go ba’i lha'
    for basis in ('reviewed_printed_extent', 'reviewed_printed_terminal_letter'):
        other = copy.deepcopy(a); other['claim']['basis'] = basis
        with pytest.raises(ValueError, match='exact typographic support'):
            annotations.apply_validated_annotations(p,base,run(tmp_path,p,[other]))
    for damage in ('hash','old_extent','new_extent'):
        other = copy.deepcopy(a)
        if damage == 'hash': other['binding']['text_sha256'] = 'f'*64
        elif damage == 'old_extent': other['claim']['previous_range']['end'] = 3
        else: other['ranges'][0]['end'] -= 1
        with pytest.raises(ValueError):
            annotations.apply_validated_annotations(p,base,run(tmp_path,p,[other]))


def test_reviewed_arrow_contraction_preserves_independent_occurrence(tmp_path):
    from parse_badw_pdf_articles import _candidates
    p = packet(tmp_path, 'pdf')
    lines = p['source']['visual_lines'][:2]
    lines[0].update(text='↑ka,', span_index=0, printed_page=1, style_spans=[
        dict(start=0,end=1,style='regular',font_id='regular'),
        dict(start=1,end=3,style='italic',font_id='italic'),
        dict(start=3,end=4,style='regular',font_id='regular')])
    lines[1].update(text='↓kha', span_index=0, printed_page=1, style_spans=[
        dict(start=0,end=4,style='italic',font_id='italic')])
    text = '↑ka,\n↓kha'
    p['source'].update(source_faithful_text=text,visual_lines=lines)
    p.update(review_text=text,review_text_sha256=annotations.digest(text))
    divisions=[dict(start_line_index=0,end_line_index_exclusive=2)]
    candidates=_candidates(lines,divisions)
    first,second=candidates['cross_references']
    # Reproduce the frozen pre-repair comma-list extent without relying on
    # the repaired parser to manufacture the defect.
    first.update(visual_end=9,target_label_candidate=text[1:9],
        source_line_end=copy.deepcopy(second['source_line_end']),end_line_index=1,line_end=4)
    swallowed=copy.deepcopy(second['target_candidates'][0])
    swallowed.update(source_text='↓kha',visual_start=5,line_start=0)
    first['target_candidates'].append(swallowed)
    base=prediction(p)
    base['nodes'].extend([dict(id='ref',kind='cross_reference',start=0,end=9,parent='root'),
                         dict(id='second',kind='cross_reference',start=5,end=9,parent='root')])
    base['original_structure']=dict(article_id=p['identity'],visual_lines=copy.deepcopy(lines),
        divisions=divisions,candidates=candidates)
    a=claim(p,kind='cross_reference_extent',ranges=[dict(start=0,end=3,literal='↑ka')])
    a['claim']=dict(node_id='ref',previous_range=dict(start=0,end=9,literal=text),
                    basis='reviewed_printed_arrow_boundary')
    reviewed=run(tmp_path,p,[a])
    result=annotations.apply_validated_annotations(p,base,reviewed)
    assert result['nodes'][1]['end']==3
    assert result['nodes'][2]==base['nodes'][2]
    assert result['original_structure']['candidates']['cross_references'][1]==second
    assert p['review_text']==text and base['nodes'][1]['end']==9
    for mutation in ('node','page','division','target','prose'):
        changed=copy.deepcopy(base)
        c=changed['original_structure']['candidates']['cross_references']
        if mutation=='node': changed['nodes'].pop()
        elif mutation=='page': c[1]['source_line']['page_id']='other'
        elif mutation=='division': c[1]['division_index']=1
        elif mutation=='target': c[0]['target_candidates'][0]['source_text']='different'
        else: c[0]['target_candidates'].append(copy.deepcopy(swallowed))
        with pytest.raises(ValueError,match='independent arrow boundary'):
            annotations.apply_validated_annotations(p,changed,reviewed)
    for mutation in ('hash','extent','basis'):
        changed=copy.deepcopy(a)
        if mutation=='hash': changed['binding']['text_sha256']='0'*64
        elif mutation=='extent': changed['claim']['previous_range']['end']=8
        else: changed['claim']['basis']='reviewed_printed_extent'
        with pytest.raises(ValueError):run(tmp_path,p,[changed])


def test_upright_space_extent_requires_review_hash_and_exact_physical_support(tmp_path,monkeypatch):
    from test_parse_badw_pdf_articles import upright_space_fixture, _candidates
    fixture, lines, divisions, sources, runs = upright_space_fixture(monkeypatch)
    p=packet(tmp_path,'pdf')
    sources[0].update(p['source']['source_objects'][0],page_id=lines[0]['page_id'])
    text=lines[0]['text']; start=text.index('↓')
    old,=_candidates(lines,divisions)['cross_references']
    new,=_candidates(lines,divisions,upright_space_sources=sources)['cross_references']
    p['source'].update(source_objects=sources,source_faithful_text=text,visual_lines=lines)
    p.update(review_text=text,review_text_sha256=annotations.digest(text))
    base=prediction(p)
    base['nodes'].append(dict(id='ref',kind='cross_reference',start=start,end=old['visual_end'],parent='root'))
    base['original_structure']=dict(article_id=p['identity'],visual_lines=copy.deepcopy(lines),
        divisions=divisions,candidates=_candidates(lines,divisions))
    a=claim(p,kind='cross_reference_extent',ranges=[dict(start=start,end=new['visual_end'],literal=text[start:new['visual_end']])])
    a['claim']=dict(node_id='ref',previous_range=dict(start=start,end=old['visual_end'],literal=text[start:old['visual_end']]),basis='reviewed_printed_upright_space')
    original=copy.deepcopy(base)
    result=annotations.apply_validated_annotations(p,base,run(tmp_path,p,[a]))
    assert result['nodes'][-1]['end']==new['visual_end'] and base==original
    assert p['review_text']==text
    for damage in ('hash','old_extent','new_extent','basis','geometry'):
        other=copy.deepcopy(a)
        if damage=='hash': other['binding']['text_sha256']='f'*64
        elif damage=='old_extent': other['claim']['previous_range']['end']-=1
        elif damage=='new_extent': other['ranges'][0]['end']-=1
        elif damage=='basis': other['claim']['basis']='reviewed_printed_extent'
        else: runs[lines[0]['style_spans'][3]['first_run_index']]['glyphs'][0]['x']+=100
        with pytest.raises(ValueError):
            annotations.apply_validated_annotations(p,base,run(tmp_path,p,[other]))


def test_page_continuation_extent_requires_frozen_review_and_physical_support(tmp_path,monkeypatch):
    from test_parse_badw_pdf_articles import page_continuation_fixture, _candidates
    import badw_pdf_reference_bridge as bridge
    _,lines,divisions,sources,runs=page_continuation_fixture(monkeypatch)
    p=packet(tmp_path,'pdf')
    mock=p['source']['source_objects'][0]
    remapped={}
    for i,s in enumerate(sources):
        physical=runs[s['canonical_object']]
        page=tmp_path/f'page-{i}.json.gz'
        page.write_bytes(b'synthetic positioned provenance')
        s.update(pdf_sha256=mock['pdf_sha256'],canonical_object=page.name,
                 canonical_object_sha256=hashlib.sha256(page.read_bytes()).hexdigest())
        remapped[page.name]=physical
    monkeypatch.setattr(bridge,'page_runs',lambda canonical,*args:remapped[canonical])
    text='\n'.join(l['text'] for l in lines)
    old,=_candidates(lines,divisions)['cross_references']
    new,=_candidates(lines,divisions,page_continuation_sources=sources)['cross_references']
    start=old['visual_start']
    p['source'].update(source_objects=sources,source_faithful_text=text,visual_lines=lines)
    p.update(review_text=text,review_text_sha256=annotations.digest(text))
    base=prediction(p)
    base['nodes'].append(dict(id='ref',kind='cross_reference',start=start,end=old['visual_end'],parent='root'))
    base['original_structure']=dict(article_id=p['identity'],visual_lines=copy.deepcopy(lines),
        divisions=divisions,candidates=_candidates(lines,divisions))
    a=claim(p,kind='cross_reference_extent',ranges=[dict(start=start,end=new['visual_end'],literal=text[start:new['visual_end']])])
    a['claim']=dict(node_id='ref',previous_range=dict(start=start,end=old['visual_end'],literal=text[start:old['visual_end']]),basis='reviewed_printed_page_continuation')
    original=copy.deepcopy(base)
    result=annotations.apply_validated_annotations(p,base,run(tmp_path,p,[a]))
    assert result['nodes'][-1]['end']==new['visual_end'] and base==original
    assert p['review_text']==text
    for damage in ('hash','old_extent','new_extent','basis','geometry'):
        other=copy.deepcopy(a)
        if damage=='hash': other['binding']['text_sha256']='f'*64
        elif damage=='old_extent': other['claim']['previous_range']['end']-=1
        elif damage=='new_extent': other['ranges'][0]['end']-=1
        elif damage=='basis': other['claim']['basis']='reviewed_printed_extent'
        else:
            for r in remapped[sources[1]['canonical_object']].values():
                for g in r['glyphs']: g['y']-=200
        with pytest.raises(ValueError):
            annotations.apply_validated_annotations(p,base,run(tmp_path,p,[other]))


def editorial_variant_packet(tmp_path, literal='kiṅ śị', lemma='kiṅ śi'):
    from badw_article_parser import parse_database_article
    body = f'<div class="text"><span class="link">↑<a class="link lemma" href="/lemma/{literal}/1">{literal}</a></span>.</div>'.encode()
    sha, path = put(tmp_path, body)
    obj = dict(sha256=sha, object_path=path)
    article = parse_database_article(body, source_metadata=dict(obj,
        delivery_type='database_article', valid_resource=True))
    text = article['article_source_text']
    p = dict(contract_version=annotations.PACKET_VERSION, identity='variant-source',
        source_kind='html', source=dict(source_object=obj, article_source_text=text),
        review_text=text, review_text_sha256=annotations.digest(text))
    # Heading markup follows the actual editorial parser contract.
    destination = f'<span class="lemma"><span class="lem">{lemma}</span></span><div class="text">auch ker śiṅ.</div>'.encode()
    ds, dp = put(tmp_path, destination)
    ref = article['cross_references'][0]
    loc = ref['locator']
    start, end = loc['visible_text_start'], loc['visible_text_end']
    a = claim(p, kind='cross_reference_target', ranges=[dict(start=start, end=end, literal=text[start:end])])
    a['claim'] = dict(occurrence_id='xref', source_target_url=ref['target_url'],
        source_target_label=ref['target_text'], lemma=lemma, homonym='1',
        basis='reviewed_editorial_headword_variant', destination_heading=dict(
            sha256=ds, object_path=dp, source_url=f'https://wts-digital.badw.de/lemma/{lemma}/1'))
    return p, a


def test_editorial_headword_variant_requires_both_immutable_sources(tmp_path):
    p, a = editorial_variant_packet(tmp_path)
    assert run(tmp_path, p, [a])[0]['effective_status'] == 'accepted'
    base = prediction(p)
    span = a['ranges'][0]
    ref = dict(record_type='cross_reference', id='xref', target_url=a['claim']['source_target_url'],
               target_label='kiṅ śị', source_spans=[dict(start=span['start'], end=span['end'])])
    base['original_records'] = [ref]
    base['nodes'].append(dict(id='refnode', kind='cross_reference', parent='root',
        start=span['start'], end=span['end'], lexical_record_id='xref'))
    before = copy.deepcopy(base)
    result = annotations.apply_validated_annotations(p, base, run(tmp_path, p, [a]))
    assert base == before and result['original_records'] == before['original_records']
    assert result['nodes'] == before['nodes']
    review = result['reviewed_cross_reference_targets']['xref']
    assert review['literal'] == 'kiṅ śị' and review['lemma'] == 'kiṅ śi'
    assert review['destination_heading'] == a['claim']['destination_heading']
    for field, value in [('lemma', 'kiṅ śị'), ('homonym', '2'),
                         ('source_target_label', 'kiṅ śi'), ('source_target_url', 'https://other/')]:
        bad = copy.deepcopy(a)
        bad['claim'][field] = value
        with pytest.raises(ValueError):
            run(tmp_path, p, [bad])
    for field, value in [('sha256', '0'*64), ('object_path', '../escape'),
                         ('source_url', 'https://other/lemma/kiṅ śi/1')]:
        bad = copy.deepcopy(a)
        bad['claim']['destination_heading'][field] = value
        with pytest.raises(ValueError):
            run(tmp_path, p, [bad])
    bad = copy.deepcopy(a)
    bad['binding']['text_sha256'] = '0'*64
    with pytest.raises(ValueError):
        run(tmp_path, p, [bad])


@pytest.mark.parametrize('literal,lemma', [('dug-mo-ñuṅ', 'dug mo ñuṅ'),
                                         ('mu-stegs-pa', 'mu stegs pa')])
def test_compound_interpretation_requires_an_individual_bound_review(tmp_path, literal, lemma):
    p, row = editorial_variant_packet(tmp_path, literal, lemma)
    assert run(tmp_path, p, [row])[0]['effective_status'] == 'accepted'
    assert row['ranges'][0]['literal'] == '↑' + literal
    assert literal in p['review_text'] and lemma not in p['review_text']
    for field, value in [('source_target_label', lemma), ('lemma', literal), ('homonym', '2')]:
        bad = copy.deepcopy(row)
        bad['claim'][field] = value
        with pytest.raises(ValueError):
            run(tmp_path, p, [bad])


def test_real_compound_reviews_preserve_explicit_identity_and_reciprocal_evidence():
    import json
    rows = [json.loads(line) for line in
            (Path(__file__).resolve().parents[1]/'data/reviewed_badw_semantic_annotations.jsonl').read_text().splitlines()]
    reviews = [r for r in rows if r['annotation_id'].startswith('badw-reviewed-editorial-compound-')]
    assert len(reviews) == 3
    assert sorted(r['claim']['source_target_label'] for r in reviews) == ['dug-mo-ñuṅ', 'dug-mo-ñuṅ', 'mu-stegs-pa']
    for row in reviews:
        assert row['claim']['basis'] == 'reviewed_editorial_headword_variant'
        assert row['claim']['homonym'] == '1'
        assert row['ranges'][0]['literal'] == '↓' + row['claim']['source_target_label']
        assert len(row['claim']['destination_heading']['sha256']) == 64
        assert 'independently' in row['review']['evidence']
        assert 'not a parser defect' in row['review']['evidence']
        assert 'No general hyphen-to-space' in row['review']['evidence']


def misplaced_arrow_packet(tmp_path):
    p = packet(tmp_path, 'pdf')
    text = '↑fut. bkru'
    line = dict(text=text, page_id='page-1', printed_page=170, first_x=339., y=162.,
        run_start=0, run_end_exclusive=10, style_spans=[
            dict(start=0,end=6,style='regular',family='TGaramond',font_id='regular'),
            dict(start=6,end=10,style='italic',family='TGaramond',font_id='italic')])
    p['source'].update(source_faithful_text=text,visual_lines=[line])
    p.update(review_text=text,review_text_sha256=annotations.digest(text))
    body='<span class="lemma"><span class="lem">bkru</span></span><div class="text">waschen <span class="link">↓<a class="link lemma" href="/lemma/’khrud/1">’khrud</a></span>.</div>'.encode()
    sha,path=put(tmp_path,body)
    a=claim(p,kind='cross_reference_target',ranges=[dict(start=0,end=4,literal='↑fut'),dict(start=6,end=10,literal='bkru')])
    a['claim']=dict(occurrence_id='ref',source_target_url=None,source_target_label='fut',lemma='bkru',homonym=None,source_headword='’khrud',basis='reviewed_printed_misplaced_arrow',destination_heading=dict(sha256=sha,object_path=path,source_url='https://wts-digital.badw.de/lemma/bkru/1'))
    return p,a


def test_printed_misplaced_arrow_preserves_literal_extent_and_requires_reciprocal_evidence(tmp_path):
    p,a=misplaced_arrow_packet(tmp_path)
    base=prediction(p)
    candidate=dict(visual_start=0,visual_end=4,target_label_candidate='fut')
    base['nodes'].append(dict(id='ref',kind='cross_reference',start=0,end=4,parent='root'))
    base['original_structure']=dict(loc_headword='’khrud',visual_lines=copy.deepcopy(p['source']['visual_lines']),candidates=dict(cross_references=[candidate]))
    before=copy.deepcopy((p,base))
    result=annotations.apply_validated_annotations(p,base,run(tmp_path,p,[a]))
    assert (p,base)==before
    assert result['nodes']==base['nodes']
    assert result['reviewed_cross_reference_targets']['ref']['literal']=='fut'
    for fault in ('hash','range','font','geometry','line','reciprocal','destination'):
        q,b=copy.deepcopy((p,a))
        if fault=='hash': b['binding']['text_sha256']='f'*64
        elif fault=='range': b['ranges'][1]['end']-=1
        elif fault=='font': q['source']['visual_lines'][0]['style_spans'][1]['style']='regular'
        elif fault=='geometry': q['source']['visual_lines'][0].pop('first_x')
        elif fault=='line': q['source']['visual_lines'][0]['text']='↑fut.'
        elif fault=='reciprocal': b['claim']['source_headword']='other'
        else: b['claim']['destination_heading']['sha256']='f'*64
        # Rebind changed physical evidence to test structural gates themselves.
        if fault in ('font','geometry','line'): b['binding']=annotations.binding(q);b['physical_selectors']=annotations.physical_selectors(q,b['ranges'])
        with pytest.raises(ValueError): run(tmp_path,q,[b])


@pytest.mark.parametrize('separator',['. ↑','. deutscher Text ','.\n','. ⟦UNKNOWN:ink⟧ '])
def test_printed_misplaced_arrow_never_bridges_prose_other_arrows_or_unknown_ink(tmp_path,separator):
    p,a=misplaced_arrow_packet(tmp_path)
    text='↑fut'+separator+'bkru'
    start=4+len(separator)
    ranges=[dict(start=0,end=4,literal='↑fut'),dict(start=start,end=len(text),literal='bkru')]
    with pytest.raises(ValueError):
        annotations.printed_misplaced_arrow(a['claim'],ranges,text,p['source']['visual_lines'])


def test_real_khrud_review_retains_both_source_ranges_and_print_evidence():
    import json
    rows=[json.loads(l) for l in (Path(__file__).resolve().parents[1]/'data/reviewed_badw_semantic_annotations.jsonl').read_text().splitlines()]
    row=next(r for r in rows if r['annotation_id']=='badw-reviewed-printed-misplaced-arrow-khrud')
    assert row['ranges']==[dict(start=13,end=17,literal='↑fut'),dict(start=19,end=23,literal='bkru')]
    assert row['claim']['basis']=='reviewed_printed_misplaced_arrow'
    assert row['claim']['homonym'] is None
    assert row['binding']['text_sha256']=='60b17485c43eaa772ad81f6553486cb524e990569fb4ddc3ea4b34dcd1e4d66d'
    assert 'printed p. 170' in row['review']['evidence']


@pytest.mark.parametrize('label', ['ka kha', 'ka--kha', 'ka-kha ', 'ka- kha', '~kha', 'ka-\nkha'])
def test_printed_compound_requires_exact_individually_reviewed_spelling(tmp_path, label):
    p, a, _, _, _ = wrapped_fixture(tmp_path, compound=True)
    a['claim']['source_target_label'] = label
    with pytest.raises(ValueError):
        run(tmp_path, p, [a])


def test_real_printed_gyad_mo_review_retains_unnumbered_identity_and_extent():
    import json
    rows = [json.loads(line) for line in (Path(__file__).resolve().parents[1] /
            'data/reviewed_badw_semantic_annotations.jsonl').read_text().splitlines()]
    a, = [r for r in rows if r['annotation_id'] == 'badw-reviewed-printed-compound-gyad-mo']
    assert a['ranges'] == [dict(start=11, end=19, literal='↑gyad-mo')]
    assert a['claim']['basis'] == 'reviewed_printed_compound_headword'
    assert a['claim']['source_target_label'] == 'gyad-mo'
    assert a['claim']['lemma'] == 'gyad mo'
    assert a['claim']['homonym'] is None
    assert a['claim']['destination_heading']['homonym'] == ''
    assert 'Neb 313' in a['review']['evidence']


def reciprocal_fixture(tmp_path):
    import gzip, json
    from test_extract_badw_pdf_entries import _page
    from extract_badw_pdf_entries import extract_page
    p = packet(tmp_path, 'pdf')
    text = ' pf. zu ↓ka zusammenziehen.'
    p['review_text'] = p['source']['source_faithful_text'] = text
    p['review_text_sha256'] = annotations.digest(text)
    line = p['source']['visual_lines'][0]
    line['text'] = text
    line['style_spans'][0]['end'] = len(text)
    p['source']['visual_lines'] = [line]
    page = _page()
    page['representative_source']['source_sha256'] = p['source']['source_objects'][0]['pdf_sha256']
    runs = page['positioned_page']['positioned_text_runs']
    runs[4]['decoded_unicode'] = ' pf. ↑bcum '
    page['source_faithful_decoded_text'] = ''.join(r['decoded_unicode'] for r in runs)
    page['visible_body_sha256'] = annotations.digest(page['source_faithful_decoded_text'])
    path = tmp_path/'destination.json.gz'
    path.write_bytes(gzip.compress(json.dumps(page).encode()))
    destination = extract_page(page, path.name)[0][0]
    proof = dict(entry_id=destination['id'], headword=dict(loc='ka', source_loc='ka', tibetan='ཀ'),
        homonym='1', entry_start_source_span=destination['source_span'], printed_page=7,
        canonical_object_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        reciprocal_passage=dict(run_start=4, run_end_exclusive=5, literal=' pf. ↑bcum '))
    a = claim(p, kind='cross_reference_target', ranges=[dict(start=8,end=11,literal='↓ka')])
    a['claim'] = dict(occurrence_id='xref', source_headword='bcum', source_target_url=None,
        source_target_label='ka', lemma='ka', homonym='1',
        basis='reviewed_printed_reciprocal_perfect', destination_heading=proof)
    base = prediction(p)
    base['nodes'].append(dict(id='xref',kind='cross_reference',start=8,end=11,parent='root'))
    base['original_structure'] = dict(loc_headword='bcum',visual_lines=copy.deepcopy(p['source']['visual_lines']),
        candidates=dict(cross_references=[dict(visual_start=8,visual_end=11,target_label_candidate='ka')]))
    return p,a,base,page,path


def test_reviewed_reciprocal_perfect_retains_numbered_identity_and_source(tmp_path):
    p,a,base,_,_ = reciprocal_fixture(tmp_path)
    before = copy.deepcopy((p,a,base))
    accepted = run(tmp_path,p,[a])
    result = annotations.apply_validated_annotations(p,base,accepted)
    assert result['reviewed_cross_reference_targets']['xref']['homonym'] == '1'
    assert result['nodes'] == base['nodes'] and result['original_structure'] == base['original_structure']
    assert (p,a,base) == before


@pytest.mark.parametrize('marker,prefix,offset', [('↓',' ',0), ('↑',' ',0), ('↑',', ',2)])
def test_reciprocal_directions_and_exact_shared_run_offset(tmp_path,marker,prefix,offset):
    import gzip,json
    p,a,_,page,path = reciprocal_fixture(tmp_path)
    p['review_text'] = p['review_text'].replace('↓',marker)
    p['source']['source_faithful_text'] = p['review_text']
    p['source']['visual_lines'][0]['text'] = p['review_text']
    p['review_text_sha256'] = annotations.digest(p['review_text'])
    a['ranges'][0]['literal'] = marker+'ka'
    a['binding'] = annotations.binding(p)
    a['physical_selectors'] = annotations.physical_selectors(p,a['ranges'])
    literal = prefix+'pf. '+{'↓':'↑','↑':'↓'}[marker]+'bcum '
    page['positioned_page']['positioned_text_runs'][4]['decoded_unicode'] = literal
    page['source_faithful_decoded_text'] = ''.join(r['decoded_unicode'] for r in page['positioned_page']['positioned_text_runs'])
    page['visible_body_sha256'] = annotations.digest(page['source_faithful_decoded_text'])
    path.write_bytes(gzip.compress(json.dumps(page).encode()))
    proof = a['claim']['destination_heading']
    proof['canonical_object_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    proof['entry_start_source_span']['visible_body_sha256'] = page['visible_body_sha256']
    proof['reciprocal_passage'].update(literal=literal,run_start_offset=offset)
    before = copy.deepcopy((p,a,page))
    assert run(tmp_path,p,[a])[0]['effective_status']=='accepted'
    assert (p,a,page)==before


@pytest.mark.parametrize('literal,offset,marker', [
    (', pf. ↓bcum',0,'↑'), (', pf. ↓bcum',1,'↑'),
    (', pf. ↓bcum',True,'↑'), (', pf. ↓bcum',2,'↓'),
    ('; pf. ↓bcum',2,'↑'), ('x pf. ↓bcum',2,'↑'),
    (', pf. ↓bcum prose',2,'↑'), (', pf. ↓¹bcum',2,'↑'),
    (', pf. ↓bcum',-1,'↑'), (', pf. ↓bcum',200,'↑'),
])
def test_reciprocal_offset_and_direction_do_not_guess(literal,offset,marker):
    assert not annotations.reciprocal_perfect_passage(
        dict(literal=literal,run_start_offset=offset),'bcum',marker)


@pytest.mark.parametrize('fault', ['hash','pdf','id','homonym','heading','span','page','prefix',
    'literal','source','passage','bounds','unknown','geometry','body','font','unnumbered'])
def test_reciprocal_perfect_proof_fails_closed(tmp_path,fault):
    import gzip,json
    p,a,_,page,path = reciprocal_fixture(tmp_path)
    c=a['claim'];d=c['destination_heading'];r=page['positioned_page']['positioned_text_runs']
    if fault=='hash': d['canonical_object_sha256']='0'*64
    elif fault=='pdf': d['entry_start_source_span']['representative_pdf_sha256']='0'*64
    elif fault=='id': d['entry_id']='other'
    elif fault=='homonym': c['homonym']='2'
    elif fault=='heading': d['headword']['tibetan']='ཁ'
    elif fault=='span': d['entry_start_source_span']['run_end_exclusive']+=1
    elif fault=='page': d['printed_page']=8
    elif fault=='prefix': p['review_text']=' xx. zu ↓ka zusammenziehen.';p['review_text_sha256']=annotations.digest(p['review_text'])
    elif fault=='literal': a['ranges'][0]['literal']='↑ka'
    elif fault=='source': c['source_headword']='other'
    elif fault=='passage': d['reciprocal_passage']['literal']=' pf. ↑other '
    elif fault=='bounds': d['reciprocal_passage']['run_end_exclusive']=6
    elif fault=='unknown': r[4]['glyphs']=[dict(unknown=True,cid_hex='0000',glyph_signature='a'*64)]
    elif fault=='geometry': r[4]['x']=None
    elif fault=='body': page['visible_body_sha256']='0'*64
    elif fault=='font': r[2]['font_id']='i'
    elif fault=='unnumbered': r[2]['decoded_unicode']=''
    path.write_bytes(gzip.compress(json.dumps(page).encode()))
    if fault!='hash': d['canonical_object_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises((ValueError,FileNotFoundError,TypeError)):
        run(tmp_path,p,[a])


def test_real_bcum_reciprocal_review_preserves_exact_source_and_numbered_destination():
    import json
    rows = [json.loads(line) for line in (Path(__file__).resolve().parents[1] /
            'data/reviewed_badw_semantic_annotations.jsonl').read_text().splitlines()]
    a, = [r for r in rows if r['annotation_id'] == 'badw-reviewed-reciprocal-perfect-bcum-jum-1']
    assert a['ranges'] == [dict(start=8, end=13, literal='↓’jum')]
    assert a['binding']['text_sha256'] == '6145720d854f7789b55540d8ba34b7d1fa75794346ed6f48492d9ec4d0da9a71'
    c = a['claim']
    assert c['occurrence_id'] == 'n8'
    assert c['basis'] == 'reviewed_printed_reciprocal_perfect'
    assert c['source_headword'] == 'bcum'
    assert c['source_target_label'] == c['lemma'] == '’jum'
    assert c['homonym'] == c['destination_heading']['homonym'] == '1'
    assert c['destination_heading']['printed_page'] == 394
    assert c['destination_heading']['reciprocal_passage'] == dict(
        run_start=239, run_end_exclusive=247, literal=' pf. ↑bcum ')


@pytest.mark.parametrize("name,node,target,homonym,end,page,runs", [
    ("gas", "n48", "’gas", "1", 13, 368, (72,79)),
    ("groṅs", "n50", "’groṅs", "1", 15, 401, (299,307)),
    ("khol", "n17", "’khol", "2", 14, 155, (835,840)),
])
def test_real_reciprocal_family_preserves_source_and_numbered_destination(name,node,target,homonym,end,page,runs):
    import json
    rows = [json.loads(line) for line in (Path(__file__).resolve().parents[1] /
            'data/reviewed_badw_semantic_annotations.jsonl').read_text().splitlines()]
    a, = [r for r in rows if r['annotation_id'] ==
          'badw-reviewed-reciprocal-perfect-'+name+'-'+target[1:]+'-'+homonym]
    assert a['ranges'] == [dict(start=8,end=end,literal='↓'+target)]
    c=a['claim']; proof=c['destination_heading']
    assert c['occurrence_id']==node and c['source_headword']==name
    assert c['lemma']==c['source_target_label']==target
    assert c['homonym']==proof['homonym']==homonym
    assert proof['printed_page']==page
    passage=proof['reciprocal_passage']
    assert (passage['run_start'],passage['run_end_exclusive'])==runs
    assert passage['literal'].strip()=='pf. ↑'+name


def test_real_brgyas_reciprocal_preserves_shared_run_and_upward_source():
    import json
    rows = [json.loads(line) for line in (Path(__file__).resolve().parents[1] /
            'data/reviewed_badw_semantic_annotations.jsonl').read_text().splitlines()]
    a, = [r for r in rows if r['annotation_id'] == 'badw-reviewed-reciprocal-perfect-brgyas-brgya-2']
    assert a['ranges'] == [dict(start=8,end=14,literal='↑brgya')]
    c=a['claim']; proof=c['destination_heading']
    assert c['occurrence_id']=='n4' and c['source_headword']=='brgyas'
    assert c['lemma']==c['source_target_label']=='brgya'
    assert c['homonym']==proof['homonym']=='2'
    assert proof['printed_page']==503
    assert proof['reciprocal_passage']==dict(run_start=1462,run_end_exclusive=1471,
        literal=', pf. ↓brgyas',run_start_offset=2)
    assert annotations.reciprocal_perfect_passage(proof['reciprocal_passage'],'brgyas','↑')
