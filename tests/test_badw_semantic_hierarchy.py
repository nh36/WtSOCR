import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hashlib
import copy
import pytest
from badw_semantic_hierarchy import hierarchy
from resolve_badw_cross_references import EntryIndex


def fixture():
    text = 'one Lex. x (Dagy); y (TTC) later (Dagy)'
    a, b = text.index('x ('), text.index(';')
    c, d = text.index('y ('), text.index(' later')
    citation = text.index('(Dagy)')
    nodes = [dict(id='s', kind='sense', start=0, end=3, lexical_record_id='r'),
             dict(id='c', kind='citation', start=citation, end=citation+6),
             dict(id='outside', kind='citation', start=text.rindex('(Dagy)'), end=len(text))]
    p = dict(identity='entry', review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
             source_kind='html', nodes=nodes, original_records=[dict(id='r', record_type='sense', ordinal=1)],
             original_structure=dict(divisions=[dict(meaning_index=0, lexical_block_indices=[0])],
             lexical_blocks=[dict(locator=dict(visible_text_start=4, visible_text_end=d),
                  clauses=[dict(start=x, end=y, source_text=text[x:y]) for x,y in ((a,b),(c,d))])]))
    return p, text


def test_exact_clauses_have_sense_owner_without_widening_sense():
    p,text=fixture();before=copy.deepcopy(p);result=hierarchy(p,text)
    assert len(result['lex_blocks'])==1 and len(result['lex_items'])==2
    assert all(i['sense_node_id']=='s' for i in result['lex_items'])
    assert [o['citation_node_id'] for o in result['citation_ownership']]==['c']
    assert result['lex_blocks'][0]['marker_span']['literal']=='Lex.'
    assert p==before and p['nodes'][0]['end']==3
    assert hierarchy(p,text)==result


def test_missing_division_is_unresolved_not_nearest_sense():
    p,text=fixture();p['original_structure']['divisions']=[]
    result=hierarchy(p,text)
    assert all(i['ownership']=='unresolved' for i in result['lex_items'])
    assert result['citation_ownership'][0]['passage_id']
    assert result['citation_ownership'][0]['sense_node_id'] is None


def test_duplicate_and_stale_source_fail_closed():
    p,text=fixture();p['original_structure']['lexical_blocks'][0]['clauses']*=2
    with pytest.raises(ValueError,match='duplicate canonical'):hierarchy(p,text)
    with pytest.raises(ValueError,match='hash mismatch'):hierarchy(p,text+'!')


def test_pdf_exact_unique_target_preserves_ambiguity():
    def entry(i,homonym=None):return dict(id=i,record_type='entry',headword=dict(loc='x'),homonym=homonym)
    occurrence=dict(target_label='x',source_candidate=dict(target_candidates=[dict(source_text='x')]))
    assert EntryIndex([entry('one')]).resolve_source_candidate(occurrence)['canonical_resolution']['status']=='resolved'
    assert EntryIndex([entry('one',1),entry('two',2)]).resolve_source_candidate(occurrence)['canonical_resolution']['status']=='ambiguous'
    occurrence['source_candidate']['target_candidates'][0]['source_text']='x extra'
    assert EntryIndex([entry('one')]).resolve_source_candidate(occurrence)['canonical_resolution']['status']=='unresolved'


def test_explicit_sanskrit_overrides_envelope_but_retains_observations():
    p,text=fixture();p['nodes'] += [dict(id='bo',kind='tibetan',start=0,end=8),dict(id='sa',kind='sanskrit',start=4,end=8,source_evidence='explicit HTML sanskrit tag')]
    result=hierarchy(p,text)
    assert [(s['start'],s['end'],s['language']) for s in result['effective_language_spans']]==[(0,4,'bo'),(4,8,'sa')]
    assert result['effective_language_spans'][1]['observation_node_ids']==['bo','sa']


def test_malformed_lex_delimiter_does_not_assert_citation_owner():
    p,text=fixture()
    text=text[:text.index('x (')]+"("+text[text.index('x (')+1:]
    p['review_text_sha256']=hashlib.sha256(text.encode()).hexdigest()
    clause=p['original_structure']['lexical_blocks'][0]['clauses'][0]
    clause['source_text']=text[clause['start']:clause['end']]
    result=hierarchy(p,text)
    assert result['lex_items'][0]['delimiter_diagnostics']
    assert result['citation_ownership']==[]
    assert result['citable_passages'][0]['citation_node_ids']==[]


def test_multiple_explicit_passages_remain_ambiguous():
    p,text=fixture();cite=next(n for n in p['nodes'] if n['id']=='c')
    p['nodes'].append(dict(id='example',kind='example',start=cite['start'],end=cite['end'],parent='s'))
    p['edges']=[dict(kind='citation_of',**{'from':'c','to':'example'})]
    result=hierarchy(p,text)
    owner=result['citation_ownership'][0]
    assert owner['ownership']=='unresolved'
    assert len(owner['candidate_passage_ids'])==2
    assert 'passage_id' not in owner


def test_derived_store_preserves_passage_join_and_rejects_unbound_xref(tmp_path):
    from badw_semantic_store import create,ingest
    p,text=fixture();semantic=hierarchy(p,text)
    pid=semantic['citation_ownership'][0]['passage_id']
    view=dict(inspection_id='entry',semantic_hierarchy=semantic,citations=[dict(
        component_id='c',sense_node_id='s',ownership='derived_source_structure',
        supports=[pid],accepted_authority_ids=['authority'])],cross_references=[])
    db=create(tmp_path/'semantic.sqlite');ingest(db,view)
    assert db.execute('SELECT passage FROM citation_passage').fetchone()==(pid,)
    assert db.execute('SELECT count(*) FROM passage JOIN citation_passage ON passage.id=citation_passage.passage JOIN citation_authority USING(citation) WHERE authority=?',('authority',)).fetchone()==(1,)
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    invalid=dict(inspection_id='other',semantic_hierarchy=dict(lex_items=[],citable_passages=[]),citations=[],cross_references=[dict(component_id=None)])
    with pytest.raises(ValueError,match='unbound xref'):ingest(db,invalid)


def pdf_example(gap=' ', grouped=False):
    text = 'bod'+gap+'„gloss“ (A)'+(' ; (B)' if grouped else '')
    gloss = text.index('„'); cite = text.index('(A)')
    nodes = [dict(id='example',kind='example',start=0,end=len(text)),
        dict(id='tib',kind='tibetan',start=0,end=3,parent='example'),
        dict(id='gloss',kind='translation',start=gloss,end=gloss+7,parent='example'),
        dict(id='c',kind='citation',start=cite,end=cite+3,parent='example')]
    if grouped:
        nodes.append(dict(id='c2',kind='citation',start=text.index('(B)'),end=len(text),parent='example'))
    p=dict(identity='pdf-example',source_kind='pdf',nodes=nodes,
        review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        original_structure=dict(candidates=dict(german_quotes=[dict(visual_start=gloss,visual_end=gloss+7)])))
    return p,text


def test_pdf_quotation_and_group_share_exact_passage():
    p,text=pdf_example(' (metr.) ',True)
    result=hierarchy(p,text)
    owners=result['citation_ownership']
    assert len(owners)==2 and len({o['passage_id'] for o in owners})==1
    assert all(o['evidence_class']=='PDF_example_quotation' for o in owners)
    assert result['citable_passages'][0]['literal']==text


@pytest.mark.parametrize('gap',[' unrelated prose ', ' (unknown.) '])
def test_pdf_nearby_tibetan_does_not_establish_owner(gap):
    p,text=pdf_example(gap)
    assert hierarchy(p,text)['citation_ownership']==[]


def test_pdf_quote_crossing_sense_is_not_promoted():
    p,text=pdf_example()
    p['nodes'].append(dict(id='s',kind='sense',start=4,end=len(text)))
    assert hierarchy(p,text)['citation_ownership']==[]


def test_pdf_parenthetical_definition_group_and_mixed_example_refusal():
    p,text=pdf_example()
    p['nodes']=[n for n in p['nodes'] if n['kind']=='citation']
    p['nodes'].append(dict(id='definition',kind='definition',start=0,end=len(text)))
    assert hierarchy(p,text)['citation_ownership'][0]['evidence_class']=='definition_comparison_clause'
    p['nodes'].append(dict(id='example',kind='example',start=0,end=3))
    assert hierarchy(p,text)['citation_ownership']==[]


def test_printed_superscript_and_wrap_require_geometry():
    from resolve_badw_cross_references import printed_target
    lines=[dict(text='1',page_id='p',first_x=10,y=105,style_spans=[dict(start=0,end=1,style='regular',font_id='r')]),
           dict(text='dkar po',page_id='p',first_x=12,y=100,style_spans=[dict(start=0,end=7,style='italic',font_id='i')]),
           dict(text='chig thub',page_id='p',first_x=12,y=90,style_spans=[dict(start=0,end=9,style='italic',font_id='i')])]
    text='\n'.join(l['text'] for l in lines)
    target=dict(visual_start=0,visual_end=len(text),source_text=text)
    parsed=printed_target(target,dict(visual_lines=lines),text)
    assert parsed['valid'] and parsed['homonym']=='1'
    assert parsed['lexical_target']=='dkar po chig thub' and parsed['literal']==text
    lines[0]['y']=100
    assert not printed_target(target,dict(visual_lines=lines),text)['valid']


def test_manifestation_identity_does_not_collapse_homonyms():
    entries=[dict(id=i,record_type='entry',headword=dict(loc='x'),homonym=h) for i,h in [('html',1),('pdf',1)]]
    ref=dict(target_label='x',source_candidate=dict(target_candidates=[dict(source_text='x')]))
    result=EntryIndex(entries).resolve_source_candidate(ref)['canonical_resolution']
    assert result['status']=='resolved' and 'target_entry_id' not in result
    assert result['target_lexical_entity']['witness_entry_ids']==['html','pdf']
    entries.append(dict(id='homonym2',record_type='entry',headword=dict(loc='x'),homonym=2))
    assert EntryIndex(entries).resolve_source_candidate(ref)['canonical_resolution']['status']=='ambiguous'


def test_absent_html_url_can_resolve_exact_homonym_other_witness():
    index=EntryIndex([dict(id='pdf',record_type='entry',headword=dict(loc='x'),homonym=2)])
    ref=dict(record_type='cross_reference',target_label='x',target_url='https://wts-digital.badw.de/lemma/x/2',source_spans=[dict(start=0,end=1)])
    result=index.resolve_manifestation(ref)['canonical_resolution']
    assert result['status']=='resolved' and result['target_entry_id']=='pdf'
    ref['target_url']='https://wts-digital.badw.de/lemma/y/2'
    assert index.resolve_manifestation(ref)['canonical_resolution']['status']=='unresolved'
