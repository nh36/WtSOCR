"""Synthetic source-anchored structures; no ownership or language guessing."""
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from badw_source_components import author_year_reference_candidates, lexical_clauses, quoted_spans, terminal_lexical_citation
from badw_article_parser import parse_database_article, _field_envelope
from benchmark_badw_structure import boundary_diagnostic
from project_badw_structural_candidates import enrich
from parse_badw_pdf_articles import _candidates, _structure


@pytest.mark.parametrize('text,expected', [
    ('(Nachtr. s. v. ka, -kha)', ['(Nachtr. s. v. ka, -kha)']),
    ('(Nachtr. s.v. ka)', ['(Nachtr. s.v. ka)']),
    ('(SWTF s. v. skt. śraddhābala)', ['(SWTF s. v. skt. śraddhābala)']),
    ('(Macrì 62)', ['(Macrì 62)']),
    ('(Śrī 12)', ['(Śrī 12)']),
    ('„(Macrì 62)“', []),
    ('„Text [vgl. Titel (Toh 543)] weiter“', ['(Toh 543)']),
    ('Text [vgl. Titel (Toh 543)]', ['(Toh 543)']),
    ('„Text [Titel (Toh 543)] weiter“', []),
    ('„Text [vgl. Titel (r. ka)] weiter“', []),
    ('„Text [vgl. Titel (ungefähr 62)] weiter“', []),
    ('(ungefähr 62)', []),
    ('(PW)', []),
    ('„(Nachtr. s.v. ka)“', []),
    ('(auch s.v. ka)', []),
    ('(Nachtr. ohne Locator)', []),
])
def test_headword_locator_observation_does_not_assign_owner(text, expected):
    from badw_source_components import located_parenthetical_citations
    records = located_parenthetical_citations(text, 0, len(text))
    assert [r['source_text'] for r in records] == expected
    assert all(r['status'] == 'unresolved_source_citation_candidate' for r in records)


@pytest.mark.parametrize('text,expected', [
    ('EMMERICK 1967:\n120 f. vermutet', ['EMMERICK 1967:\n120 f.']),
    ('LAUFER 1916: 464 Nr. 66', ['LAUFER 1916: 464 Nr. 66']),
    ('LAUFER 1916: 464\nNr. 64', ['LAUFER 1916: 464\nNr. 64']),
    ('LAUFER 1916: 464 weitere Angaben', ['LAUFER 1916: 464']),
    ('vgl. Laufer 1916: 464, Nr. 66.', ['Laufer 1916: 464, Nr. 66']),
    ('(Kletter/Kriechbaum 2001: 141)', ['Kletter/Kriechbaum 2001: 141']),
    ('LIN 2005: 310, Anm. 2015', ['LIN 2005: 310, Anm. 2015']),
    ('„Kletter/Kriechbaum 2001: 141“', []),
    ('„EMMERICK 1967: 120“', []),
    ('EMMERICK 1967 vermutet', []),
    ('1967: 120', []),
])
def test_author_year_candidates_preserve_wrapping_without_assigning_ownership(text, expected):
    result = author_year_reference_candidates(text, 0, len(text))
    assert [item['source_text'] for item in result] == expected
    assert all(item['status'] == 'unresolved_source_citation_candidate' for item in result)
    assert all(text[item['start']:item['end']] == item['source_text'] for item in result)


def test_untagged_html_author_year_locator_is_preserved_as_unowned_candidate():
    body = ('<div class="text"><span class="lem">ka</span><div class="bedeutung">'
            'Pfau; von skt. mayūra, vgl. Laufer 1916: 464, Nr. 66.'
            '</div></div>').encode()
    article = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    assert [c['source_text'] for c in article['citations']] == ['Laufer 1916: 464, Nr. 66']
    assert article['citations'][0]['locator']['derivation'] == 'source_author_year_locator_candidate'
    assert article['citations'][0]['candidate_status'] == 'unresolved_source_citation_candidate'


def test_parenthetical_author_year_citation_keeps_complete_locator_once():
    body = ('<div class="text"><span class="lem">ka</span><div class="bedeutung">'
            'Definition (Author 1892: 458, Tafel XXIII, Nr. 55); '
            'weiter Author 1892: 459.</div></div>').encode()
    article = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    assert [c['source_text'] for c in article['citations']] == [
        'Author 1892: 459', '(Author 1892: 458, Tafel XXIII, Nr. 55)']
    assert any(d['diagnosis'] == 'contained_author_year_citation'
               for d in article['citation_candidate_diagnostics'])


def test_grouped_parenthetical_authors_are_not_collapsed_to_first_author():
    body = ('<div class="text"><span class="lem">ka</span><div class="bedeutung">'
            'Definition (Author 1892: 458; Other 1992: 12).</div></div>').encode()
    article = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    assert any('Other 1992: 12' in c['source_text'] for c in article['citations'])


@pytest.mark.parametrize('markup', ['<span class="stelle">Pasang 1998: 178</span>',
    '<span class="bibl">Pasang 1998</span>: 178'])
def test_explicit_citation_does_not_expand_to_parenthesis_with_tibetan_target(markup):
    body = ('<div class="text"><span class="lem">ka</span><div class="bedeutung"><div class="lex">'
            'Lex. <tib>ka</tib> (' + markup +
            ' s.v. <tib>ma la yar skyes</tib>).</div></div></div>').encode()
    article = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    assert [c['source_text'] for c in article['citations']] == ['Pasang 1998: 178']
    assert 's.v. ma la yar skyes' in article['article_source_text']
    diagnostics = article['citation_candidate_diagnostics']
    assert diagnostics
    assert all(d['diagnosis'] == 'overlaps_explicit_dom_citation' for d in diagnostics)
    assert any('s.v.' in d['source_text'] for d in diagnostics)
    candidates = [c for clause in article['lexical_blocks'][0]['clauses']
                  for c in clause['terminal_citation_candidates']]
    assert all(c['source_text'] == 'Pasang 1998: 178' for c in candidates)
    # Exercise the final source-component enrichment as well as the parser.
    nodes = []
    enrich(nodes, article['article_source_text'], article=article)
    citations = [n for n in nodes if n['kind'] == 'citation']
    assert all(article['article_source_text'][n['start']:n['end']] == 'Pasang 1998: 178'
               for n in citations)


@pytest.mark.parametrize('suffix,expected', [(': 1519.', 'Schuh 2012: 1519'),
    (': 15–19 ff.', 'Schuh 2012: 15–19 ff.'),
    (': 464, Nr. 64.', 'Schuh 2012: 464, Nr. 64'),
    (': 464\nNr. 64 Anm. 2.', 'Schuh 2012: 464\nNr. 64 Anm. 2'),
    (' discusses this.', None)])
def test_explicit_bibliography_locator_candidate(suffix, expected):
    body = ('<div class="text"><span class="lem">ka</span><div class="bedeutung">'
            'Definition vgl. <span class="bibl">Schuh 2012<span class="infotext">'
            'Private tooltip expansion</span></span>' + suffix + '</div></div>').encode()
    article = parse_database_article(body, source_metadata=dict(delivery_type='database_article',
        valid_resource=True, final_url='https://wts-digital.badw.de/lemma/ka/1'))
    assert 'Private tooltip' not in article['article_source_text']
    assert [c['source_text'] for c in article['citations']] == ([expected] if expected else [])
    for citation in article['citations']:
        loc = citation['locator']
        assert article['article_source_text'][loc['visible_text_start']:loc['visible_text_end']] == expected
        assert loc['derivation'] == 'explicit_bibliography_locator_candidate'
        assert citation['candidate_status'] == 'unresolved_source_citation_candidate'


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
    ('Eine Gottheit (Neb 229) und weitere Erklärung.', '(Neb 229)'),
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
    ('ka (Dagy, brDa).', '(Dagy, brDa)'),
    ('ka (Dagy, ähnl. brDa).', '(Dagy, ähnl. brDa)'),
    ("ka (Be’uD 225,1)", "(Be’uD 225,1)"),
    ('ka (Dagy, auch).', None),
    ('ka (Mvy 1039, 1040).', '(Mvy 1039, 1040)'),
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


@pytest.mark.parametrize('reference', ['vgl. BHSD s.v. nagarāvalambikā',
    'vgl. Mvy 1155 ff.', 'vgl. BHSD 500 s.v. vivācayati',
    'vgl. BHSD\ns.v. śa'])
def test_comparison_references_preserve_source_without_ownership(reference):
    from badw_source_components import comparison_reference_candidates
    text = 'Text ' + reference + '; danach'
    rows = comparison_reference_candidates(text, 0, len(text))
    assert [r['source_text'] for r in rows] == [reference]
    assert text[rows[0]['start']:rows[0]['end']] == reference
    assert rows[0]['status'] == 'unresolved_source_citation_candidate'


@pytest.mark.parametrize('text', ['„vgl. BHSD 500“', 'vgl. etwas anderes',
    'vgl. ↑ ka', 'BHSD 500', 'vgl. BHSD'])
def test_comparison_references_do_not_type_prose_or_quoted_content(text):
    from badw_source_components import comparison_reference_candidates
    assert comparison_reference_candidates(text, 0, len(text)) == []
    with pytest.raises(ValueError, match='bounds'):
        comparison_reference_candidates(text, -1, len(text))


def test_html_comparison_reference_is_unresolved_and_source_bound():
    body = ('<div class="text"><span class="lem">ka</span>'
        '<div class="bedeutung">Text, vgl. BHSD s.v. śa.</div></div>').encode()
    parsed = parse_database_article(body, source_metadata=dict(
        delivery_type='database_article', valid_resource=True,
        final_url='https://wts-digital.badw.de/lemma/ka/1'))
    citation = next(c for c in parsed['citations'] if 'vgl.' in c['source_text'])
    assert citation['source_text'] == 'vgl. BHSD s.v. śa'
    assert citation['locator']['derivation'] == 'explicit_comparison_reference_candidate'


@pytest.mark.parametrize('note,expected', [
    ('[vgl. <skt>Titel</skt> (Toh 543)]', ['(Toh 543)']),
    ('[<skt>Titel</skt> (Toh 543)]', []),
    ('(Toh 543)', []),
])
def test_html_editorial_comparison_inside_translation(note, expected):
    body = ('<div class="text"><span class="lem">ka</span>'
        '<div class="beleg-all"><span class="deutsch">„Text '
        + note + ' weiter“</span></div></div>').encode()
    parsed = parse_database_article(body, source_metadata=dict(
        delivery_type='database_article', valid_resource=True,
        final_url='https://wts-digital.badw.de/lemma/ka/1'))
    candidates = [c for c in parsed['citations'] if 'Toh' in c['source_text']]
    assert [c['source_text'] for c in candidates] == expected
    for citation in candidates:
        locator = citation['locator']
        assert locator['derivation'] == 'source_parenthesis_candidate'


def test_nonterminal_lexical_parenthesis_is_source_bound_without_ownership():
    body = ('<div class="text"><span class="lem">ka</span>'
        '<div class="lex">Lex. <tib>kha</tib> (Mim1 354), '
        '<tib>ka</tib> ≅ <tib>kha</tib> „Wort“ '
        '<span class="stelle">(brDa)</span>.</div></div>').encode()
    parsed = parse_database_article(body, source_metadata=dict(
        delivery_type='database_article', valid_resource=True,
        final_url='https://wts-digital.badw.de/lemma/ka/1'))
    citations = parsed['citations']
    assert [c['source_text'] for c in citations].count('(Mim1 354)') == 1
    candidate = next(c for c in citations if c['source_text'] == '(Mim1 354)')
    assert candidate['locator']['derivation'] == 'source_parenthesis_candidate'
    assert 'supports' not in candidate
    assert [c['source_text'] for c in citations].count('(brDa)') == 1


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


def test_partial_lexical_node_does_not_suppress_full_source_clause():
    text = 'Lex. ka ≈ kha „Wort“ (Mvy 1)'
    lines = [{'text': text, 'page_id': 'p', 'printed_page': 1,
              'span_index': 0, 'run_start': 0, 'run_end_exclusive': 1,
              'style_spans': []}]
    partial = text.index('kha')
    nodes = [dict(id='root', kind='source_division', start=0, end=len(text), parent=None),
             dict(id='partial', kind='lexical_parallel', start=partial, end=len(text), parent='root')]
    divisions, _ = _structure(lines)
    enrich(nodes, text, structure={'visual_lines': lines,
                                  'candidates': _candidates(lines, divisions)})
    complete = [n for n in nodes if n['kind'] == 'lexical_parallel' and n['start'] == 5]
    assert len(complete) == 1
    assert complete[0]['association_status'] == 'source_containment_only'
    assert nodes[1]['start'] == partial
