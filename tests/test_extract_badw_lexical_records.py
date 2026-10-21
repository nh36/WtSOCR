from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from badw_article_parser import parse_database_article  # noqa: E402
from extract_badw_lexical_records import extract_article, extract_jsonl  # noqa: E402
from validate_lexical_record_contract import validate  # noqa: E402


ARTICLE_BYTES = (ROOT / "tests" / "fixtures" / "badw" / "article.html").read_bytes()
SOURCE = {
    "sha256": __import__("hashlib").sha256(ARTICLE_BYTES).hexdigest(),
    "delivery_type": "database_article",
    "valid_resource": True,
    "content_classification": "database_article",
    "final_url": "https://wts-digital.badw.de/lemma/ka/2",
}


def article() -> dict[str, object]:
    return parse_database_article(ARTICLE_BYTES, source_metadata=SOURCE)


def test_emits_source_faithful_semantic_records_without_bibliography_guesses() -> None:
    records = extract_article(article(), snapshot_id="snapshot", extraction_run_id="run")
    assert validate(records) == []
    entry = records[0]
    assert entry["layer"] == "badw_editorial"
    assert entry["headword"] == {"loc": "kā", "tibetan": "ཀ་"}
    assert entry["homonym"] == "2"
    senses = [record for record in records if record["record_type"] == "sense"]
    assert [sense["source_label"] for sense in senses] == ["1", "2"]
    assert "erste Bedeutung" in senses[0]["definition"]
    attestations = [record for record in records if record["record_type"] == "attestation"]
    assert len(attestations) == 1
    assert attestations[0]["association_status"] == "explicit"
    assert attestations[0]["tibetan"] == "ཀ་ཁ་"
    citations = [record for record in records if record["record_type"] == "citation"]
    assert len(citations) == 1
    assert citations[0]["siglum"] == "TS"
    assert [item["text"] for item in citations[0]["sigla"]] == ["TS"]
    assert citations[0]["authority_status"] == "unresolved"
    assert "bibliographic_source_id" not in citations[0]
    refs = [record for record in records if record["record_type"] == "cross_reference"]
    assert [(record["marker"], record["target_label"]) for record in refs] == [("↑", "kha"), ("↓", "ga")]
    assert all(span["field"] == "article_source_text" for record in records for span in record["source_spans"])
    source_text = article()["article_source_text"]
    assert all(
        source_text[span["start"]:span["end"]]
        for record in records
        for span in record["source_spans"]
    )


def test_multiple_sigla_keep_separate_exact_spans_without_scalar_guess() -> None:
    html = ARTICLE_BYTES.replace(
        b'<span class="stellenangabe">1.2a</span>',
        b'<span class="textsiglum info">LX<span class="infotext">Lexicon</span></span> '
        b'<span class="stellenangabe">1.2a</span>',
    )
    source = SOURCE | {"sha256": hashlib.sha256(html).hexdigest()}
    parsed = parse_database_article(html, source_metadata=source)
    records = extract_article(parsed, snapshot_id="snapshot", extraction_run_id="run")
    assert validate(records) == []
    citation = next(row for row in records if row["record_type"] == "citation")
    assert [item["text"] for item in citation["sigla"]] == ["TS", "LX"]
    assert "siglum" not in citation
    for item in citation["sigla"]:
        span = item["source_span"]
        assert parsed["article_source_text"][span["start"]:span["end"]] == item["text"]


def test_rejects_unlocated_or_out_of_order_citation_sigla() -> None:
    records = extract_article(article(), snapshot_id="snapshot", extraction_run_id="run")
    citation = next(row for row in records if row["record_type"] == "citation")
    citation["sigla"][0]["source_span"]["start"] = 0
    assert any("citation sigla" in error for error in validate(records))


def test_jsonl_emission_is_deterministic_and_keeps_structural_failures_as_diagnostics() -> None:
    good = article()
    broken = article()
    broken["lemma_field"] = None
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        input_path = root / "articles.jsonl"
        input_path.write_text("\n".join(json.dumps(value, ensure_ascii=False) for value in [broken, good]) + "\n", encoding="utf-8")
        paths = [(root / f"records-{number}.jsonl", root / f"diagnostics-{number}.jsonl", root / f"manifest-{number}.json") for number in (1, 2)]
        first = extract_jsonl(input_path, *paths[0], snapshot_id="fixture")
        second = extract_jsonl(input_path, *paths[1], snapshot_id="fixture")
        assert first == second == {"articles": 2, "diagnostics": 1, "records": 7, "snapshot_id": "fixture"}
        assert paths[0][0].read_bytes() == paths[1][0].read_bytes()
        assert paths[0][1].read_bytes() == paths[1][1].read_bytes()
        manifest = json.loads(paths[0][2].read_text(encoding="utf-8"))
        assert manifest["records_sha256"] == hashlib.sha256(paths[0][0].read_bytes()).hexdigest()
        assert manifest["diagnostics_sha256"] == hashlib.sha256(paths[0][1].read_bytes()).hexdigest()
        diagnostics = [json.loads(line) for line in paths[0][1].read_text(encoding="utf-8").splitlines()]
        assert diagnostics == [{"reason": "lemma lacks source_text", "source_identifier": "badw:https://wts-digital.badw.de/lemma/ka/2"}]


def test_shared_malformed_anchor_keeps_exact_individual_labels_without_url_identity():
    # A minimal article isolates the same malformed editorial shape found in
    # ka chen and kos sñuṅ; punctuation and qualifiers must fail closed.
    for content, expected in [
        ('↑<a class="link lemma" href="/lemma/ko sko, ↓sko cig pa/1">ko sko, ↓sko cig pa</a>', ['ko sko', 'sko cig pa']),
        ('↓<a href="/lemma/ka chen bźi, ↓/1">ka chen bźi, ↓</a><tib>bka’ chen</tib>', ['ka chen bźi', '']),
        ('↑<a href="/lemma/x/1">ko sko (?), ↓sko cig pa 2</a>', ['', '']),
    ]:
        body = ('<div class="text"><span class="link">'+content+'</span></div>').encode()
        parsed = parse_database_article(body, source_metadata=SOURCE | {'sha256':hashlib.sha256(body).hexdigest()})
        refs = parsed['cross_references']
        assert [r['target_text'] for r in refs] == expected
        assert all(r['target_url'] is None and r['target_homonym'] is None for r in refs)
        for ref in refs:
            loc = ref['locator']
            assert parsed['article_source_text'][loc['visible_text_start']:loc['visible_text_end']] == ref['source_text']


def test_empty_label_replay_preserves_identity_spans_and_fails_on_stale_source(tmp_path):
    import pytest
    from badw_article_parser import replay_empty_reference_labels
    body = b'<div class="text"><span class="link">\xe2\x86\x91<a href="/lemma/ka, ga/1">ka, \xe2\x86\x93ga</a></span></div>'
    sha = hashlib.sha256(body).hexdigest()
    source = SOURCE | {'sha256': sha, 'object_path': 'source.html'}
    (tmp_path/'source.html').write_bytes(body)
    parsed = parse_database_article(body, source_metadata=source)
    records = [dict(record_type='cross_reference', id=str(i), target_label=r['target_text'], target_url=None, source_spans=[dict(start=r['locator']['visible_text_start'], end=r['locator']['visible_text_end'])]) for i,r in enumerate(parsed['cross_references'])]
    original = [dict(r, target_label='', canonical_resolution={'status':'unresolved'})
                if r['record_type']=='cross_reference' else r for r in records]
    projection = dict(source_kind='html', source=dict(source_object=source,
                      article_source_text=parsed['article_source_text']), original_records=original)
    result = replay_empty_reference_labels(projection, tmp_path)
    recovered = [r for r in result['original_records'] if r['record_type']=='cross_reference']
    assert [r['target_label'] for r in recovered] == ['ka','ga']
    old = [r for r in original if r['record_type']=='cross_reference']
    assert [(r['id'],r['source_spans']) for r in recovered] == [(r['id'],r['source_spans']) for r in old]
    assert all('canonical_resolution' not in r for r in recovered)
    assert all(r['target_label']=='' for r in old)  # no mutation
    projection['source']['article_source_text'] += 'stale'
    with pytest.raises(ValueError,match='changed source text'):
        replay_empty_reference_labels(projection,tmp_path)
    (tmp_path/'source.html').write_bytes(body+b'changed')
    with pytest.raises(ValueError):
        replay_empty_reference_labels(projection,tmp_path)


def test_trailing_arrow_typed_sibling_is_separately_source_bound(tmp_path):
    from badw_article_parser import replay_empty_reference_labels
    from resolve_badw_cross_references import EntryIndex
    prefix = '<div class="text"><span class="link">↓<a class="link lemma" href="/lemma/ka chen bźi, ↓/1">ka chen bźi, ↓</a></span>'
    suffix = '</div>'
    for target, expected in [
        ('<tib>bka’ chen</tib>.', 'bka’ chen'),
        ('<tib>bka’ chen</tib>; sonst', 'bka’ chen'),
        ('<tib>bka’ chen</tib> und anderes', ''),
        (' <tib>bka’ chen</tib>.', ''),
        ('<i>bka’ chen</i>.', ''),
        ('<tib>bka’ chen (?)</tib>.', ''),
        ('<tib>bka’ chen 2</tib>.', ''),
        ('<tib>bka’ chen, ga</tib>.', ''),
        ('<tib><a href="/lemma/other/2">bka’ chen</a></tib>.', ''),
        ('<tib>bka’ chen</tib>', ''),
    ]:
        body = (prefix + target + suffix).encode()
        source = SOURCE | {'sha256':hashlib.sha256(body).hexdigest(), 'object_path':'source.html'}
        (tmp_path/'source.html').write_bytes(body)
        article = parse_database_article(body, source_metadata=source)
        refs = article['cross_references']
        assert len(refs) == 2
        ref = refs[1]
        assert ref['source_text'] == '↓' and ref['target_text'] == expected
        assert ref['target_url'] is None and ref['target_homonym'] is None
        if not expected:
            assert 'target_locator' not in ref
            continue
        loc = ref['locator']; span = dict(start=loc['visible_text_start'],end=loc['visible_text_end'])
        old = dict(id='frozen-arrow',record_type='cross_reference',marker='↓',target_label='',target_url=None,source_spans=[span],canonical_resolution={'status':'unresolved'})
        projection = dict(source_kind='html',source=dict(source_object=source,article_source_text=article['article_source_text']),original_records=[old])
        new, = replay_empty_reference_labels(projection,tmp_path)['original_records']
        assert new['id'] == old['id'] and new['source_spans'] == old['source_spans']
        assert old['target_label'] == '' and 'canonical_resolution' not in new
        target_loc = new['target_source_locator']
        assert article['article_source_text'][target_loc['visible_text_start']:target_loc['visible_text_end']] == expected
        assert target_loc['visible_text_start'] == span['end']
        index = EntryIndex([dict(record_type='entry',id='target',headword={'loc':expected},homonym='1')])
        resolution = index.resolve_manifestation(new)['canonical_resolution']
        assert resolution['status'] == 'resolved'
        assert resolution['target_parsing_evidence']['target_source_locator'] == target_loc


def test_html_comma_dom_evidence_replay_keeps_exact_source_and_accepted_records(tmp_path):
    from badw_article_parser import replay_empty_reference_labels
    from test_badw_dictionary_target_members import html_comma_fixture
    projection, ref=html_comma_fixture()
    # Replay the actual cached object through the frozen projection adapter.
    body=ARTICLE_BYTES.decode().replace(
        '<span class="link">↑<a class="link lemma" href="/lemma/kha/1">kha</a></span>',
        '<span class="link">↑<sup>2</sup><a class="link lemma" href="/lemma/ka, kha/2">ka, kha</a></span>').encode()
    (tmp_path/'source.html').write_bytes(body)
    projection['source']['source_object']=SOURCE | {'sha256':hashlib.sha256(body).hexdigest(),'object_path':'source.html'}
    proof=ref.pop('html_target_members')
    ref['canonical_resolution']={'status':'unresolved'}
    new=replay_empty_reference_labels(projection,tmp_path)['original_records'][1]
    assert new['html_target_members']==proof
    assert new['id']==ref['id'] and new['source_spans']==ref['source_spans']
    assert 'html_target_members' not in ref and 'canonical_resolution' not in new
    ref['canonical_resolution']={'status':'resolved','target_entry_id':'existing'}
    assert replay_empty_reference_labels(projection,tmp_path)==projection


def test_html_comma_parser_rejects_unbounded_or_untyped_qualifiers():
    for content in [
        '↑2<a href="/lemma/ka, kha/2">ka, kha</a>',
        '↑<sup>2</sup> <a href="/lemma/ka, kha/2">ka, kha</a>',
        '↑<a href="/lemma/ka, kha/2">ka, kha</a> (?)',
        '↑<a href="/lemma/ka, kha/2">ka, 2kha</a>',
        '↑<a href="/lemma/ka, kha/2">ka, <sup>2</sup>kha</a>',
        '↑<a href="/lemma/ka, kha/2">ka, kha (?)</a>',
        '↑<a href="/lemma/ka, kha/2">ka, </a>',
    ]:
        body=('<div class="text"><span class="link">'+content+'</span></div>').encode()
        parsed=parse_database_article(body,source_metadata=SOURCE | {'sha256':hashlib.sha256(body).hexdigest()})
        assert all('html_target_members' not in r for r in parsed['cross_references'])
