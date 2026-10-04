"""Synthetic source-anchored structures; no ownership or language guessing."""
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from badw_source_components import lexical_clauses, quoted_spans
from badw_article_parser import parse_database_article, _field_envelope
from benchmark_badw_structure import boundary_diagnostic
from project_badw_structural_candidates import enrich
from parse_badw_pdf_articles import _candidates, _structure


def test_lexical_delimiters_preserve_apparatus_quotes_and_unicode():
    text = ' ka (r.ka; r. kha) „Wort; ṅa“ (A); śa (B). '
    clauses, diagnostics = lexical_clauses(text, 0, len(text))
    assert [c['source_text'] for c in clauses] == [
        'ka (r.ka; r. kha) „Wort; ṅa“ (A)', 'śa (B).']
    assert diagnostics == []
    assert quoted_spans(text, 0, len(text))[0]['source_text'] == '„Wort; ṅa“'
    for clause in clauses:
        assert text[clause['start']:clause['end']] == clause['source_text']


def test_incomplete_delimiters_are_not_discarded():
    text = 'ka (A; śa'
    clauses, diagnostics = lexical_clauses(text, 0, len(text))
    assert clauses[0]['source_text'] == text
    assert diagnostics == [{'offset': len(text), 'reason': 'unclosed_delimiter'}]
    with pytest.raises(ValueError):
        lexical_clauses(text, -1, len(text))


def test_nested_quotation_semicolon_is_not_a_lexical_boundary():
    text = 'ka „außen «innen; noch innen»; außen“ (A); kha (B)'
    clauses, diagnostics = lexical_clauses(text, 0, len(text))
    assert [c['source_text'] for c in clauses] == [
        'ka „außen «innen; noch innen»; außen“ (A)', 'kha (B)']
    assert diagnostics == []
    assert quoted_spans(text, 0, len(text))[0]['source_text'] == '„außen «innen; noch innen»; außen“'
    with pytest.raises(ValueError):
        quoted_spans(text, 0, len(text) + 1)


def test_german_single_quotation_and_tibetan_apostrophe_are_distinct():
    text = '’khor „außen ‚innen; innen‘ außen“ (A); kha (B)'
    clauses, diagnostics = lexical_clauses(text, 0, len(text))
    assert diagnostics == []
    assert [c['source_text'] for c in clauses] == [
        '’khor „außen ‚innen; innen‘ außen“ (A)', 'kha (B)']
    assert quoted_spans(text, 0, len(text))[0]['source_text'] == '„außen ‚innen; innen‘ außen“'


def article():
    body = '''<div class="text"><span class="lemma"><span class="lem">ka</span><sup>2</sup></span>
<span class="lemtib">ཀ་</span><div class="bedeutung">Sache <tib>ka</tib> <skt>kāya</skt>.
<div class="beleg-all"><span class="tibetisch"><tib>ka</tib> (r.ka) <tib>ṅa</tib></span>
<span class="deutsch">„Ding“</span><span class="stelle">(A: 1)</span></div></div>
<div class="lex">Lex. <tib>ka</tib> ≅ <tib>ṅa</tib> „Wort; Sache“ (<span class="textsiglum">A<span class="infotext">hidden</span></span>); <skt>śa</skt> (B).</div>
<span class="link">↓<a href="/lemma/kha/3">kha</a></span></div>'''.encode()
    metadata = dict(delivery_type='database_article', valid_resource=True,
                    sha256=hashlib.sha256(body).hexdigest(),
                    final_url='https://wts-digital.badw.de/lemma/ka/2')
    return parse_database_article(body, source_metadata=metadata)


def test_multi_segment_html_fields_and_lex_structure_are_lossless():
    a = article()
    assert a == article()
    example = a['examples'][0]
    assert example['tibetan']['source_text'] == 'ka (r.ka) ṅa'
    assert [s['source_text'] for s in example['tibetan_segments']] == ['ka', 'ṅa']
    assert a['homonym'] == '2'
    assert 'hidden' not in a['article_source_text']
    block = a['lexical_blocks'][0]
    assert len(block['clauses']) == 2
    assert block['clauses'][0]['german_quotation_candidates'][0]['source_text'] == '„Wort; Sache“'
    assert block['clauses'][1]['tagged_fields']['sanskrit'][0]['source_text'] == 'śa'
    assert a['cross_references'][0]['target_homonym'] == '3'
    assert a['cross_references'][0]['marker'] == '↓'
    for field in [example['tibetan'], *a['sanskrit'], *a['tibetan_segments'], *a['cross_references']]:
        loc = field['locator']
        assert a['article_source_text'][loc['visible_text_start']:loc['visible_text_end']] == field['source_text']


def test_untagged_envelope_gaps_do_not_claim_a_language():
    text = 'ka German ṅa'
    fields = [{'locator': {'visible_text_start': 0, 'visible_text_end': 2}},
              {'locator': {'visible_text_start': 10, 'visible_text_end': 12}}]
    envelope = _field_envelope(fields, text)
    assert envelope['source_text'] == text
    assert envelope['untagged_gaps'] == [{'source_text': ' German ',
        'locator': {'visible_text_start': 2, 'visible_text_end': 10},
        'status': 'untagged_language_unresolved'}]


def test_source_enrichment_adds_typed_fields_without_ownership():
    a = article()
    text = a['article_source_text']
    nodes = [dict(id='root', kind='source_division', start=0, end=len(text), parent=None)]
    for kind, field in [('definition', a['meanings'][0]), ('example', a['examples'][0])]:
        loc = field['locator']
        nodes.append(dict(id=kind, kind=kind, start=loc['visible_text_start'],
                          end=loc['visible_text_end'], parent='root'))
    assert enrich(nodes, text, article=a) == []
    assert {n['kind'] for n in nodes} >= {'lexical_parallel', 'translation', 'sanskrit', 'tibetan', 'cross_reference'}
    assert all(n.get('association_status') == 'source_containment_only' for n in nodes[3:])
    a['article_source_text'] += 'changed'
    with pytest.raises(ValueError, match='differs'):
        enrich(nodes, text, article=a)


def test_boundary_diagnostic_only_trims_terminal_whitespace():
    text = ' ka\n ṅa '
    nodes = [dict(kind='definition', start=0, end=len(text)),
             dict(kind='definition', start=1, end=len(text)-1),
             dict(kind='definition', start=0, end=1)]
    keys, collisions, empty = boundary_diagnostic(nodes, text)
    assert keys == {('definition', 1, 7)}
    assert (collisions, empty) == (1, 1)
    assert text[1:7] == 'ka\n ṅa'


def test_pdf_source_components_project_without_ownership_or_language_guesses():
    text = 'Lex. ka „Sache“ (A); skt. śa'
    start = text.index('śa')
    lines = [{'text': text, 'page_id': 'p', 'printed_page': 1,
              'span_index': 0, 'run_start': 0, 'run_end_exclusive': 1,
              'style_spans': [{'start': 0, 'end': start, 'style': 'regular'},
                              {'start': start, 'end': len(text), 'style': 'italic',
                               'font_id': 'font'}]}]
    divisions, _ = _structure(lines)
    structure = {'visual_lines': lines, 'candidates': _candidates(lines, divisions)}
    nodes = [dict(id='root', kind='source_division', start=0, end=len(text), parent=None)]
    assert enrich(nodes, text, structure=structure) == []
    assert [text[n['start']:n['end']] for n in nodes if n['kind'] == 'sanskrit'] == ['śa']
    assert len([n for n in nodes if n['kind'] == 'lexical_parallel']) == 2
    assert all(n['association_status'] == 'source_containment_only' for n in nodes[1:])
    structure['candidates']['sanskrit'][0]['source_text'] = 'guessed'
    with pytest.raises(ValueError, match='differs'):
        enrich(nodes, text, structure=structure)
