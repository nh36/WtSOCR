"""Fake-provider commissioning: never call a model or use private source data."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import badw_model_worker as w
import prepare_badw_scan_trial as t
import run_badw_scan_trial_batch as b
from test_prepare_badw_scan_trial import result, spec


@pytest.fixture
def setup(tmp_path,monkeypatch):
    # Tiny twelve-scan frozen source set, independent of the Mac's private cache.
    monkeypatch.setattr(w,'private',lambda p:Path(p))
    run=tmp_path/'trial';run.mkdir();scans=[];truth=[];prices=[]
    for i in range(12):
        s=dict(family='wts_test',physical_page=i+1);scans.append(s)
        page=run/f'wts_test-{i+1}';page.mkdir();(page/'source.png').write_bytes(b'fake image')
        request=spec();evidence=json.loads(request['input'][0]['content'][0]['text'].split('\n',1)[1])
        evidence['image']['sha256']=t.sha(page/'source.png')
        request['input'][0]['content'][0]['text']='prompt\n'+json.dumps(evidence)
        request['input'][0]['content'].append(dict(image_url='placeholder'))
        w.write(page/'compact.json',request)
        count=dict(request_sha256=t.binding(t.materialize(page/'compact.json')),input_tokens=100)
        w.write(page/'compact-tokens.json',count)
        cap=w.cost('gpt-6-luna',361,6000,cache_write_tokens=361)/2
        prices.append(dict(page=page.name,variant='compact',**count,output_ceiling=6000,batch_cap_usd=cap))
        w.write(page/'retrieval.json',dict(supplied_ids=['html:a']))
        truth.append(dict(**s,starts=[dict(truth_id='source:1',html_ids=['html:a'],side='single',heading='head')]))
    w.write(run/'selection.json',dict(scans=scans))
    w.write(run/'truth.json',dict(selection_sha256=t.sha(run/'selection.json'),scans=truth))
    w.write(run/'truth-binding.json',dict(truth_sha256=t.sha(run/'truth.json'),selection_sha256=t.sha(run/'selection.json')))
    w.write(run/'pricing.json',dict(requests=prices))
    budget=tmp_path/'budget';budget.mkdir();spending=w.Spending(budget,20,'approval')
    w.write(budget/'spending.json',dict(cap=20,approval='approval',requests={'old-uncertain':dict(reserved=7.6618)}))
    manifest=b.prepare(run,spending)
    return run,spending,manifest


class Fake:
    base_url=b.ENDPOINT
    def __init__(self):
        self.uploads=[];self.jobs=[];self.blobs={};self.create_calls=0;self.upload_timeout=False;self.create_timeout=False
        self.fail_before_create=False;self.files=SimpleNamespace(create=self.upload,list=self.listfiles,content=self.content)
        self.batches=SimpleNamespace(create=self.create,list=lambda **kw:list(self.jobs),retrieve=lambda key:self.jobs[0])
        self.models=SimpleNamespace(retrieve=lambda key:dict(id=key))
    def upload(self,file,purpose):
        name,data,_=file;fid=f'file-{len(self.uploads)}'
        self.uploads.append(dict(id=fid,filename=name));self.blobs[fid]=data
        if self.upload_timeout: self.upload_timeout=False;raise TimeoutError('after upload')
        return self.uploads[-1]
    def listfiles(self,**kwargs):return self.uploads
    def content(self,fid):return SimpleNamespace(content=self.blobs[fid])
    def create(self,**kwargs):
        self.create_calls+=1
        if self.fail_before_create:raise TimeoutError('before create')
        job=dict(id='batch-1',status='completed',**kwargs);self.jobs.append(job)
        if self.create_timeout:self.create_timeout=False;raise TimeoutError('after create')
        return job


def response(cid,status='completed',data=None):
    return dict(custom_id=cid,response=dict(status_code=200,request_id='provider-'+cid,
        body=dict(status=status,usage=dict(input_tokens=100,output_tokens=20),output=[
            dict(type='message',content=[dict(type='output_text',text=json.dumps(data or result()))])])),error=None)


def test_frozen_upload_exact_set_no_answer_key_tamper_and_count_binding(setup):
    run,sp,m=setup
    rows=[json.loads(s) for s in (run/'batch/input.jsonl').read_text().splitlines()]
    assert len(rows)==12 and len({r['custom_id'] for r in rows})==12
    assert all(r['method']=='POST' and r['url']=='/v1/responses' for r in rows)
    assert 'truth_id' not in (run/'batch/input.jsonl').read_text()
    assert b.verify(run)==m
    (run/'batch/input.jsonl').write_text((run/'batch/input.jsonl').read_text()+'{}\n')
    c=Fake()
    with pytest.raises(ValueError,match='upload'):b.launch(run,sp,c,.045)
    assert not c.uploads and not c.jobs
    assert len(t.load(sp.directory/'spending.json')['requests'])==1


def test_interrupted_submission_reconciles_without_buying_or_reserving_twice(setup):
    run,sp,m=setup;c=Fake();c.create_timeout=True
    with pytest.raises(TimeoutError):b.launch(run,sp,c,.045)
    ledger=copy.deepcopy(t.load(sp.directory/'spending.json'))
    assert len(ledger['requests'])==13 and ledger['requests']['old-uncertain']==dict(reserved=7.6618)
    state=b.launch(run,sp,c,.045)
    assert state['job_id']=='batch-1' and c.create_calls==1 and len(c.uploads)==1
    assert t.load(sp.directory/'spending.json')==ledger
    b.launch(run,sp,c,.045);assert c.create_calls==1


def test_ambiguous_not_found_never_automatically_resubmits(setup):
    run,sp,m=setup;c=Fake();c.fail_before_create=True
    with pytest.raises(TimeoutError):b.launch(run,sp,c,.045)
    with pytest.raises(RuntimeError,match='outcome unclear'):b.launch(run,sp,c,.045)
    assert c.create_calls==1


def test_interrupted_upload_reconciles_content(setup):
    run,sp,m=setup;c=Fake();c.upload_timeout=True
    with pytest.raises(TimeoutError):b.launch(run,sp,c,.045)
    assert b.launch(run,sp,c,.045)['job_id']=='batch-1'
    assert len(c.uploads)==1


def test_out_of_order_missing_failed_incomplete_invalid_box_and_usage(setup):
    run,sp,m=setup;c=Fake();b.launch(run,sp,c,.045)
    records=m['records'];rows=[response(r['custom_id']) for r in records]
    rows.pop()  # Missing provider result remains reserved.
    rows[0]=dict(custom_id=records[0]['custom_id'],response=None,error=dict(code='batch_expired'))
    rows[1]=response(records[1]['custom_id'],'incomplete')
    rows[2]=response(records[2]['custom_id'],data=dict(bad='schema'))
    box=result();box['starts'][0]['heading_box']=[0,0,0,0];rows[3]=response(records[3]['custom_id'],data=box)
    c.blobs['outputs']='\n'.join(json.dumps(r) for r in reversed(rows)).encode()
    c.jobs[0]['output_file_id']='outputs'
    answer=b.collect(run,sp,c)
    assert answer['counts']==dict(failed=1,incomplete=1,invalid=1,valid=8,missing=1)
    assert answer['rows'][3]['box_error'] and answer['rows'][3]['status']=='valid'
    ledger=t.load(sp.directory/'spending.json');assert ledger['requests']['old-uncertain']==dict(reserved=7.6618)
    assert 'actual' not in ledger['requests'][b.request_key(m,records[0])]
    assert 'actual' not in ledger['requests'][b.request_key(m,records[-1])]
    assert sum('actual' in r for r in ledger['requests'].values())==10
    c.files.content=lambda *a:pytest.fail('completed download should be cached')
    assert b.collect(run,sp,c)==answer
    assert b.report(run,sp)['denominators']==dict(all_linkable=12,correct_id_supplied=12)


def test_readiness_no_create_and_authorization_endpoint_checks(setup):
    run,sp,m=setup;c=Fake()
    assert b.readiness(c)['batch_list_accessible'] and not c.jobs
    with pytest.raises(ValueError,match='explicit'):b.launch(run,sp,c,None)
    c.base_url='https://regional.example/v1'
    with pytest.raises(ValueError,match='regional'):b.launch(run,sp,c,.045)
    assert len(t.load(sp.directory/'spending.json')['requests'])==1


def test_audit_source_phase_has_no_html_ids_then_scores_and_checks_existing_policy(setup):
    run,sp,m=setup;c=Fake();b.launch(run,sp,c,.045)
    rows=[response(r['custom_id']) for r in m['records']]
    c.blobs['outputs']='\n'.join(json.dumps(r) for r in rows).encode();c.jobs[0]['output_file_id']='outputs'
    b.collect(run,sp,c);b.audit(run)
    text=(run/'batch/source-audit.html').read_text()
    assert 'html:a' not in text and 'active_seconds' in text
    w.write(run/'batch/source-audit.json',dict(manifest_sha256=t.binding(m),
        results_sha256=t.sha(run/'batch/results.json'),phase='source-location-before-identity',active_seconds=42,
        pages={r['page']:{'a':'source:1'} for r in m['records']}))
    report=b.report(run,sp)
    assert report['metrics']['complete_scan']==12 and report['metrics']['correct_assignments']==12
    assert report['active_source_seconds']==42
    assert report['newly_certifiable_links']==0 and report['certification_gate']=='independent source verification missing or disputed'
    assert 'html:a' in (run/'batch/identity-review.html').read_text()


@pytest.mark.parametrize('change',[lambda s:s.update(input_tokens=0),lambda s:s.update(request_sha256='different')])
def test_bad_count_stops_before_upload_or_reservation(setup,change):
    run,sp,m=setup;cp=run/'wts_test-1/compact-tokens.json';saved=t.load(cp);change(saved);w.write(cp,saved)
    with pytest.raises(ValueError,match='count'):b.launch(run,sp,Fake(),.045)
    assert len(t.load(sp.directory/'spending.json')['requests'])==1


def test_tariff_exceeding_trial_cap_is_rejected(setup,monkeypatch):
    run,sp,m=setup
    monkeypatch.setattr(b,'LIMIT',.0001)
    with pytest.raises(ValueError,match='hard cap'):b.frozen(run)


def test_duplicate_and_foreign_results_do_not_settle_uncertain_usage(setup):
    run,sp,m=setup;c=Fake();b.launch(run,sp,c,.045)
    row=response(m['records'][0]['custom_id'])
    c.blobs['outputs']='\n'.join(json.dumps(r) for r in [row,row]).encode()
    c.jobs[0]['output_file_id']='outputs'
    assert b.collect(run,sp,c)['counts']==dict(duplicate=1,missing=11)
    assert all('actual' not in r for r in t.load(sp.directory/'spending.json')['requests'].values())
    (run/'batch/output_file_id.jsonl').write_text(json.dumps(response('foreign')))
    with pytest.raises(ValueError,match='foreign result'):b.collect(run,sp,c)


def test_wrong_provider_job_binding_stops_collection(setup):
    run,sp,m=setup;c=Fake();b.launch(run,sp,c,.045)
    c.jobs[0]['input_file_id']='unrelated-upload'
    with pytest.raises(ValueError,match='does not match'):b.collect(run,sp,c)
    assert all('actual' not in r for r in t.load(sp.directory/'spending.json')['requests'].values())


def test_dry_report_does_not_claim_audited_accuracy(setup):
    run,sp,m=setup
    report=b.report(run,sp)
    assert not report['source_audited'] and report['active_source_seconds'] is None
    assert 'complete_scan' not in report['metrics']
    assert report['actual_trial_spend_usd']==0 and report['certification_screened']==0
