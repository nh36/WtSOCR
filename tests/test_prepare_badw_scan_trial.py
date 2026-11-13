"""Offline controls for a private experiment; these grant no certification authority."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_badw_scan_trial as t


def spec():
    evidence=dict(candidates=[dict(source_id='html:a')],image=dict(pixels=[100,100]))
    return dict(model='gpt-6-luna',max_output_tokens=6000,
                input=[dict(content=[dict(text='prompt\n'+json.dumps(evidence))])],text={})


def result():
    return dict(layout='single page, two columns',non_start_regions=['continued article'],starts=[
        dict(start_id='a',heading='head',printed_numeral='',source_id='html:a',side='single',
             outcome='matched',evidence='distinctive citation 12,3',distinction='different from homonym',
             printed_folio='12',heading_box=[1,2,20,30])])


class Fake:
    def __init__(self,n=123,error=None):
        self.responses=SimpleNamespace(input_tokens=SimpleNamespace(count=self.count))
        self.n=n;self.error=error;self.calls=[]
    def count(self,**kwargs):
        self.calls.append(kwargs)
        if self.error: raise self.error
        return SimpleNamespace(input_tokens=self.n)


def test_exact_count_cache_binding_and_no_generation():
    s=spec();c=Fake();saved=t.count_request(s,None,c)
    assert saved['input_tokens']==123 and len(c.calls)==1
    assert c.calls[0]=={k:s[k] for k in ('model','input','text')}
    assert t.count_request(s,saved,c)==saved and len(c.calls)==1
    changed=copy.deepcopy(s);changed['input'][0]['content'][0]['text']+=' changed'
    t.count_request(changed,saved,c);assert len(c.calls)==2
    # An output ceiling change also invalidates the saved request binding.
    changed=copy.deepcopy(s);changed['max_output_tokens']=1000
    t.count_request(changed,saved,c);assert len(c.calls)==3


@pytest.mark.parametrize('n',[None,True,0,-1,1.5,'123',922001])
def test_invalid_count(n):
    with pytest.raises(ValueError):t.count_request(spec(),None,Fake(n))


def test_missing_support_failure_and_corrupt_cache():
    with pytest.raises(AttributeError):t.count_request(spec(),None,SimpleNamespace(responses=object()))
    with pytest.raises(ConnectionError):t.count_request(spec(),None,Fake(error=ConnectionError()))
    saved=dict(request_sha256=t.binding(spec()),input_tokens=922001)
    c=Fake();assert t.count_request(spec(),saved,c)['input_tokens']==123
    assert len(c.calls)==1


def test_parser_identity_side_evidence_and_start_controls():
    t.validate_result(result(),spec())
    mutations=[lambda r:r['starts'][0].update(source_id='target-not-supplied'),
               lambda r:r['starts'][0].update(side='column1'),
               lambda r:r['starts'][0].update(evidence=''),
               lambda r:r['starts'][0].update(outcome='ambiguous'),
               lambda r:r['starts'].append(copy.deepcopy(r['starts'][0])),
               lambda r:r.update(accepted=True),
               lambda r:r['starts'][0].update(heading_box=[0,0,200,100])]
    for mutate in mutations:
        r=result();mutate(r)
        with pytest.raises(ValueError):t.validate_result(r,spec())


def truth():
    return dict(starts=[dict(truth_id='source:1',html_ids=['html:a'],side='single'),
                        dict(truth_id='source:2',html_ids=['html:b'],side='right'),
                        dict(truth_id='source:3',html_ids=[],side='left')])


def test_scores_identity_side_missing_and_false_starts_separately_from_boxes():
    r=result();audit={'a':'source:1'}
    m=t.score_scan(truth(),r,{'html:a'},audit)
    assert m['eligible']==3 and m['linkable']==2 and m['supplied']==1
    assert m['correct_assignments']==1 and m['missing_starts']==2 and not m['complete_scan']
    r['starts'][0]['heading_box']=[0,0,0,0]
    assert t.score_scan(truth(),r,{'html:a'},audit)==m  # box quality is separate
    r['starts'][0]['side']='left'
    assert t.score_scan(truth(),r,{'html:a'},audit)['wrong_side']==1
    r['starts'][0]['source_id']='html:b'
    assert t.score_scan(truth(),r,{'html:a'},audit)['wrong_identity']==1
    assert t.score_scan(truth(),r,{'html:a'},{'a':None})['false_starts']==1
    with pytest.raises(ValueError):t.score_scan(truth(),r,{'html:a'},{})


def test_complete_scan_requires_all_starts_and_correct_dispositions():
    tr=dict(starts=[truth()['starts'][0]])
    assert t.score_scan(tr,result(),{'html:a'},{'a':'source:1'})['complete_scan']==1
    tr['starts'][0]['html_ids']=[]
    r=result();r['starts'][0].update(source_id='',outcome='no_supplied_match')
    assert t.score_scan(tr,r,set(),{'a':'source:1'})['complete_scan']==1
    r['starts'][0]['outcome']='ambiguous'
    assert t.score_scan(tr,r,set(),{'a':'source:1'})['complete_scan']==0


def test_streaming_components_preserve_exact_reference_target(tmp_path):
    path=tmp_path/'bodies.json';cache=tmp_path/'refs.json'
    body={'html:a':dict(components=[dict(id='c1',type='cross_reference',source_form='↑²target'),
                                    dict(id='c2',type='definition',source_form='not a reference')])}
    path.write_text(json.dumps(body,ensure_ascii=False))
    assert list(t.stream_bodies(path))==list(body.items())
    refs=t.reference_components(path,cache)
    assert refs['html:a'][0]['source_form']=='↑²target'
    assert t.reference_components(path,cache)==refs


@pytest.mark.parametrize('side',['left','unknown'])
def test_review_regression_no_html_abstention_must_locate_printed_side(side):
    tr=dict(starts=[dict(truth_id='source:1',html_ids=[],side='single')])
    r=result();r['starts'][0].update(source_id='',outcome='no_supplied_match',side=side)
    m=t.score_scan(tr,r,set(),{'a':'source:1'})
    assert m['wrong_side']==1 and m.get('correct_no_html_dispositions',0)==0
    assert not m['complete_scan'] and m['abstentions']==1


def test_review_regression_candidate_omissions_include_skipped_starts():
    m=t.score_scan(truth(),dict(starts=[]),{'html:a'},{})
    assert m['omitted_correct_id']==1 and m['missing_starts']==3 and not m['complete_scan']
    r=result();r['starts'][0].update(source_id='wrong',side='unknown')
    m=t.score_scan(truth(),r,{'html:a'},{'a':'source:1'})
    assert m['wrong_side']==1 and m['wrong_identity']==1 and m['omitted_correct_id']==1
