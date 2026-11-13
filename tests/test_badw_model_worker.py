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
    with pytest.raises(ValueError):w.cost('gpt-6-luna',922001,1)


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


def test_cache_write_billing_uses_mutually_exclusive_input_categories():
    assert w.cost('gpt-6-luna',4082,3274,0,4079)==pytest.approx(.002147175)
    assert w.cost('gpt-6.1-terra',1000,100,200,300)==pytest.approx(.001385)
    assert w.cost('gpt-6.1-terra',922000,100,0,922000)==pytest.approx(2.30575)
    for cached,written in [(600,401),(-1,0),(0,-1)]:
        with pytest.raises(ValueError):w.cost('gpt-6-luna',1000,100,cached,written)


def test_live_response_cache_write_usage_is_recorded_before_validation(local_work):
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6-luna','original',100)
    usage=dict(input_tokens=1000,output_tokens=100,
               input_tokens_details=dict(cached_tokens=200,cache_write_tokens=300))
    response=SimpleNamespace(usage=SimpleNamespace(model_dump=lambda:usage),status='completed',
        output_text=__import__('json').dumps(p['inventory']),id='fixture-response')
    client=SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs:response))
    result=w.execute(spec,p,local_work/'cache',w.Spending(local_work,1,'approved'),client,interval=0)
    assert result['usd']==pytest.approx(.0001395)
    entry=next(iter(w.load(local_work/'spending.json')['requests'].values()))
    assert entry['actual']==result['usd'] and entry['usage']==usage


def test_stop_prevents_any_paid_request(local_work,monkeypatch):
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6-luna','original',100)
    (local_work/'STOP').touch()
    with pytest.raises(ValueError,match='stop file'):
        w.execute(spec,p,local_work/'cache',w.Spending(local_work,1,'approved'),object())
    assert not (local_work/'spending.json').exists()


def test_rejected_paid_response_is_preserved_without_another_request(local_work):
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('match',p,'gpt-6-luna','original',100)
    invalid=match();invalid['matches'][0]['html_evidence']='not in the supplied source'
    raw=__import__('json').dumps(invalid)
    usage=dict(input_tokens=1000,output_tokens=100)
    calls=[]
    def respond(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(usage=SimpleNamespace(model_dump=lambda:usage),
            status='completed',output_text=raw,id='rejected-fixture')
    client=SimpleNamespace(responses=SimpleNamespace(create=respond))
    spending=w.Spending(local_work,1,'approved')
    with pytest.raises(ValueError,match='exact supplied component quote'):
        w.execute(spec,p,local_work/'cache',spending,client,interval=0)
    saved=w.load(next((local_work/'cache').glob('*.json')))
    assert saved['output_text']==raw and saved['usd']>0
    with pytest.raises(ValueError,match='cached rejected'):
        w.execute(spec,p,local_work/'cache',spending,client,interval=0)
    assert len(calls)==1
    assert len(w.load(local_work/'spending.json')['requests'])==1


def test_timeout_is_not_reissued(local_work,monkeypatch):
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


def test_billing_rejection_is_not_retried_or_logged_as_uncertain(local_work):
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6-luna','original',100)
    class QuotaError(Exception):
        status_code=429
        body={'code':'credit_balance_exhausted','type':'insufficient_quota',
              'message':'secret request content'}
    calls=[]
    def fail(**kwargs):
        calls.append(kwargs);raise QuotaError('secret credential')
    client=SimpleNamespace(responses=SimpleNamespace(create=fail))
    with pytest.raises(RuntimeError,match='credit_balance_exhausted'):
        w.execute(spec,p,local_work/'cache',w.Spending(local_work,1,'approved'),client,interval=0)
    assert len(calls)==1
    state=w.load(local_work/'spending.json')
    assert next(iter(state['requests'].values()))['actual']==0
    failure=w.load(next((local_work/'cache').glob('*-failure.json')))
    assert failure['reservation_retained'] is False
    assert 'secret' not in str(failure)


def test_reference_census_and_false_header_match():
    ref=dict(reviewer='agent source inspection; no human adjudication',source_image_sha256='bound',
             review_decision='source-reviewed reference',
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


def test_maximum_input_reservation_blocks_unaffordable_live_calls(local_work):
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6.1-terra','original',100)
    with pytest.raises(ValueError,match='cap'):
        w.execute(spec,p,local_work/'cache',w.Spending(local_work,.01,'approved'),object())
    assert w.cost('gpt-6.1-terra',922000,100)==pytest.approx(1.84475)
    assert w.cost('gpt-6-luna',272001,100)==pytest.approx(.0544752)


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


def test_real_offline_sequence_preserves_regions_and_abstentions(local_work):
    import pymupdf
    body=dict(inspection_id='html:known',source_kind='html',source_url='https://example.invalid/known',
              headword=dict(loc='test',tibetan=''),homonym=1,sources=[dict(sha256='html-hash')],
              components=[dict(type='definition',source_form='specific gloss')])
    pdf=local_work/'synthetic.pdf'
    with pymupdf.open() as document:
        document.new_page(width=100,height=100);document.save(pdf)
    family='wts_8_b';label=w.a.FAMILIES[family]
    resources=(dict(pages=[],inputs={}),{'html:known':body},{},[],
               {label:dict(label=label,filename=str(pdf),sha256=w.a.digest(pdf))},{})
    p=w.prepare_page(dict(family=family,physical_page=1),resources,local_work,dpi=72)
    inventory=dict(visible_folios='synthetic fixture',completeness='provisional_complete',limitations='',items=[
        dict(item(),bbox=[5,5,35,15]),
        dict(item('header','running_header'),bbox=[5,20,35,30]),
        dict(item('unknown'),heading_loc='unassociated',bbox=[5,40,35,50])])
    invspec=w.request_spec('inventory',p,'gpt-6-luna','original',1000)
    inv=w.execute(invspec,p,local_work/'fixtures',fixture=inventory)
    w.write(local_work/'inventory-gpt-6-luna.json',inv)
    inv=w.checked_observation(local_work/'inventory-gpt-6-luna.json','inventory',p,'gpt-6-luna')
    p['inventory']=inv['result'];p['candidates']=w.retrieve(inventory,p,resources[1])
    assert len(p['candidates'])==1 and p['bindings']['html:known']['anchors']==[]
    regions=w.prepare_match_crops(p,local_work,padding=1)
    assert {r['item_id'] for r in regions}=={'a','header','unknown'}
    assert regions[0]['pdf_bbox']==[4,79,100,96]
    matching=match()
    for key in ('header','unknown'):
        matching['matches'].append(dict(match()['matches'][0],item_id=key,outcome='unmatched',source_id=None,component_index=None))
    spec=w.request_spec('match',p,'gpt-6-luna','original',1000)
    record=w.execute(spec,p,local_work/'fixtures',fixture=matching)
    w.write(local_work/'match-gpt-6-luna.json',record)
    checked=w.checked_observation(local_work/'match-gpt-6-luna.json','match',p,'gpt-6-luna')
    prediction=w.combined_prediction(p,inventory,checked['result'])
    assert len(prediction['items'])==3 and prediction['items'][2]['source_id'] is None
    reference=dict(reviewer='synthetic test, no scholarly authority',review_decision='source-reviewed reference',
                   source_image_sha256=p['image']['sha256'],complete_census=True,items=copy.deepcopy(prediction['items']))
    score=w.evaluate(reference,prediction)
    assert score['correct_links']==1 and score['correct_abstentions']==2 and score['heading_recall']==1
    wrong=copy.deepcopy(prediction);wrong['items'][0]['printed_homonym']=2
    assert w.evaluate(reference,wrong)['homonym_errors']==1
    assert w.evaluate(reference,wrong)['false_positive_links']==1
    queue=w.review_drafts(p,matching,resources)
    assert queue['drafts']==[] and len(queue['direct_source_review_queue'])==1
    dropped=copy.deepcopy(matching);dropped['matches'].pop()
    with pytest.raises(ValueError):w.combined_prediction(p,inventory,dropped)
    reference['review_decision']='unreviewed certificate'
    with pytest.raises(ValueError,match='source-bound'):w.evaluate(reference,prediction)
    (local_work/regions[0]['path']).write_bytes(b'changed crop')
    with pytest.raises(ValueError,match='crop changed'):w.execute(spec,p,local_work/'fixtures',fixture=matching)


def test_exact_multimodal_count_reservation_and_response_reuse(local_work):
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6.1-terra','original',100)
    calls=[]
    def count(**kwargs):
        calls.append(('count',kwargs));return SimpleNamespace(input_tokens=1000)
    response=SimpleNamespace(usage=SimpleNamespace(model_dump=lambda:dict(input_tokens=1000,output_tokens=100)),
        status='completed',output_text=__import__('json').dumps(p['inventory']),id='fixture-counted-response')
    def create(**kwargs):
        calls.append(('generate',kwargs));return response
    client=SimpleNamespace(responses=SimpleNamespace(input_tokens=SimpleNamespace(count=count),create=create))
    spending=w.Spending(local_work,.01,'approved')
    result=w.execute(spec,p,local_work/'cache',spending,client,interval=0)
    assert [x[0] for x in calls]==['count','generate']
    assert calls[0][1]['input']==calls[1][1]['input']
    assert calls[0][1]['text']==calls[1][1]['text']
    entry=next(iter(w.load(local_work/'spending.json')['requests'].values()))
    assert entry['reserved']==pytest.approx(w.cost(spec['model'],1306,100,cache_write_tokens=1306))
    assert w.execute(spec,p,local_work/'cache',spending,client,interval=0)==result
    assert len(calls)==2 and len(w.load(local_work/'spending.json')['requests'])==1


def test_count_network_failure_does_not_reserve_or_generate(local_work):
    (local_work/'page.png').write_bytes(b'image')
    p=pack();p['image']['sha256']=w.a.digest(local_work/'page.png')
    spec=w.request_spec('inventory',p,'gpt-6.1-terra','original',100)
    def fail(**kwargs):raise ConnectionError('private server message')
    client=SimpleNamespace(responses=SimpleNamespace(input_tokens=SimpleNamespace(count=fail)))
    with pytest.raises(RuntimeError,match='preflight failed'):
        w.execute(spec,p,local_work/'cache',w.Spending(local_work,.01,'approved'),client)
    assert not (local_work/'spending.json').exists()
