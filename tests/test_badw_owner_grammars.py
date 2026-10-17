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

from badw_reference_runs import compose_reference_runs
from badw_pdf_mixed_clauses import style_runs


@pytest.mark.parametrize('label,leaf',[
    ('K\nLETTER/KRIECHBAUM 2001: 136','LETTER/KRIECHBAUM'),
    ('K\nLETTER/\nK\nRIECHBAUM 2001: 136','RIECHBAUM'),
    ('K\nLETTER/KRIECH-\nBAUM 2001: 136','BAUM'),
    ('H\nUCKER 1985: 481','UCKER'),
])
def test_composed_reference_preserves_runs_and_observed_citation(monkeypatch,label,leaf):
    text='vgl. '+label+'.';p=comparison('vgl. SOURCE.')
    a=text.index(leaf);p['nodes'][0].update(start=a,end=len(text)-1)
    p['nodes'][1]['end']=len(text)
    p['original_structure']['visual_lines'][0].update(text=text,style_spans=[dict(start=0,end=len(text),style='regular')])
    monkeypatch.setattr('badw_reference_runs.passage_layout',lambda p,r:[dict(line_index=0)])
    _,runs=style_runs(p,text);before=copy.deepcopy(p)
    result=compose_reference_runs(p,text,0,len(text),[p['nodes'][0]],runs)
    assert len(result)==1 and result[0]['start']==5
    assert result[0]['end']==p['nodes'][0]['end'] and p==before
    assert comparison_clauses(p,text,set(),obj)[0]['citation_node_ids']==['c']


@pytest.mark.parametrize('prefix',['UPPERCASE PROSE ', 'K\nordinary prose ', 'ANOTHER\n'])
def test_reference_composition_rejects_noninitial_prose(monkeypatch,prefix):
    text='vgl. '+prefix+'AUTHOR 2001: 1.'
    p=comparison('vgl. SOURCE.');a=text.index('AUTHOR')
    p['nodes'][0].update(start=a,end=len(text)-1)
    monkeypatch.setattr('badw_reference_runs.passage_layout',lambda p,r:[{}])
    assert not compose_reference_runs(p,text,0,len(text),[p['nodes'][0]],[])


def test_composed_reference_requires_exact_physical_continuity(monkeypatch):
    text='vgl. H\nUCKER 1985: 481.';p=comparison('vgl. SOURCE.')
    p['nodes'][0].update(start=text.index('UCKER'),end=len(text)-1)
    monkeypatch.setattr('badw_reference_runs.passage_layout',lambda p,r:None)
    assert not compose_reference_runs(p,text,0,len(text),[p['nodes'][0]],[])


@pytest.mark.parametrize('text',[
    'Kurzf. für form eine Gottheit (SOURCE).',
    'synon. form (SOURCE).',
    'wird dem Element Feuer zugeordnet (SOURCE);',
    'auch form Bez. für den Mondknoten (SOURCE).',
    'Name wird auch als Gottheit angesehen (SOURCE).',
    'ein Gewand, das bei Tänzen getragen wird (SOURCE).',
    'Indefinitpartikel (SOURCE), ordinary following prose.',
    'ordinary preceding prose, selector (SOURCE);',
])
def test_editorial_and_coordinated_assertions(monkeypatch,text):
    monkeypatch.setattr('badw_source_assertions.passage_layout',lambda p,r:[{}])
    result=source_assertions(comparison(text),text,set(),obj)
    assert len(result)==1 and result[0]['passage_type']=='source_supported_assertion'
    assert 'SOURCE' in text[result[0]['start']:result[0]['end']]


@pytest.mark.parametrize('text',[
    'auch arbitrary prose (SOURCE).', 'selector arbitrary prose (SOURCE).',
    'Kurzf. für form (SOURCE) additional prose.',
    'ein Gewand (SOURCE).', 'Name wird erwähnt (SOURCE).',
])
def test_editorial_productions_do_not_accept_arbitrary_prose(monkeypatch,text):
    monkeypatch.setattr('badw_source_assertions.passage_layout',lambda p,r:[{}])
    assert not source_assertions(comparison(text),text,set(),obj)


def test_heading_comparison_scope_is_descriptive_dom_sibling():
    text='Nominalsuffix; vgl. SOURCE 12.'
    p=projection(text)
    result=comparison_clauses(p,text,set(),obj)
    assert len(result)==1 and result[0]['start']==text.index('vgl.')
    assert result[0]['boundary_evidence']['dom_path']=='/div[1]/span[2]/'
    p['original_structure']['text_fragments'][0]['dom_path']='/div[2]/span[2]/text()[1]'
    assert not comparison_clauses(p,text,set(),obj)


def test_multiword_reference_headword_requires_observed_italic_extent(monkeypatch):
    from badw_reference_runs import compose_reference_locators
    monkeypatch.setattr('badw_reference_runs.passage_layout',lambda p,r:[{}])
    text='vgl. SOURCE s. v. thig rkud.'
    a=text.index('thig');b=len(text)-1
    runs=[dict(start=a,end=b,style='italic'),dict(start=b,end=b+1,style='regular')]
    got=compose_reference_locators({},text,0,len(text),runs)
    assert len(got)==1 and got[0]['form_span']==dict(start=a,end=b)
    assert not compose_reference_locators({},text,0,len(text),[dict(start=a,end=b,style='regular')])
    # A transition to prose rather than reference punctuation cannot close a locator.
    other='vgl. SOURCE s. v. thig rkud additional prose.'
    assert not compose_reference_locators({},other,0,len(other),runs[:1])


def test_nested_quotes_are_validated_only_for_existing_translation_role():
    from badw_semantic_hierarchy import bounded_example_quotes
    text='„say „yes“ and continue“'
    child=dict(visual_start=5,visual_end=10,diagnostics=[],children=[])
    q=dict(visual_start=0,visual_end=len(text),diagnostics=[],children=[child])
    assert bounded_example_quotes(q,text)
    child['diagnostics']=['unclosed']
    assert not bounded_example_quotes(q,text)
    child['diagnostics']=[];child['visual_end']=len(text)
    assert not bounded_example_quotes(q,text)
    child['visual_end']=10
    assert not bounded_example_quotes(q,text.replace('“','"',1))


@pytest.mark.parametrize('prefix',['eine Gottheit, gehört zu den ', 'npr. ein Geist aus der Gruppe der ', 'eine Gewichtseinheit, 1 form sind 27 '])
def test_relational_definition_assertion_keeps_exact_xref_child(monkeypatch,prefix):
    text=prefix+'↓form (SOURCE).';p=comparison(text)
    a=text.index('↓');b=a+5
    p['nodes'] += [dict(id='d',kind='definition',start=0,end=4),dict(id='r',kind='cross_reference',start=a,end=b)]
    monkeypatch.setattr('badw_source_assertions.passage_layout',lambda p,r:[{}])
    before=copy.deepcopy(p);result=source_assertions(p,text,set(),obj)
    assert len(result)==1 and result[0]['nested_reference_node_ids']==['r']
    assert result[0]['definition_node_ids']==['d'] and p==before
    p['nodes'][-1]['end']=len(text)-1
    assert not source_assertions(p,text,set(),obj)


def test_unrecognized_xref_relation_still_blocks_assertion(monkeypatch):
    text='eine Behauptung vgl. ↓form (SOURCE).';p=comparison(text)
    a=text.index('↓')
    p['nodes'] += [dict(id='d',kind='definition',start=0,end=4),dict(id='r',kind='cross_reference',start=a,end=a+5)]
    monkeypatch.setattr('badw_source_assertions.passage_layout',lambda p,r:[{}])
    assert not source_assertions(p,text,set(),obj)


def test_reference_locator_nested_in_observed_citation_is_masked_once(monkeypatch):
    text='vgl. SOURCE s. v. thig rkud.';p=comparison(text)
    p['nodes'][0]['end']=len(text)-1
    a=text.index('s. v.')
    monkeypatch.setattr('badw_comparison_clauses.compose_reference_locators',lambda *args:[dict(start=a,end=len(text)-1)])
    assert len(comparison_clauses(p,text,set(),obj))==1
