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
