"""Offline controls: synthetic observations convey no source-review authority."""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import badw_model_worker as w


def item(key='a', classification='article'):
    return dict(item_id=key,heading_loc='test',heading_tibetan=None,printed_homonym=None,
        bbox=[0,0,10,10],column='left',classification=classification,printed_evidence='specific gloss',
        preceding='preceding article',following='following article',uncertainty='')


def pack():
    return dict(image=dict(path='page.png',sha256='x',pixels=[20,20],transform={}),
        inventory=dict(visible_folios='1',completeness='partial',limitations='',items=[item()]),
        candidates=[dict(source_id='html:known',components=[dict(source_form='specific gloss')])])


def match():
    return dict(matches=[dict(item_id='a',outcome='supported',source_id='html:known',component_index=0,
        printed_evidence='specific gloss',html_evidence='specific gloss',boundary_evidence='new heading below article',
        homonym_evidence='unnumbered print',alternatives='',uncertainty='')])


def test_strict_inventory_and_identity_controls():
    p=pack();w.validate('inventory',p['inventory'],p);w.validate('match',match(),p)
    for mutate in [lambda r:r['matches'][0].update(source_id='invented'),
                   lambda r:r['matches'][0].update(html_evidence='invented gloss'),
                   lambda r:r['matches'][0].update(boundary_evidence=''),
                   lambda r:r.update(matches=[]),
                   lambda r:r['matches'].append(copy.deepcopy(r['matches'][0]))]:
        r=match();mutate(r)
        with pytest.raises(ValueError):w.validate('match',r,p)
    p['inventory']['items'][0]['classification']='running_header'
    with pytest.raises(ValueError):w.validate('match',match(),p)
    p['inventory']['items'][0]['bbox']=[0,0,21,10]
    with pytest.raises(ValueError):w.validate('inventory',p['inventory'],p)


def test_inventory_prompt_does_not_leak_candidates_or_previous_reviews():
    p=pack();p['accepted']=[{'secret':'old judgement'}]
    spec=w.request_spec('inventory',p,'gpt-6-luna','original',1000)
    assert spec['evidence']=={'image_pixels':[20,20]}
    assert 'old judgement' not in str(spec)
    assert w.request_spec('match',p,'gpt-6-luna','original',1000)!=spec


@pytest.fixture
def local_work(tmp_path,monkeypatch):
    monkeypatch.setattr(w.a,'ROOT',tmp_path)
    d=tmp_path/'work'/'run';d.mkdir(parents=True)
    return d


def test_cost_cap_and_uncertain_retry_reservation(local_work):
    ledger=w.Spending(local_work,0.01,'approval')
    ledger.change('first',reservation=.006)
    with pytest.raises(ValueError,match='cap'):ledger.change('second',reservation=.006)
    with pytest.raises(ValueError,match='already reserved'):ledger.change('first',reservation=.006)
    ledger.change('first',actual=.002)
    ledger.change('second',reservation=.006)
    with pytest.raises(ValueError,match='approval/cap'):w.Spending(local_work,.02,'approval').change('third',reservation=.001)
    assert w.cost('gpt-6-luna',1000000//10,1000,20000)==pytest.approx(.0087)
    with pytest.raises(ValueError):w.cost('gpt-6-luna',272001,1)


def test_fixture_cache_is_bound_to_image_and_result(local_work):
    image=local_work/'page.png';image.write_bytes(b'fixture image')
    p=pack();p['image']['sha256']=w.a.digest(image)
    spec=w.request_spec('inventory',p,'gpt-6-luna','original',100)
    cache=local_work/'fixtures'
    result=w.execute(spec,p,cache,fixture=p['inventory'])
    assert result['usd']==0 and 'offline fixture' in result['status']
    assert w.execute(spec,p,cache)==result
    path=next(cache.glob('*.json'));tampered=w.load(path);tampered['result']['limitations']='tampered';w.write(path,tampered)
    with pytest.raises(ValueError,match='corrupt'):w.execute(spec,p,cache)
    image.write_bytes(b'changed')
    with pytest.raises(ValueError,match='image changed'):w.execute(spec,p,cache)


def test_stop_prevents_any_paid_request(local_work,monkeypatch):
    monkeypatch.setattr(w,"LIVE_IMAGE_BILLING_VERIFIED",True)
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6-luna','original',100)
    (local_work/'STOP').touch()
    with pytest.raises(ValueError,match='stop file'):
        w.execute(spec,p,local_work/'cache',w.Spending(local_work,1,'approved'),object())
    assert not (local_work/'spending.json').exists()


def test_timeout_is_not_reissued(local_work,monkeypatch):
    monkeypatch.setattr(w,"LIVE_IMAGE_BILLING_VERIFIED",True)
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6-luna','original',100)
    calls=[]
    def fail(**kwargs):
        calls.append(kwargs);raise TimeoutError('secret must not appear in diagnostic')
    client=SimpleNamespace(responses=SimpleNamespace(create=fail))
    with pytest.raises(RuntimeError,match='reservation retained') as exc:
        w.execute(spec,p,local_work/'cache',w.Spending(local_work,1,'approved'),client,interval=0)
    assert 'secret' not in str(exc.value) and len(calls)==1
    state=w.load(local_work/'spending.json')
    assert len(state['requests'])==1 and 'actual' not in next(iter(state['requests'].values()))


def test_reference_census_and_false_header_match():
    ref=dict(reviewer='agent source inspection; no human adjudication',source_image_sha256='bound',
             complete_census=True,items=[dict(item(),source_id='html:known')])
    pred=dict(source_image_sha256='bound',items=[dict(item(classification='running_header'),source_id='html:known')])
    score=w.evaluate(ref,pred)
    assert score['heading_recall']==0 and score['false_positive_links']==1
    pred['items'][0]['classification']='article'
    assert w.evaluate(ref,pred)['correct_links']==1
    ref['complete_census']=False
    assert w.evaluate(ref,pred)['heading_recall'] is None
    pred['source_image_sha256']='other'
    with pytest.raises(ValueError):w.evaluate(ref,pred)


def test_frozen_evaluation_has_disjoint_development_and_holdout():
    manifest=w.load(w.DATA/'badw_model_evaluation_pages.json')
    rows=manifest['pages']
    assert 40<=len(rows)<=60
    assert len({(r['family'],r['physical_page']) for r in rows})==len(rows)
    assert len({r['family'] for r in rows})==4
    assert {r['split'] for r in rows}=={'development','heldout'}
    assert all('accepted' not in r and 'answers' not in r for r in rows)


def test_unverified_model_image_billing_blocks_live_calls(local_work):
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6-luna','original',100)
    with pytest.raises(ValueError,match='model-specific image billing'):
        w.execute(spec,p,local_work/'cache',w.Spending(local_work,1,'approved'),object())
    assert not (local_work/'spending.json').exists()


def test_saved_observations_rebind_before_matching_or_drafting(local_work):
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6-luna','original',100)
    record=w.execute(spec,p,local_work/'fixtures',fixture=p['inventory'])
    path=local_work/'inventory-gpt-6-luna.json';w.write(path,record)
    assert w.checked_observation(path,'inventory',p,'gpt-6-luna')==record
    changed=copy.deepcopy(p);changed['physical_page']=999
    with pytest.raises(ValueError,match='binding'):
        w.checked_observation(path,'inventory',changed,'gpt-6-luna')
    record['result']['limitations']='changed';w.write(path,record)
    with pytest.raises(ValueError,match='binding'):
        w.checked_observation(path,'inventory',p,'gpt-6-luna')
