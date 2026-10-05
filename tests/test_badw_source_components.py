"""Synthetic source-anchored structures; no ownership or language guessing."""
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from badw_source_components import lexical_clauses, quoted_spans, terminal_lexical_citation
from badw_article_parser import parse_database_article, _field_envelope
from benchmark_badw_structure import boundary_diagnostic
from project_badw_structural_candidates import enrich
from parse_badw_pdf_articles import _candidates, _structure


@pytest.mark.parametrize('content,expected', [
    ('Lex. <tib>ka</tib> (<span class="textsiglum">A</span>, <span class="textsiglum">B</span>).', '(A, B)'),
    ('Lex. <tib>ka</tib> (<span class="textsiglum">Be’uD</span> 221,3).', '(Be’uD 221,3)'),
    ('Lex. <tib>ka</tib> (<span class="textsiglum">Mvy</span> 6062, Abt. <tib>ka</tib>).', '(Mvy 6062, Abt. ka)'),
    ('Definition (<span class="textsiglum">Neb<span class="infotext">hidden (B)</span></span> 229).', '(Neb 229)'),
    ('Definition (auch so).', None),
    ('„Zitat (<span class="textsiglum">A</span>)“', None),
    ('Definition (<span class="textsiglum">A</span>', None),
])
def test_explicit_siglum_citations_without_stelle(content, expected):
    body = ('<div class="text"><span class="lem">ka</span><div class="lex">' + content + '</div></div>').encode()
    a = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    assert [c['source_text'] for c in a['citations']] == ([expected] if expected else [])
    for c in a['citations']:
        assert a['article_source_text'][c['locator']['visible_text_start']:c['locator']['visible_text_end']] == expected
        assert c['candidate_status'] == 'unresolved_source_citation_candidate'


@pytest.mark.parametrize('content,expected', [
    ('Eine Gottheit (Neb 229).', '(Neb 229)'),
    ('Eine Gottheit (auch so).', None),
    ('Eine Gottheit (r. ka).', None),
    ('Eine Gottheit „Name (Neb 229)“.', None),
    ('Eine Gottheit (Neb 229) und weitere Erklärung.', None),
    ('Eine Gottheit (Neb 229.', None),
])
def test_untagged_terminal_definition_citation_is_only_a_candidate(content, expected):
    body = ('<div class="text"><span class="lem">ka</span><div class="bedeutung">' + content + '</div></div>').encode()
    a = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    assert [c['source_text'] for c in a['citations']] == ([expected] if expected else [])
    assert all(c['candidate_status'] == 'unresolved_source_citation_candidate' for c in a['citations'])


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


@pytest.mark.parametrize('text,expected', [
    ('ka (Mim1 107).', '(Mim1 107)'),
    ('ka „Wort (A)“ (brDa)', '(brDa)'),
    ('ka (r.ka)', None), ('ka (metr.)', None),
    ('ka „Wort (A)“', None), ('ka (A) weiter', None),
    ('ka (A', None), ('ka (r. kha (A))', None),
    ('ka (auch)', None),
])
def test_terminal_lexical_citations_are_candidates_not_resolutions(text, expected):
    candidate = terminal_lexical_citation(text, 0, len(text))
    assert (candidate['source_text'] if candidate else None) == expected
    if candidate:
        assert text[candidate['start']:candidate['end']] == expected
        assert candidate['status'] == 'unresolved_source_citation_candidate'


def test_lexical_citation_projection_preserves_envelope_without_ownership_edges():
    a = article()
    text = a['article_source_text']
    nodes = [dict(id='n0', kind='source_division', start=0, end=len(text), parent=None)]
    enrich(nodes, text, article=a)
    citations = [n for n in nodes if n['kind'] == 'citation']
    assert [text[n['start']:n['end']] for n in citations] == ['(A)', '(B)']
    assert all(nodes[int(n['parent'][1:])]['kind'] == 'lexical_parallel' for n in citations)
    assert all(n['association_status'] == 'source_containment_only' for n in citations)
    assert all(n['candidate_status'] == 'unresolved_source_citation_candidate' for n in citations)


def test_explicit_metrical_qualifier_preserves_unicode_and_hidden_text_exclusion():
    body = '<div class="text"><span class="lem">ka</span><span class="beleg metr">(<span class="info">metr.<span class="infotext">hidden</span></span>)</span></div>'.encode()
    a = parse_database_article(body, source_metadata=dict(
        delivery_type='database_article', valid_resource=True,
        sha256=hashlib.sha256(body).hexdigest(), final_url='https://wts-digital.badw.de/lemma/ka/1'))
    assert a['qualifiers'][0]['source_text'] == '(metr.)'
    nodes = []
    enrich(nodes, a['article_source_text'], article=a)
    qualifier = next(n for n in nodes if n['kind'] == 'qualifier')
    assert a['article_source_text'][qualifier['start']:qualifier['end']] == '(metr.)'
    assert qualifier['parent'] is None


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


def test_lexical_clause_intersects_tags_without_losing_parent_provenance():
    body = '''<div class="text"><span class="lem">ka</span>
<div class="lex">Lex.<tib> ka </tib> (A);<skt> śa; ṅa </skt>(B).</div></div>'''.encode()
    a = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    block = a['lexical_blocks'][0]
    assert [f['source_text'] for c in block['clauses']
            for f in c['tagged_fields']['tibetan_segments']] == ['ka ']
    fields = [f for c in block['clauses'] for f in c['tagged_fields']['sanskrit']]
    assert [f['source_text'] for f in fields] == ['śa', 'ṅa ']
    assert block['sanskrit'][0]['source_text'] == ' śa; ṅa '
    for f in fields:
        assert f['parent_source_locator'] == block['sanskrit'][0]['locator']
        loc = f['locator']
        assert a['article_source_text'][loc['visible_text_start']:loc['visible_text_end']] == f['source_text']
        assert loc['derivation'] == 'source_clause_intersection'


def test_mixed_language_example_preserves_container_and_tagged_sanskrit():
    body = '''<div class="text"><span class="lem">ka</span>
<div class="beleg-all"><span class="tibetisch"><tib>gnas so</tib> ≅ <skt>viharati</skt></span>
<span class="deutsch">wohnt</span><span class="stelle">(A: 1)</span></div></div>'''.encode()
    a = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    example = a['examples'][0]
    assert example['tibetan']['source_text'] == 'gnas so ≅ viharati'
    assert example['tibetan_container_languages'] == ['sanskrit', 'tibetan']
    assert [s['source_text'] for s in example['sanskrit']] == ['viharati']
    field = example['sanskrit'][0]
    loc = field['locator']
    assert a['article_source_text'][loc['visible_text_start']:loc['visible_text_end']] == 'viharati'


def test_direct_entry_links_and_ambiguous_arrow_targets_are_preserved():
    body = '''<div class="text"><span class="lem">ka</span>
<a class="link" href="/lemma/kha/2">kha</a>
<span class="link">↓<a href="/lemma/ga/1">ga</a>, <a href="/lemma/ṅa/1">ṅa</a></span>
<a class="link" href="/lemma/ca/1">↑ca</a>
<a href="/pdf/cha/3">cha</a>
<span class="link">↓missing</span>
<span class="infotext"><a class="link" href="/lemma/hidden/1">↑hidden</a></span></div>'''.encode()
    a = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    assert [r['target_lemma'] for r in a['entry_links']] == ['kha', 'ga', 'ṅa', 'ca', 'cha']
    assert a['entry_links'][-1]['target_homonym'] == '3'
    assert a['entry_links'][-1]['target_delivery_type'] == 'generated_pdf'
    assert [r['target_lemma'] for r in a['cross_references']] == ['ca']
    assert a['reference_diagnostics'][0]['anchor_count'] == 2
    assert a['reference_diagnostics'][1]['markers'] == ['↓']
    assert a['reference_diagnostics'][1]['anchor_count'] == 0
    for r in a['entry_links'] + a['cross_references'] + a['reference_diagnostics']:
        loc = r['locator']
        assert a['article_source_text'][loc['visible_text_start']:loc['visible_text_end']] == r['source_text']


def test_language_tags_inside_translation_keep_dom_containment():
    body = '''<div class="text"><span class="lem">ka</span>
<div class="beleg-all"><span class="tibetisch"><tib>ka</tib> (r. <tib>kha</tib>)</span>
<span class="deutsch">„<tib>ga</tib>“, skt. <skt>śa</skt></span></div></div>'''.encode()
    article = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    example = article['examples'][0]
    assert [f['source_text'] for f in example['tibetan_segments']] == ['ka', 'kha', 'ga']
    assert [f['source_text'] for f in example['tibetan_container_segments']] == ['ka', 'kha']
    assert [f['source_text'] for f in example['translation_tibetan_segments']] == ['ga']
    assert [f['source_text'] for f in example['translation_sanskrit']] == ['śa']
    assert example['tibetan']['source_text'] == 'ka (r. kha)'
    for name in ('tibetan_container_segments', 'translation_tibetan_segments', 'translation_sanskrit'):
        for field in example[name]:
            loc = field['locator']
            assert article['article_source_text'][loc['visible_text_start']:loc['visible_text_end']] == field['source_text']


def pdf_lines(parts, *, fonts=None, pages=None):
    lines = []
    for index, (text, start, end) in enumerate(parts):
        font = (fonts or ['italic'] * len(parts))[index]
        spans = []
        if start:
            spans.append(dict(start=0, end=start, style='regular', font_id='roman'))
        spans.append(dict(start=start, end=end, style='italic', font_id=font))
        if end < len(text):
            spans.append(dict(start=end, end=len(text), style='regular', font_id='roman'))
        lines.append(dict(text=text, style_spans=spans, page_id=(pages or ['p'] * len(parts))[index],
                          line_index=index, printed_page=1, volume=2, span_index=0,
                          run_start=index, run_end_exclusive=index + 1))
    return lines


def test_sanskrit_wrap_and_unlabelled_tokens_preserve_exact_source():
    lines = pdf_lines([('skt. cai-', 5, 9), ('tyāṅganaḥ „Hof“', 0, 10)])
    divisions = [dict(start_line_index=0, end_line_index_exclusive=2)]
    candidates = _candidates(lines, divisions)
    assert candidates['sanskrit'][0]['source_text'] == 'cai-\ntyāṅganaḥ'
    assert candidates['transliteration_candidates'] == []
    unlabelled = pdf_lines([('Lex. pradakṣiṇapaṭṭikā „Weg“', 5, 22),
                           ('≈ cai-', 2, 6), ('tyāṅganaḥ „Hof“', 0, 10),
                           ('Beiname Viṣṇus.', 0, 0)])
    # Regular prose has no italic span at all.
    unlabelled[-1]['style_spans'] = [dict(start=0, end=15, style='regular', font_id='roman')]
    c = _candidates(unlabelled, [dict(start_line_index=0, end_line_index_exclusive=4)])
    assert [t['source_text'] for t in c['transliteration_candidates']] == [
        'pradakṣiṇapaṭṭikā', 'cai-\ntyāṅganaḥ', 'Viṣṇus']
    assert c['sanskrit'] == []
    assert any(s['source_text'] == 'cai-\ntyāṅganaḥ ' for s in c['unclassified_italic_spans'])


def test_sanskrit_label_inside_italic_and_division_barrier():
    lines = pdf_lines([('skt. śa', 0, 7)])
    candidates = _candidates(lines, [dict(start_line_index=0, end_line_index_exclusive=1)])
    assert candidates['sanskrit'][0]['source_text'] == 'śa'
    lines = pdf_lines([('skt. cai-', 5, 9), ('tyāṅganaḥ', 0, 9)])
    candidates = _candidates(lines, [dict(start_line_index=0, end_line_index_exclusive=1),
                                    dict(start_line_index=1, end_line_index_exclusive=2)])
    assert candidates['sanskrit'][0]['source_text'] == 'cai-'
    assert [s['source_text'] for s in candidates['unclassified_italic_spans']] == ['tyāṅganaḥ']


def test_lexical_typographic_children_preserve_ascii_and_clause_boundaries():
    text = 'Lex. niruddham (A); ka (B).'
    lines = pdf_lines([(text, 5, len(text))])
    c = _candidates(lines, [dict(start_line_index=0, end_line_index_exclusive=1)])
    clauses = c['lexical_blocks'][0]['clauses']
    assert [clause['typographic_fields'][0]['source_text'] for clause in clauses] == [
        'niruddham (A)', 'ka (B).']
    assert c['sanskrit'] == []
    assert c['transliteration_candidates'] == []
    for clause in clauses:
        field = clause['typographic_fields'][0]
        assert field['status'] == 'language_unresolved'
        assert text[field['visual_start']:field['visual_end']] == field['source_text']
        assert field['parent_field_visual_start'] == 5
        assert field['parent_field_visual_end'] == len(text)
        assert field['source_style_spans'] == c['unclassified_italic_spans'][0]['source_style_spans']


@pytest.mark.parametrize('fonts,pages', [(['a', 'b'], ['p', 'p']), (['a', 'a'], ['p', 'q'])])
def test_italic_continuation_cannot_cross_font_or_page_identity(fonts, pages):
    lines = pdf_lines([('skt. cai-', 5, 9), ('tyāṅganaḥ', 0, 9)], fonts=fonts, pages=pages)
    c = _candidates(lines, [dict(start_line_index=0, end_line_index_exclusive=2)])
    assert c['sanskrit'][0]['source_text'] == 'cai-'
    assert len(c['unclassified_italic_spans']) == 1


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
