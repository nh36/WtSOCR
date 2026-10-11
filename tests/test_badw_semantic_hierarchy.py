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
