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
