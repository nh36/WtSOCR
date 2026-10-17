"""Independent boundaries, source containment and competing-role rejection."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from badw_lex_assertions import lex_assertions
from badw_header_assertions import header_assertions
from badw_comparison_clauses import comparison_clauses


def obj(kind, start, end, **kwargs):
    return dict(type=kind, start=start, end=end, **kwargs)


def projection(text, kind='html'):
    a = text.index('SOURCE')
    return dict(source_kind=kind, nodes=[dict(id='c', kind='citation', start=a, end=a+6)],
                original_structure=dict(
                    lemma_field=dict(locator=dict(dom_path='/div[1]/span[1]/span[1]')),
                    text_fragments=[dict(dom_path='/div[1]/span[2]/text()[1]',
                                         visible_text_start=0, visible_text_end=len(text))],
                    visual_lines=[dict(text=text, style_spans=[dict(start=0, end=len(text), style='regular')])]))


def test_lex_semicolon_recovers_local_assertion_preserving_damaged_item():
    text = 'bad (earlier; ~ ≅ form (SOURCE)'
    p = projection(text)
    start = text.index('~')
    p['nodes'].append(dict(id='t', kind='tibetan', start=start, end=start+1))
    item = dict(id='lex', start=0, end=len(text), delimiter_diagnostics=['unclosed'],
                sense_node_id=None, ownership='entry')
    before = copy.deepcopy((p, item))
    result = lex_assertions(p, text, [item], set(), obj)
    assert len(result) == 1
    assert text[result[0]['start']:result[0]['end']] == '~ ≅ form (SOURCE)'
    assert result[0]['lex_item_id'] == 'lex'
    assert (p, item) == before
    assert not lex_assertions(p, text, [item], {'c'}, obj)


@pytest.mark.parametrize('local', ['~ ≅ form (SOURCE', '~ ≅ form (SOURCE))', '~ form (SOURCE)', '~ ≅ form (SOURCE) more prose'])
def test_lex_rejects_incomplete_or_nonassertion(local):
    text = 'bad (; ' + local
    p = projection(text)
    a = text.index('~')
    p['nodes'].append(dict(id='t', kind='tibetan', start=a, end=a+1))
    item = dict(id='lex', start=0, end=len(text), delimiter_diagnostics=['unclosed'], sense_node_id=None, ownership='entry')
    assert not lex_assertions(p, text, [item], set(), obj)


@pytest.mark.parametrize('text', ['Genitivsuffix (SOURCE)', '„erste, zweite“ (SOURCE)', 'extra, Pluralpartikel (vgl. SOURCE)'])
def test_heading_assertion_is_exact_descriptive_sibling_clause(text):
    p = projection(text)
    result = header_assertions(p, text, set(), obj)
    assert len(result) == 1
    assert result[0]['citation_node_ids'] == ['c']
    assert not header_assertions(p, text, {'c'}, obj)
    p['original_structure']['text_fragments'][0]['dom_path'] = '/div[2]/span[2]/text()[1]'
    assert not header_assertions(p, text, set(), obj)


@pytest.mark.parametrize('text', ['ordinary prose (SOURCE)', '(SOURCE)', '„broken (SOURCE)', 'Genitivsuffix (SOURCE) more prose'])
def test_heading_rejects_prose_and_malformed_or_nonterminal_enclosures(text):
    assert not header_assertions(projection(text), text, set(), obj)


def comparison(text):
    p = projection(text, 'pdf')
    p['nodes'].append(dict(id='division', kind='source_division', start=0, end=len(text)))
    return p


def test_comparison_terminal_punctuation_and_locator_are_independent_boundaries():
    text = 'vgl. SOURCE 12, 23 s.v. form. Following prose.'
    p = comparison(text)
    result = comparison_clauses(p, text, set(), obj)
    assert len(result) == 1
    assert text[result[0]['start']:result[0]['end']] == 'vgl. SOURCE 12, 23 s.v. form.'
    assert not comparison_clauses(p, text, {'c'}, obj)


@pytest.mark.parametrize('text', ['vgl. SOURCE 12', 'vgl. SOURCE 12 → form.', 'vgl. SOURCE 12 und more prose.', 'vgl. SOURCE (12.', '(vgl. SOURCE 12.)'])
def test_comparison_rejects_missing_end_prose_xrefs_and_nested_scope(text):
    assert not comparison_clauses(comparison(text), text, set(), obj)


def test_comparison_rejects_competing_semantic_component_and_layout_jump():
    text = 'vgl. SOURCE 12.'
    p = comparison(text)
    p['nodes'].append(dict(id='ex', kind='example', start=5, end=len(text)))
    assert not comparison_clauses(p, text, set(), obj)
    p['nodes'].pop()
    p['original_structure']['visual_lines'] = [
        dict(text='vgl.', style_spans=[dict(start=0, end=4, style='regular')], first_x=0, y=10),
        dict(text='SOURCE 12.', style_spans=[dict(start=0, end=10, style='regular')], first_x=100, y=9)]
    assert not comparison_clauses(p, 'vgl.\nSOURCE 12.', set(), obj)

from badw_source_assertions import source_assertions, clause_ends
from badw_assertion_layout import continuous


@pytest.mark.parametrize('text,role', [
    ('a topic marker similar to ni (SOURCE).', 'grammatical_assertion'),
    ('skt. sthūla (SOURCE);', 'source_language_assertion'),
    ('Bez. einer besonderen Erkenntnis (SOURCE);', 'definition_assertion'),
])
def test_supported_assertion_has_independent_scope_and_punctuation(monkeypatch,text,role):
    monkeypatch.setattr('badw_source_assertions.passage_layout',lambda p,r: [{'line_index':0}])
    p=comparison(text)
    if role=='definition_assertion': p['nodes'].append(dict(id='d',kind='definition',start=0,end=text.index(' (')))
    before=copy.deepcopy(p)
    result=source_assertions(p,text,set(),obj)
    assert len(result)==1 and result[0]['assertion_role']==role
    assert result[0]['start']==0 and result[0]['end']==len(text)
    assert p==before
    assert not source_assertions(p,text,{'c'},obj)


@pytest.mark.parametrize('text',[
    'ordinary prose (SOURCE).', 'skt. sthūla (SOURCE)',
    'skt. sthūla (SOURCE) further prose.', 'skt. sthūla (SOURCE)).',
])
def test_supported_assertion_rejects_missing_grammar_or_end(monkeypatch,text):
    monkeypatch.setattr('badw_source_assertions.passage_layout',lambda p,r: [{}])
    assert not source_assertions(comparison(text),text,set(),obj)


@pytest.mark.parametrize('kind',['example','lexical','lexical_parallel','cross_reference'])
def test_supported_assertion_rejects_competing_role(monkeypatch,kind):
    monkeypatch.setattr('badw_source_assertions.passage_layout',lambda p,r: [{}])
    text='skt. sthūla (SOURCE).';p=comparison(text)
    p['nodes'].append(dict(id='competing',kind=kind,start=5,end=11))
    assert not source_assertions(p,text,set(),obj)


def test_assertion_and_comparison_reject_new_sense_boundary(monkeypatch):
    monkeypatch.setattr('badw_source_assertions.passage_layout',lambda p,r: [{}])
    for text, grammar in [('skt. sthūla (SOURCE).',source_assertions),
                          ('vgl. SOURCE 12.',comparison_clauses)]:
        p=comparison(text)
        p['nodes'].append(dict(id='new_sense',kind='sense',start=5,end=len(text)))
        assert not grammar(p,text,set(),obj)


def test_physical_continuity_keeps_columns_pages_and_baseline_order():
    def line(x,y,right=None,page='p'):
        return dict(x=x,y=y,right=x+40 if right is None else right,page_id=page,printed_page=1)
    assert continuous([line(50,700,180),line(180,700)],0,1)
    assert continuous([line(180,700),line(50,684)],0,1)
    assert not continuous([line(50,700),line(325,684)],0,1)
    assert not continuous([line(50,700),line(50,684,page='other')],0,1)
    assert not continuous([line(50,700),line(50,705)],0,1)
    assert not continuous([line(50,700),line(50,660)],0,1)


@pytest.mark.parametrize('text',[
    'Genitivsuffix (SOURCE) bzw. particule génitive-relative (OTHER);',
    'bounded locus role particle, „inside space“ (SOURCE);',
    '„the selector ‘separate units’ marks the plural“ (SOURCE);',
    'Suffix, das den Ergativ und Instrumental markiert (SOURCE);',
])
def test_heading_coordinated_and_nested_complete_descriptions(text):
    assert len(header_assertions(projection(text),text,set(),obj))==1


@pytest.mark.parametrize('text',[
    'Suffix, arbitrary editorial discussion (SOURCE);',
    'bounded locus role particle, „broken (SOURCE);',
    'topicalizer (SOURCE) with additional prose;',
])
def test_heading_complete_phrase_grammar_required(text):
    assert not header_assertions(projection(text),text,set(),obj)


def test_heading_extension_preserves_existing_quoted_assertion_span():
    text='bounded locus role particle, „inside space“ (SOURCE);'
    result=header_assertions(projection(text),text,set(),obj)
    assert len(result)==1
    assert text[result[0]['start']:result[0]['end']]=='„inside space“ (SOURCE)'


def test_heading_observed_form_end_is_a_boundary():
    text='also bo Nominalsuffix (SOURCE)'
    p=projection(text)
    p['original_structure']['text_fragments']=[
        dict(dom_path='/div[1]/span[2]/text()[1]',visible_text_start=0,visible_text_end=5),
        dict(dom_path='/div[1]/span[2]/tib[1]/text()[1]',visible_text_start=5,visible_text_end=7),
        dict(dom_path='/div[1]/span[2]/text()[2]',visible_text_start=7,visible_text_end=len(text))]
    result=header_assertions(p,text,set(),obj)
    assert len(result)==1 and result[0]['start']==8
    p['original_structure']['text_fragments'][1]['dom_path']='/div[1]/span[2]/span[1]/text()[1]'
    assert not header_assertions(p,text,set(),obj)


def test_supported_assertion_rejects_layout_without_independent_geometry(monkeypatch):
    monkeypatch.setattr('badw_source_assertions.passage_layout',lambda p,r: None)
    assert not source_assertions(comparison('skt. sthūla (SOURCE).'),'skt. sthūla (SOURCE).',set(),obj)


def test_physical_layout_requires_exact_source_binding(monkeypatch):
    from badw_assertion_layout import physical_lines
    p=projection('SOURCE','pdf')
    assert physical_lines(p)==[]
    p['source']={'source_objects':[dict(page_id='p',canonical_object='c',canonical_object_sha256='h',pdf_sha256='pdf',pdf_url='url')]}
    p['original_structure']['visual_lines']=[dict(page_id='p',run_start=0,run_end_exclusive=1)]
    monkeypatch.setattr('badw_assertion_layout.page_runs',lambda *args:None)
    assert physical_lines(p)==[]
