"""Frozen twelve-scan Batch pilot. No production/publication writes.

prepare/readiness are non-generating. Only run --authorize-usd .045 can submit.
An ambiguous upload/create is reconciled, never automatically retried. Provider
results and usage are saved before interpretation; unresolved charges stay held.
"""
import argparse
from collections import Counter
import fcntl
import html
import json
import math
import os
from pathlib import Path
import sqlite3
import time

import badw_model_worker as w
import prepare_badw_scan_trial as t

ENDPOINT = 'https://api.openai.com/v1'
LIMIT = .045
TERMINAL = {'completed', 'failed', 'expired', 'cancelled'}
TARIFF = dict(model='gpt-6-luna', input_per_million=.05, output_per_million=.25,
              cached_per_million=.005, cache_write_per_million=.0625,
              regional_surcharge=0, verified='2026-11-13',
              source='https://developers.openai.com/api/docs/pricing')


def obj(value):
    return value.model_dump(mode='json') if hasattr(value, 'model_dump') else value


def budget(campaign):
    # Read-only: do not initialise/change the campaign database or its STOP.
    with sqlite3.connect(f'file:{campaign / "campaign.sqlite"}?mode=ro', uri=True) as db:
        cfg = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM config')}
    root = Path(cfg['budget_root'])
    approval = t.load(root/'approval.json'); ledger = t.load(root/'spending.json')
    if (ledger['approval'] != w.a.object_digest(approval) or ledger['cap'] != cfg['cap_usd']
            or ledger['cap'] > approval['approved_usd'] or not approval.get('transmission_authorized')):
        raise ValueError('campaign approval/cap mismatch')
    return w.Spending(root, ledger['cap'], ledger['approval'])


def allowance(spending):
    ledger = t.load(spending.directory/'spending.json')
    rows = ledger['requests'].values()
    usage = sum(r.get('actual', 0) for r in rows)
    holds = sum(r['reserved'] for r in rows if 'actual' not in r)
    return dict(cap_usd=ledger['cap'], returned_usage_usd=usage,
                unresolved_reserved_usd=holds, available_usd=ledger['cap']-usage-holds,
                unresolved_requests=sum('actual' not in r for r in rows))


def frozen(run):
    selection = t.load(run/'selection.json'); truth = t.load(run/'truth.json')
    binding = t.load(run/'truth-binding.json')
    if (binding['truth_sha256'] != t.sha(run/'truth.json')
            or binding['selection_sha256'] != t.sha(run/'selection.json')
            or truth['selection_sha256'] != t.sha(run/'selection.json')):
        raise ValueError('frozen source-first census changed')
    scans = selection['scans']
    keys = [(s['family'], s['physical_page']) for s in scans]
    if len(keys) != 12 or len(set(keys)) != 12:
        raise ValueError('exactly twelve unique frozen scans required')
    if {(s['family'], s['physical_page']) for s in truth['scans']} != set(keys):
        raise ValueError('census/selection mismatch')
    rows = []; records = []
    pricing = t.load(run/'pricing.json')
    for s in scans:
        page = f"{s['family']}-{s['physical_page']}"
        spec = t.materialize(run/page/'compact.json')
        digest = t.binding(spec); count = t.load(run/page/'compact-tokens.json')
        n = count.get('input_tokens')
        if count.get('request_sha256') != digest or type(n) is not int or not 0 < n <= 922000:
            raise ValueError(f'{page}: missing/invalid exact priced count')
        if spec['model'] != TARIFF['model'] or set(spec) != {'model','input','text','max_output_tokens'}:
            raise ValueError('unsupported model or unpriced payload options')
        if spec['max_output_tokens'] != 6000 or n > 272000:
            raise ValueError('outside frozen output/context pricing class')
        priced = [r for r in pricing['requests'] if r['page']==page and r['variant']=='compact']
        cap = w.cost(spec['model'], math.ceil(n*1.05)+256, spec['max_output_tokens'],
                     cache_write_tokens=math.ceil(n*1.05)+256)/2
        if (len(priced)!=1 or priced[0]['request_sha256'] != digest
                or priced[0]['input_tokens'] != n or priced[0]['output_ceiling'] != 6000
                or abs(priced[0]['batch_cap_usd']-cap)>1e-12):
            raise ValueError('pricing binding mismatch')
        cid = f'{page}-{digest[:24]}'
        rows.append(dict(custom_id=cid, method='POST', url='/v1/responses', body=spec))
        records.append(dict(custom_id=cid, page=page, family=s['family'], physical_page=s['physical_page'],
                            payload_sha256=digest, input_tokens=n, output_ceiling=6000, cap_usd=cap))
    payload = ''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':'))+'\n' for r in rows).encode()
    if len(payload)>200_000_000: raise ValueError('Batch file exceeds 200 MB')
    manifest = dict(selection_sha256=t.sha(run/'selection.json'), truth_sha256=t.sha(run/'truth.json'),
                    pricing_sha256=t.sha(run/'pricing.json'), records=records, tariff=TARIFF,
                    endpoint=ENDPOINT, jsonl_sha256=__import__('hashlib').sha256(payload).hexdigest(),
                    bytes=len(payload), cap_usd=sum(r['cap_usd'] for r in records))
    if manifest['cap_usd'] > LIMIT: raise ValueError('trial exceeds $0.045 hard cap')
    return manifest, payload


def prepare(run, spending):
    manifest, payload = frozen(run)
    directory = run/'batch'; directory.mkdir(exist_ok=True)
    target = directory/'input.jsonl'; mp = directory/'manifest.json'
    if mp.exists() and t.load(mp) != manifest: raise ValueError('prepared batch changed')
    if target.exists() and target.read_bytes()!=payload: raise ValueError('prepared JSONL changed')
    target.write_bytes(payload); w.write(mp, manifest)
    available = allowance(spending)
    if manifest['cap_usd'] > available['available_usd']:
        # Resume can already own this job's reservations.
        ledger = t.load(spending.directory/'spending.json')
        owned = sum(ledger['requests'].get(request_key(manifest,r),{}).get('reserved',0)
                    for r in manifest['records'])
        if manifest['cap_usd'] > available['available_usd']+owned:
            raise ValueError('insufficient existing campaign allowance')
    return manifest


def verify(run):
    manifest, payload = frozen(run)
    if t.load(run/'batch/manifest.json') != manifest or (run/'batch/input.jsonl').read_bytes()!=payload:
        raise ValueError('frozen upload does not match exact priced payloads')
    return manifest


def request_key(manifest, record):
    return 'scan-trial-batch:'+t.binding(manifest)+':'+record['custom_id']


def reserve(manifest, spending):
    # Each request keeps its own hold, even when other rows fail or time out.
    for r in manifest['records']:
        key = request_key(manifest,r)
        existing = t.load(spending.directory/'spending.json')['requests'].get(key)
        if existing is None: spending.change(key, reservation=r['cap_usd'])
        elif abs(existing['reserved']-r['cap_usd'])>1e-12: raise ValueError('reservation changed')


def readiness(client):
    model = obj(client.models.retrieve(TARIFF['model']))
    # Listing proves endpoint access, not the model's queued-token quota or credit eligibility.
    active = [dict(id=b['id'],status=b['status']) for b in map(obj, client.batches.list(limit=100))
              if b['status'] not in TERMINAL]
    return dict(model_accessible=model['id'], batch_list_accessible=True, active_batches=active,
                queue_limit='Not exposed by the standard API; verify project Limits in dashboard. '
                'Submission alone confirms queued-token admission, model Batch entitlement and billing eligibility.',
                endpoint=ENDPOINT, regional_surcharge=0)


def launch(run, spending, client, authorized):
    manifest = verify(run)
    if authorized != LIMIT: raise ValueError('run requires explicit --authorize-usd 0.045 after spending decision')
    if str(client.base_url).rstrip('/') != ENDPOINT:
        raise ValueError('priced global endpoint required; regional/FedRAMP uplift exceeds trial cap')
    directory = run/'batch'; path = directory/'state.json'
    with (directory/'submission.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = t.load(path) if path.exists() else dict(manifest_sha256=t.binding(manifest))
        if state['manifest_sha256'] != t.binding(manifest): raise ValueError('submission binding changed')
        if state.get('job_id'): return state
        reserve(manifest,spending)
        filename = f"wts-pilot-{t.binding(manifest)}.jsonl"
        if not state.get('file_id'):
            if state.get('upload_pending'):
                # A timed-out upload may already exist. Match filename AND content.
                hits = []
                for f in map(obj,client.files.list(purpose='batch',limit=100)):
                    if f['filename']==filename:
                        data=client.files.content(f['id']).content
                        if __import__('hashlib').sha256(data).hexdigest()==manifest['jsonl_sha256']:
                            hits.append(f['id'])
                if len(hits)!=1: raise RuntimeError('upload outcome unclear; reconcile provider files before retry; no new upload')
                state['file_id']=hits[0];w.write(path,state)
            else:
                state['upload_pending']=True;w.write(path,state)
                verify(run)  # Recheck the bytes immediately before transmission.
                data=(directory/'input.jsonl').read_bytes()
                uploaded=obj(client.files.create(file=(filename,data,'application/jsonl'),purpose='batch'))
                state['file_id']=uploaded['id'];w.write(path,state)
        if state.get('submission_pending'):
            hits=[b for b in map(obj,client.batches.list(limit=100))
                  if b.get('metadata',{}).get('wts_pilot')==t.binding(manifest)
                  and b['input_file_id']==state['file_id']]
            if len(hits)!=1:
                raise RuntimeError('submission outcome unclear; reconcile provider jobs before retry; no duplicate create')
            state['job_id']=hits[0]['id'];w.write(path,state)
        else:
            state['submission_pending']=True;w.write(path,state)
            job=obj(client.batches.create(input_file_id=state['file_id'],endpoint='/v1/responses',
                completion_window='24h',metadata={'wts_pilot':t.binding(manifest)}))
            state['job_id']=job['id'];w.write(path,state)
        return state


def usage_cost(usage):
    n=usage.get('input_tokens');out=usage.get('output_tokens')
    details=usage.get('input_tokens_details') or {}
    cached=details.get('cached_tokens',0);writes=details.get('cache_write_tokens',0)
    if any(type(x) is not int or x<0 for x in (n,out,cached,writes)) or cached+writes>n:
        raise ValueError('missing/invalid returned usage; keep reservation')
    return w.cost(TARIFF['model'],n,out,cached_tokens=cached,cache_write_tokens=writes)/2


def collect(run, spending, client):
    manifest=verify(run);directory=run/'batch';state=t.load(directory/'state.json')
    job=obj(client.batches.retrieve(state['job_id']));w.write(directory/'job.json',job)
    if (state['manifest_sha256']!=t.binding(manifest) or job['id']!=state['job_id']
            or job['input_file_id']!=state['file_id']
            or (job.get('metadata') or {}).get('wts_pilot')!=t.binding(manifest)):
        raise ValueError('provider job does not match frozen submission; holds retained')
    if job['status'] not in TERMINAL: return dict(status=job['status'])
    raw=[]
    for field in ('output_file_id','error_file_id'):
        fid=job.get(field)
        if fid:
            path=directory/(field+'.jsonl')
            if not path.exists():
                data=client.files.content(fid).content
                tmp=path.with_suffix('.tmp');tmp.write_bytes(data);tmp.replace(path)
            raw.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    expected={r['custom_id']:r for r in manifest['records']};grouped={k:[] for k in expected}
    for row in raw:
        if row.get('custom_id') not in expected: raise ValueError('foreign result custom_id; holds retained')
        grouped[row['custom_id']].append(row)
    outcomes=[]
    for cid,r in expected.items():
        rows=grouped[cid]; record=dict(custom_id=cid,page=r['page'],status='missing')
        if len(rows)>1: record['status']='duplicate'
        elif rows:
            row=rows[0];response=row.get('response') or {};body=response.get('body') or {}
            record['provider_request_id']=response.get('request_id')
            if body.get('usage'):
                amount=usage_cost(body['usage']);key=request_key(manifest,r)
                prior=t.load(spending.directory/'spending.json')['requests'][key]
                if 'actual' in prior and abs(prior['actual']-amount)>1e-12: raise ValueError('usage changed')
                spending.change(key,actual=amount,usage=dict(provider=body['usage'],
                    provider_request_id=response.get('request_id'),batch_id=state['job_id']))
                record['actual_usd']=amount
            if row.get('error') or response.get('status_code')!=200:
                record.update(status='failed',error=row.get('error') or body.get('error'))
            elif body.get('status')!='completed': record.update(status='incomplete',details=body.get('incomplete_details'))
            else:
                try:
                    text=''.join(c['text'] for m in body.get('output',[]) if m['type']=='message'
                                 for c in m['content'] if c['type']=='output_text')
                    result=json.loads(text)
                    t.validate_result(result,t.load(run/r['page']/'compact.json'),check_boxes=False)
                    record.update(status='valid',result=result)
                    try: t.validate_result(result,t.load(run/r['page']/'compact.json'))
                    except (TypeError,ValueError) as e: record['box_error']=str(e)
                except (ValueError,TypeError,KeyError) as e: record.update(status='invalid',error=str(e))
        outcomes.append(record)
    report=dict(status=job['status'],rows=outcomes,counts=dict(Counter(r['status'] for r in outcomes)),
                returned_trial_usage_usd=sum(r.get('actual_usd',0) for r in outcomes),allowance=allowance(spending))
    w.write(directory/'results.json',report)
    return report


def audit(run):
    """Source-first phase: proposed HTML IDs are absent, not merely hidden by CSS."""
    manifest=verify(run);results=t.load(run/'batch/results.json');truth=t.load(run/'truth.json')
    source={(s['family'],s['physical_page']):s for s in truth['scans']};sections=[]
    for record,row in zip(manifest['records'],results['rows']):
        if row['custom_id']!=record['custom_id']: raise ValueError('audit/result binding')
        tr=source[record['family'],record['physical_page']]
        options='<option value="">Choose source start</option><option value="FALSE">False start / continuation</option>'
        options+=''.join(f'<option value="{html.escape(s["truth_id"],quote=True)}">'
                         f'{html.escape(s["heading"])} — {s["side"]}</option>' for s in tr['starts'])
        controls=''.join(f'<p>{html.escape(s["start_id"])}: {html.escape(s["heading"])} '
                        f'<select data-page="{record["page"]}" data-start="{html.escape(s["start_id"],quote=True)}">'
                        f'{options}</select> Box quality <input placeholder="usable / inaccurate / absent" data-box></p>'
                        for s in row.get('result',{}).get('starts',[]))
        sections.append(f'<section><h2>{record["page"]} ({row["status"]})</h2>'
                        f'<a href="../{record["page"]}/source.png" target="_blank">Full-resolution source</a>'
                        f'<img style="width:100%" src="../{record["page"]}/source.png">{controls}</section>')
    prefix=dict(manifest_sha256=t.binding(manifest),results_sha256=t.sha(run/'batch/results.json'))
    document='''<!doctype html><meta charset="utf-8"><title>Source location audit</title>
<p>Identify each predicted heading on the source before viewing its proposed HTML identity.
Map each start once; continuations and spurious headings are false starts. Boxes are separate.
Timer runs only while this window is focused and source checking is active.</p>
<button id="toggle">Pause checking</button><button id="save">Save source audit</button><span id="clock"></span>
'''+''.join(sections)+'''<script>
const binding=BINDING, key=JSON.stringify(binding); let seconds=0, active=true, last=performance.now();
const fields=[...document.querySelectorAll('select,input')];
const prior=JSON.parse(localStorage.getItem(key)||'null');
if(prior){seconds=prior.active_seconds;fields.forEach((f,i)=>f.value=prior.fields[i]||'');}
function tick(){const now=performance.now();if(active&&document.hasFocus()&&!document.hidden)seconds+=(now-last)/1000;last=now;}
setInterval(()=>{tick();clock.textContent=Math.round(seconds)+' active seconds';
localStorage.setItem(key,JSON.stringify({active_seconds:seconds,fields:fields.map(f=>f.value)}));},1000);
toggle.onclick=()=>{tick();active=!active;toggle.textContent=active?'Pause checking':'Resume checking';};
save.onclick=()=>{tick();let pages={};for(const f of document.querySelectorAll('select')){
if(!f.value){alert('Dispose every predicted start first');return;}
(pages[f.dataset.page]??={})[f.dataset.start]=f.value==='FALSE'?null:f.value;}
let boxes={};for(const f of document.querySelectorAll('select'))(boxes[f.dataset.page]??={})[f.dataset.start]=f.parentElement.querySelector('input').value;
const data={...binding,phase:'source-location-before-identity',active_seconds:seconds,pages,boxes};
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)]));a.download='source-audit.json';a.click();};
</script>'''.replace('BINDING',json.dumps(prefix))
    (run/'batch/source-audit.html').write_text(document)
    return dict(audit=str(run/'batch/source-audit.html'), next='Save source-audit.json here, then run report to reveal identity comparisons.')


def report(run,spending):
    manifest=verify(run);directory=run/'batch';truth=t.load(run/'truth.json')
    path=directory/'results.json';results=t.load(path) if path.exists() else dict(rows=[],counts={},returned_trial_usage_usd=0)
    ap=directory/'source-audit.json';a=t.load(ap) if ap.exists() else None
    if a and (a['manifest_sha256']!=t.binding(manifest) or a['results_sha256']!=t.sha(path)
              or a['phase']!='source-location-before-identity' or not math.isfinite(a['active_seconds']) or a['active_seconds']<0):
        raise ValueError('source audit binding/time invalid')
    rows={r['custom_id']:r for r in results['rows']};totals=Counter();details=[]
    for rec in manifest['records']:
        tr=next(s for s in truth['scans'] if s['family']==rec['family'] and s['physical_page']==rec['physical_page'])
        supplied=t.load(run/rec['page']/'retrieval.json')['supplied_ids']
        predictions=rows.get(rec['custom_id'],{}).get('result',dict(starts=[]))
        if a:
            metrics=t.score_scan(tr,predictions,supplied,a['pages'].get(rec['page'],{}))
            totals.update(metrics)
            details.append(dict(page=rec['page'],metrics=metrics,starts=[dict(prediction=p,
                source_truth=next((s for s in tr['starts'] if s['truth_id']==a['pages'][rec['page']][p['start_id']]),None))
                for p in predictions['starts']]))
        else:
            totals.update(eligible=len(tr['starts']),linkable=sum(bool(s['html_ids']) for s in tr['starts']),
                supplied=sum(bool(set(s['html_ids'])&set(supplied)) for s in tr['starts']),
                omitted_correct_id=sum(bool(s['html_ids']) and not bool(set(s['html_ids'])&set(supplied)) for s in tr['starts']))
    # Feed every real proposed match through the existing acceptance gate. This
    # trial supplies one source reading; do not fabricate an independent reading
    # from the audit answer or from another field of the same model response.
    from certify_badw_model_links import policy_reason
    certification=[]
    for rec in manifest['records']:
        for start in rows.get(rec['custom_id'],{}).get('result',{}).get('starts',[]):
            if start['outcome']!='matched': continue
            evidence=dict(state='trial-single-reading',source_id=start['source_id'],
                          heading=start,first_matching=start)
            reason=policy_reason(evidence,{},0,fresh=True)
            if not reason:
                raise ValueError('single-reading trial unexpectedly passed independent certification gate')
            certification.append(dict(page=rec['page'],start_id=start['start_id'],
                                      source_id=start['source_id'],exclusion=reason))
    result=dict(scans=12,denominators=dict(all_linkable=totals['linkable'],correct_id_supplied=totals['supplied']),
        source_audited=bool(a),metrics=dict(totals),active_source_seconds=a['active_seconds'] if a else None,
        actual_trial_spend_usd=results['returned_trial_usage_usd'],request_status=results['counts'],
        newly_certifiable_links=0,certification_screened=len(certification),
        certification_exclusions=dict(Counter(r['exclusion'] for r in certification)),
        certification_gate='independent source verification missing or disputed',
        publication='disabled; existing certified path required',
        box_quality=dict(Counter(v or 'unrecorded' for page in (a or {}).get('boxes',{}).values() for v in page.values())),
        allowance=allowance(spending),details=details,certification=certification)
    w.write(directory/'report.json',result)
    if a:
        (directory/'identity-review.html').write_text('<!doctype html><meta charset="utf-8"><h1>Identity review after source mapping</h1><pre>'+
            html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre>')
    return {k:v for k,v in result.items() if k not in ('details','certification')}


def client():
    from openai import OpenAI
    # Pin the priced global endpoint. Regional/FedRAMP 10% uplift would breach .045.
    return OpenAI(api_key=os.environ.get('OPENAI_API_KEY') or (t.ROOT/'work/openai-api-key').read_text().strip(),
                  base_url=ENDPOINT, max_retries=0, timeout=120)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','readiness','run','audit','report'])
    p.add_argument('--trial',type=Path,default=Path('work/single-scan-trial-20261113'))
    p.add_argument('--campaign',type=Path,default=Path('work/linking-campaign-20261112'))
    p.add_argument('--authorize-usd',type=float)
    p.add_argument('--poll-seconds',type=float,default=30)
    args=p.parse_args();run=w.private(args.trial);spending=budget(args.campaign.resolve())
    if args.command=='prepare':
        m=prepare(run,spending);answer=dict(requests=len(m['records']),input_tokens=sum(r['input_tokens'] for r in m['records']),
            file_bytes=m['bytes'],manifest_sha256=t.binding(m),cap_usd=m['cap_usd'],allowance=allowance(spending),
            generation_submitted=False)
    elif args.command=='readiness':
        verify(run);answer=readiness(client());w.write(run/'batch/readiness.json',answer)
    elif args.command=='run':
        # One poller/collector per trial, including across resumed invocations.
        with (run/'batch/run.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
            c=client();launch(run,spending,c,args.authorize_usd)
            while True:
                answer=collect(run,spending,c)
                if answer['status'] in TERMINAL: break
                print(json.dumps(answer),flush=True);time.sleep(max(1,args.poll_seconds))
            answer=report(run,spending)
    elif args.command=='audit':answer=audit(run)
    else:answer=report(run,spending)
    print(json.dumps(answer,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
