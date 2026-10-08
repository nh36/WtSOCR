"""Synthetic reader contract checks: rendering never supplies scholarship."""
import copy
from test_badw_dictionary_prototype import record
from build_badw_dictionary_prototype import view
from badw_dictionary_entry_view import entry_view
from resolve_badw_cross_references import EntryIndex
import pytest


def inspect(r):
    return view([r], EntryIndex(r['original_records']))[0]


def test_literal_preservation_no_language_guessing_and_no_debug_payload():
    r=record();before=copy.deepcopy(r)
    result=entry_view(inspect(r))
    assert ''.join(s['text'] for s in result['segments'])=='für skt. Viṣṇus'
    assert not any(s['languages'] for s in result['segments'])
    assert not {'projection','nodes','source_kind','review_text_sha256'} & result.keys()
    assert r==before
    assert result==entry_view(inspect(r))


def test_tibetan_identity_and_future_forms_are_explicit():
    r=record();r['nodes'][0]['kind']='tibetan'
    result=entry_view(inspect(r));c=result['components'][0]
    assert c['language']=='bo' and c['source_form']=='für skt. Viṣṇus'
    assert c['normalized_wylie'] is None and c['tibetan_script'] is None
    assert c['id']==entry_view(inspect(r))['components'][0]['id']
    assert all(s['languages']==['bo'] for s in result['segments'])
    assert result['headword_forms']
    assert all(f['language']=='bo' and f['id'] for f in result['headword_forms'])
    assert all(f['normalized_wylie'] is None for f in result['headword_forms'])


def test_review_language_annotation_supplements_source_and_rejects_stale_binding():
    r=record();r['nodes'][0]['kind']='tibetan'
    a=dict(annotation_id='review:1',kind='language_span',effective_status='accepted',
           binding=dict(text_sha256=r['review_text_sha256']),claim=dict(language='sa'),
           ranges=[dict(start=9,end=15,literal='Viṣṇus')])
    r['semantic_annotations']=[a]
    result=entry_view(inspect(r))
    assert result['segments'][-1]['languages']==['bo','sa']
    a['binding']['text_sha256']='stale'
    with pytest.raises(ValueError,match='different source view'):entry_view(inspect(r))


def test_reviewed_smaller_passage_and_unresolved_ownership():
    r=record();r['nodes'].append(dict(id='citation',kind='citation',start=9,end=15,lexical_record_id='c1'))
    assert entry_view(inspect(r))['citations'][0]['ownership']=='unresolved'
    relation=dict(annotation_id='relationship:1',relation='citation_of',
                  binding=dict(text_sha256=r['review_text_sha256']),
                  **{'from':dict(node_id='citation'),'to':[dict(start=0,end=3,kind='citable_passage')]})
    r['semantic_relationships']=[relation]
    result=entry_view(inspect(r),{'c1':[dict(id='book:1',label='Book',descriptions=[])]})
    assert result['citations'][0]['ownership']=='reviewed'
    assert result['citations'][0]['bibliography'][0]['id']=='book:1'
    assert 'citable_passage' in result['segments'][0]['types']
    assert ''.join(s['text'] for s in result['segments'])=='für skt. Viṣṇus'
    relation['status']='candidate'
    assert not entry_view(inspect(r))['relationships']
    relation['status']='accepted';relation['to'][0]['end']=500
    with pytest.raises(ValueError,match='outside source'):entry_view(inspect(r))


@pytest.mark.parametrize('damage',['source','target','empty','literal'])
def test_accepted_relationships_fail_closed(damage):
    r=record()
    relation=dict(annotation_id='review:relation',relation='gloss_of',
                  binding=dict(text_sha256=r['review_text_sha256']),
                  **{'from':dict(node_id='n1'),'to':[dict(start=0,end=3,literal='für')]})
    if damage=='source': relation['from']['node_id']='missing'
    if damage=='target': relation['to']=[dict(node_id='missing')]
    if damage=='empty': relation['to']=[]
    if damage=='literal': relation['to'][0]['literal']='not source'
    r['semantic_relationships']=[relation]
    with pytest.raises(ValueError):entry_view(inspect(r))
