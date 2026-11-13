"""Persistent orchestration of the source-bound worker; never grants review authority.

Private campaign databases, images and responses belong in ignored work/. A single
writer lock, atomic worker cache and the shared spending ledger survive interruption.
"""
import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import signal
import functools
import http.server
import threading
import sqlite3
import subprocess
import sys
import time
import copy
import shutil

import badw_model_worker as w


def select_pages(count, starts=None):
    """Round-robin the registered corpus, retaining partially certified scans.

    These are physical locators only: pagination and article identity remain
    unknown until source inspection. Starts permit explicit front-matter skips.
    """
    if count < 1:
        raise ValueError('page count must be positive')
    starts = starts or {}
    cert = w.load(w.a.CERTIFICATE)
    # An accepted article says nothing about the remaining headings. Only an
    # explicit complete physical-scan census can retire a whole scan. Reviewed
    # printed-page crops alone do not establish coverage of a two-page spread.
    prior = {(p['family'],p['physical_page']) for p in cert.get('complete_scan_reviews', [])
             if isinstance(p,dict) and p.get('physical_scan_complete') is True
             and p.get('heading_census_reviewed') is True}
    registry = {r['label']:r for r in csv.DictReader(
        (w.DATA/'source_pdfs.tsv').open(), delimiter='\t') if r.get('label')}
    queues = []
    for family, label in w.a.FAMILIES.items():
        first = starts.get(family,1)
        if not isinstance(first,int) or isinstance(first,bool) or first < 1:
            raise ValueError('positive physical start required')
        queues.append([dict(family=family,physical_page=n)
            for n in range(first,int(registry[label]['pages'])+1) if (family,n) not in prior])
    result = []
    for index in range(max(map(len,queues))):
        for queue in queues:
            if index < len(queue):
                result.append(queue[index])
                if len(result) == count:
                    return result
    return result


def database(root):
    root = w.private(root)
    db = sqlite3.connect(root/'campaign.sqlite')
    db.row_factory = sqlite3.Row
    db.executescript('''
      PRAGMA journal_mode=WAL;
      CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS coverage(family TEXT, physical INTEGER,
        source_sha256 TEXT NOT NULL, prior_certified INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(family,physical));
      CREATE TABLE IF NOT EXISTS views(id TEXT PRIMARY KEY, spec TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        error TEXT, updated REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at REAL NOT NULL,
        view_id TEXT, kind TEXT NOT NULL, detail TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS reviewed(source_id TEXT PRIMARY KEY, view_id TEXT NOT NULL,
        certificate_sha256 TEXT NOT NULL, page_key TEXT NOT NULL, provenance TEXT NOT NULL,
        published INTEGER NOT NULL DEFAULT 0);
    ''')
    return db


def event(db, view, kind, detail):
    db.execute('INSERT INTO events(at,view_id,kind,detail) VALUES(?,?,?,?)',
               (time.time(), view, kind, json.dumps(detail, ensure_ascii=False)))


def config(db):
    return {r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM config')}


def checkpoint(db, view, stage, detail=None):
    with db:
        db.execute('UPDATE views SET stage=?,error=NULL,updated=? WHERE id=?',
                   (stage, time.time(), view))
        event(db, view, stage, detail or {})


def plan(root, pages, bodies, budget_root, dpi=240, model='gpt-6.1-terra'):
    db = database(root)
    if db.execute('SELECT count(*) FROM config').fetchone()[0]:
        raise ValueError('campaign already planned; resume it or use a new directory')
    cert = w.load(w.a.CERTIFICATE)
    registry = {r['label']:r for r in csv.DictReader(
        (w.DATA/'source_pdfs.tsv').open(), delimiter='\t') if r.get('label')}
    prior = {(p['family'],p['physical_page']) for p in cert['pages'] if p['accepted']}
    baseline = w.load(w.a.GENERATED)
    budget_path = Path(budget_root)
    cap = 10
    if (budget_path/'spending.json').exists():
        state = w.load(budget_path/'spending.json')
        approval = w.load(budget_path/'approval.json')
        if state['approval'] != w.a.object_digest(approval) or state['cap'] > approval['approved_usd']:
            raise ValueError('spending ledger and approval disagree')
        cap = state['cap']
    settings = dict(bodies=str(Path(bodies).resolve()), budget_root=str(Path(budget_root).resolve()),
                    dpi=dpi, model=model, detail='original', max_output_tokens=16000,
                    baseline=w.a.object_digest(baseline['witnesses']),
                    baseline_witnesses={r['source_url']:r for r in baseline['witnesses']}, cap_usd=cap,
                    manual_sha256=w.a.digest(w.DATA/'badw_html_print_pages.json'),
                    prompt_hashes={s:w.a.digest(w.DATA/f'badw_model_{s}_prompt.txt')
                                   for s in ('inventory','match')})
    seen = set()
    with db:
        for family, label in w.a.FAMILIES.items():
            row = registry[label]
            db.executemany('INSERT INTO coverage VALUES(?,?,?,?)',
                [(family,n,row['sha256'],int((family,n) in prior))
                 for n in range(1,int(row['pages'])+1)])
        for spec in pages:
            family, physical = spec['family'], spec['physical_page']
            if not isinstance(physical,int) or isinstance(physical,bool) or not db.execute(
                    'SELECT 1 FROM coverage WHERE family=? AND physical=?',(family,physical)).fetchone():
                raise ValueError('unregistered physical page')
            identity = (family,physical,spec.get('page_key'))
            if identity in seen or any(x[:2]==identity[:2] and (x[2] is None or identity[2] is None) for x in seen):
                raise ValueError('duplicate or overlapping page views')
            if spec.get('page_key'):
                matches = [p for p in cert['pages'] if p['key']==spec['page_key']]
                if len(matches)!=1 or (matches[0]['family'],matches[0]['physical_page'])!=identity[:2]:
                    raise ValueError('reviewed geometry belongs to another source page')
            seen.add(identity)
            view = family+'-'+str(physical)+('-'+spec['page_key'] if spec.get('page_key') else '')
            if '/' in view or '..' in view:
                raise ValueError('unsafe view identity')
            db.execute('INSERT INTO views(id,spec,updated) VALUES(?,?,?)',
                       (view,json.dumps(spec,sort_keys=True),time.time()))
        if not seen:
            raise ValueError('empty campaign')
        db.executemany('INSERT INTO config VALUES(?,?)',[(k,json.dumps(v)) for k,v in settings.items()])
        event(db,None,'planned',dict(views=len(seen),publication_authority=False))
    return status(root, db)


def status(root, db=None):
    db = db or database(root)
    cfg = config(db)
    stages = {r[0]:r[1] for r in db.execute('SELECT stage,count(*) FROM views GROUP BY stage')}
    spending = Path(cfg.get('budget_root',root))/'spending.json'
    requests = w.load(spending)['requests'] if spending.exists() else {}
    actual = sum(r.get('actual',0) for r in requests.values())
    reserved = sum(r['reserved'] for r in requests.values() if 'actual' not in r)
    observed = supported = inventories = 0
    outcomes = {}
    for path in Path(root).glob('pages/*/inventory.json'):
        inventories += 1
        inventory=w.load(path)['result']
        observed += sum(i['classification']=='article' for i in inventory['items'])
    for path in Path(root).glob('pages/*/match.json'):
        for item in w.load(path)['result']['matches']:
            outcome=item['outcome']
            outcomes[outcome]=outcomes.get(outcome,0)+1
    for path in Path(root).glob('pages/*/prediction.json'):
        prediction = w.load(path)
        supported += sum(i.get('source_id') is not None for i in prediction['items'])
    usage={}
    for row in db.execute("SELECT detail FROM events WHERE kind IN ('inventoried','matched')"):
        detail=json.loads(row[0])
        if detail.get('request_sha256'):
            usage[detail['request_sha256']]=detail
    cached={}
    for path in Path(root).glob('pages/*/cache/*.json'):
        record=w.load(path)
        if record.get('request_sha256'):
            cached[record['request_sha256']]=record
    paid={key:value for key,value in requests.items() if key.rsplit(':',1)[0] in cached}
    # Include rejected paid responses, not just successful stage checkpoints.
    campaign_actual=sum(r.get('actual',0) for r in paid.values())
    campaign_requests=sum('actual' in r for r in paid.values())
    service_seconds=sum(r.get('elapsed_seconds',0) for r in cached.values())
    first=db.execute('SELECT min(at) FROM events').fetchone()[0]
    elapsed=max(0,time.time()-first) if first else 0
    finished=stages.get('awaiting_review',0)
    runtime_path=Path(root)/'runtime.json'
    runtime=w.load(runtime_path) if runtime_path.exists() else {}
    alive=False
    if runtime.get('state')=='running' and runtime.get('pid'):
        # The held lock distinguishes the live controller from a recycled PID.
        with (Path(root)/'controller.lock').open('a') as probe:
            try:
                fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
                fcntl.flock(probe,fcntl.LOCK_UN)
            except BlockingIOError:
                alive=True
    review_alive=False
    with (Path(root)/'source-review.lock').open('a') as probe:
        try:
            fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(probe,fcntl.LOCK_UN)
        except BlockingIOError:
            review_alive=True
    publication_alive=False
    with (Path(root)/'publication.lock').open('a') as probe:
        try:
            fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(probe,fcntl.LOCK_UN)
        except BlockingIOError:
            publication_alive=True
    published=db.execute("SELECT detail FROM events WHERE kind='local_reader_published' ORDER BY id DESC LIMIT 1").fetchone()
    reader_output=json.loads(published[0])['output'] if published else None
    reader_counts={}
    if reader_output:
        for tier,name in (('certified','print_facsimiles.json'),('provisional','provisional_print_links.json')):
            manifest=Path(reader_output)/'reader'/name
            if manifest.exists():
                reader_counts[tier]=len(w.load(manifest).get('witnesses',[]))
        if 'certified' in reader_counts:
            reader_counts.setdefault('provisional',0)
    result = dict(stages=stages,planned_views=sum(stages.values()),
        process_running=alive or review_alive or publication_alive,
        process_state=('publishing' if publication_alive else 'source_review' if review_alive else 'running' if alive else ('interrupted' if runtime.get('state')=='running' else runtime.get('state','not_running'))),
        source_review_running=review_alive,
        controller_running=alive,
        publication_running=publication_alive,
        published_reader_output=reader_output,
        published_reader_certified_links=reader_counts.get('certified'),
        published_reader_provisional_links=reader_counts.get('provisional'),
        process_pid=runtime.get('pid'),last_progress_at=db.execute("SELECT max(at) FROM events WHERE kind IN ('inventoried','awaiting_review','source_reviewed','local_reader_published')").fetchone()[0],
        remaining_authorized_usd=cfg['cap_usd']-actual-reserved,
        pages_awaiting_review=sum(not (p.parent/'source_review.json').exists()
            for p in Path(root).glob('pages/*/match.json')),
        pages_awaiting_certificate_adjudication=stages.get('awaiting_review',0),
        generation_remaining_views=sum(n for stage,n in stages.items() if stage!='awaiting_review'),
        corpus_physical_scans=db.execute('SELECT count(*) FROM coverage').fetchone()[0],
        provisional_scan_inventories=inventories,model_outcomes=outcomes,
        independent_headings_provisional=observed,model_supported_proposals=supported,
        source_reviewed_acceptances=db.execute('SELECT count(*) FROM reviewed').fetchone()[0],
        published_additional_links=db.execute('SELECT count(*) FROM reviewed WHERE published=1').fetchone()[0],
        publication_policy='finished source certificates include validated model-source policies; unaccepted suggestions remain separate',
        api_actual_usd=actual,api_unresolved_reservations_usd=reserved,
        campaign_returned_usage_usd=campaign_actual,
        campaign_completed_requests=campaign_requests,
        campaign_valid_stage_responses=len(usage),
        campaign_rejected_responses=sum(r.get('status')=='rejected model response; no evidence authority' for r in cached.values()),
        api_service_seconds=round(service_seconds,1),
        elapsed_wall_seconds=round(elapsed,1),
        review_packs_per_hour=round(finished*3600/elapsed,2) if elapsed else 0,
        maximum_pending_requests=1,
        maximum_stage_requests=sum(stages.values())*2,
        projected_usage_usd=(round(campaign_actual/campaign_requests*sum(stages.values())*2,4)
            if campaign_requests else None),
        projection_basis='Measured returned usage per completed stage; not a billing bound or spending approval',
        approved_cap_usd=cfg.get('cap_usd'),stop_requested=(Path(root)/'STOP').exists(),
        recent_errors=[dict(r) for r in db.execute(
            'SELECT id,stage,error FROM views WHERE error IS NOT NULL ORDER BY updated DESC LIMIT 8')])
    w.write(Path(root)/'status.json',result)
    return result


def sync_reviews(root):
    """Import decisions only from compiler-validated canonical certificates.

    A review.json or model response can never confer acceptance. Publication is
    deliberately separate and requires a built reader and browser verification.
    """
    db=database(root)
    cfg=config(db)
    resources=w.authoritative(Path(cfg['bodies']))
    cert,bodies,anchors,edges,registry,qa=resources
    compiled=w.a.compile_records(cert,bodies,anchors,edges,registry,qa)
    witnesses=compiled['witnesses']
    by_url={r['source_url']:r for r in witnesses}
    for url,record in cfg['baseline_witnesses'].items():
        if by_url.get(url)!=record:
            raise ValueError('protected baseline changed')
    assignments={r['source_id']:(p,r) for p in cert['pages'] for r in p['accepted']}
    if cfg.get('manual_sha256') and w.a.digest(w.DATA/'badw_html_print_pages.json')!=cfg['manual_sha256']:
        raise ValueError('protected manual attachments changed')
    for old in db.execute('SELECT * FROM reviewed'):
        if old['source_id'] not in assignments:
            raise ValueError('reviewed assignment withdrawn; explicit correction required')
    with db:
        for view in db.execute('SELECT * FROM views').fetchall():
            spec=json.loads(view['spec'])
            for sid,(page,assertion) in assignments.items():
                if (page['family'],page['physical_page'])!=(spec['family'],spec['physical_page']):
                    continue
                if spec.get('page_key') and page['key']!=spec['page_key']:
                    continue
                if bodies[sid]['source_url'] in cfg['baseline_witnesses']:
                    continue
                sha=w.a.object_digest(assertion)
                old=db.execute('SELECT * FROM reviewed WHERE source_id=?',(sid,)).fetchone()
                if old and (old['certificate_sha256']!=sha or old['view_id']!=view['id']):
                    raise ValueError('reviewed assignment changed; explicit correction required')
                db.execute('INSERT OR IGNORE INTO reviewed VALUES(?,?,?,?,?,0)',
                    (sid,view['id'],sha,page['key'],w.a.review_basis(assertion)))
                if not old:
                    event(db,view['id'],'source_reviewed',dict(source_id=sid,certificate_sha256=sha))
    return status(root,db)


def review_batch(root, decisions, output):
    """Bind explicit source-reviewed inventories in one fail-closed batch.

    The input is operator-authored, never a raw model response: optional new
    page records have reviewed geometry/inventories and empty accepted lists;
    bindings name exact inventory items and HTML components. The result stays
    private until an operator reviews its diff and installs it as the ledger.
    """
    import prepare_badw_print_drafts as drafts
    cfg=config(database(root))
    cert,bodies,anchors,edges,registry,qa=w.authoritative(Path(cfg['bodies']))
    cert=copy.deepcopy(cert)
    request=w.load(decisions)
    if not request.get('bindings'):
        raise ValueError('explicit reviewed bindings required')
    for page in request.get('pages',[]):
        if page.get('accepted') != [] or any(p['key']==page['key'] for p in cert['pages']):
            raise ValueError('new reviewed page must be unique and have no assertions')
        cert['pages'].append(page)
    for binding in request['bindings']:
        assertion=drafts.bind_reviewed_direct(cert,bodies[binding['source_id']],
            binding['page_key'],binding['item_id'],binding['component_index'],
            binding['historical_issue'],binding['historical_reason'],anchors,edges,registry)
        page=next(p for p in cert['pages'] if p['key']==binding['page_key'])
        page['accepted'].append(assertion)
    compiled=w.a.compile_records(cert,bodies,anchors,edges,registry,qa)
    by_url={r['source_url']:r for r in compiled['witnesses']}
    if any(by_url.get(url)!=record for url,record in cfg['baseline_witnesses'].items()):
        raise ValueError('protected baseline changed')
    if w.a.digest(w.DATA/'badw_html_print_pages.json')!=cfg['manual_sha256']:
        raise ValueError('protected manual attachments changed')
    output=Path(output)
    w.private(output.parent)
    if output.exists():
        raise ValueError('review output must be a new private file')
    w.write(output,cert)
    return dict(output=str(output),validated_bindings=len(request['bindings']),
                canonical_ledger_changed=False,reader_published=False)


def publish(root, output, resume_build=False, base_reader=None):
    with (Path(root)/'publication.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _publish(root,output,resume_build,base_reader)


def _publish(root, output, resume_build=False, base_reader=None):
    """Build and exercise the full reader before recording local publication.

    Git publication is a separate, explicit operator step. A failed build or
    browser journey never marks the SQLite assignments as published.
    """
    sync_reviews(root)
    db=database(root)
    cfg=config(db)
    output=w.private(output)
    ledger_sha=w.a.digest(w.a.CERTIFICATE)
    build_files = ('pages/manifest.json','suggested-pages/manifest.json','reader/data.json',
                   'reader/print_facsimiles.json','reader/provisional_print_links.json','reader/manifest.json')
    checkpoint=output/'build-checkpoint.json'
    if resume_build:
        saved=w.load(checkpoint)
        expected=dict(certificate_sha256=ledger_sha,files={str(path.relative_to(output)):w.a.digest(path)
            for path in (output/name for name in build_files) if path.exists()})
        if saved!=expected:
            raise ValueError('publication build checkpoint changed; use a fresh build')
    elif any(output.iterdir()):
        raise ValueError('publication requires a fresh output directory')
    commands=[
        [sys.executable,'scripts/badw_provisional_print_links.py','--campaign',str(root),
         '--prepare',str(output/'suggested-pages')],
        [sys.executable,'scripts/badw_html_print_alignment.py','--bodies',cfg['bodies'],'--check'],
        [sys.executable,'scripts/badw_html_print_facsimiles.py','--scans-root','.',
         '--output',str(output/'pages')],
        [sys.executable,'scripts/build_badw_full_reader.py','--output',str(output/'reader'),
         '--print-facsimiles',str(output/'pages/manifest.json'),
         '--provisional-print-links',str(output/'suggested-pages/manifest.json')]]
    if base_reader and not resume_build:
        base_reader=w.private(base_reader)
        if w.load(base_reader/'print_facsimiles.json').get('certificate_sha256')!=ledger_sha:
            raise ValueError('base reader has different certified attachments')
        shutil.copytree(base_reader,output/'reader')
        commands=commands[:2]+[[sys.executable,'scripts/badw_provisional_print_links.py',
            '--prepare',str(output/'suggested-pages'),'--refresh-reader',str(output/'reader')]]
        # Preserve the familiar checkpoint path without regenerating certificates.
        (output/'pages').mkdir()
        w.write(output/'pages/manifest.json',w.load(base_reader/'print_facsimiles.json'))
        for name in ('app.js','style.css','index.html'):
            shutil.copyfile(w.a.ROOT/'scripts/badw_dictionary_prototype'/name,output/'reader'/name)
    for command in (commands[1:2] if resume_build else commands):
        subprocess.run(command,cwd=w.a.ROOT,check=True)
    if not resume_build:
        w.write(checkpoint,dict(certificate_sha256=ledger_sha,files={str(path.relative_to(output)):w.a.digest(path)
            for path in (output/name for name in build_files)}))
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(output/'reader'))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        env=os.environ.copy()
        env.update(BADW_READER_URL=f'http://127.0.0.1:{server.server_port}',
                   BADW_SCREENSHOTS=str(output/'screenshots'))
        for suite in ('badw_full_reader.browser.cjs','badw_html_print_facsimiles.browser.cjs',
                      'badw_provisional_print_links.browser.cjs'):
            subprocess.run(['node',f'tests/{suite}'],cwd=w.a.ROOT,env=env,check=True,timeout=3600)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
    if w.a.digest(w.a.CERTIFICATE)!=ledger_sha:
        raise ValueError('certificates changed during reader verification')
    with db:
        db.execute('UPDATE reviewed SET published=1')
        event(db,None,'local_reader_published',dict(output=str(output),certificate_sha256=ledger_sha))
    w.write(output/'publication.json',dict(certificate_sha256=ledger_sha,
        browser_suites='full reader and every facsimile attachment; exited zero',git_pushed=False))
    return status(root,db)


def process(root, db, view, cfg, resources, spending=None, client=None, fixtures=None):
    directory = w.private(Path(root)/'pages'/view['id'])
    pack_path = directory/'pack.json'
    spec = json.loads(view['spec'])
    if pack_path.exists():
        pack = w.load(pack_path)
        if (pack['family'],pack['physical_page']) != (spec['family'],spec['physical_page']):
            raise ValueError('cached page identity changed')
        if w.a.digest(directory/pack['image']['path']) != pack['image']['sha256']:
            raise ValueError('cached image changed')
    else:
        w.prepare_page(spec,resources,directory,cfg['dpi'])
        pack = w.load(pack_path)
    checkpoint(db,view['id'],'prepared',dict(image=pack['image']['sha256']))
    results = {}
    for stage in ('inventory','match'):
        if (Path(root)/'STOP').exists():
            return
        if stage=='match':
            pack['inventory']=results['inventory']['result']
            pack['candidates']=w.retrieve(pack['inventory'],pack,resources[1])
            w.prepare_match_crops(pack,directory)
        request = w.request_spec(stage,pack,cfg['model'],cfg['detail'],cfg['max_output_tokens'])
        fixture = w.load(Path(fixtures)/view['id']/(stage+'.json')) if fixtures else None
        try:
            output = w.execute(request,pack,directory/('fixtures' if fixtures else 'cache'),
                               spending,client,fixture)
        except ValueError:
            cached = directory/'cache'/(w.a.object_digest(request)+'.json')
            if stage != 'match' or fixtures or not cached.exists():
                raise
            from badw_campaign_review import recover_review
            output = recover_review(w.load(cached),request,pack)
        w.write(directory/(stage+'.json'),output)
        results[stage]=output
        checkpoint(db,view['id'],'inventoried' if stage=='inventory' else 'matched',
                   dict(request_sha256=output['request_sha256'],
                        response_id=output.get('response_id'),usage=output['usage'],usd=output['usd']))
    prediction=w.combined_prediction(pack,results['inventory']['result'],results['match']['result'])
    w.write(directory/'prediction.json',prediction)
    # Failures in clerical draft preparation must not discard a successful paid match.
    try:
        review=w.review_drafts(pack,results['match']['result'],resources)
    except ValueError as exc:
        review=dict(status='non-publishable; draft binding needs examination',reason=str(exc))
    review['prediction']='prediction.json'
    review['image_sha256']=pack['image']['sha256']
    review['source_review']=dict(decision=None,reviewer=None)
    w.write(directory/'review.json',review)
    checkpoint(db,view['id'],'awaiting_review')


def recover_cached_matches(root, db, cfg, resources):
    """Drain completed paid matching failures without a client or a new request."""
    for view in db.execute("SELECT * FROM views WHERE stage!='awaiting_review'").fetchall():
        directory=Path(root)/'pages'/view['id']
        paid=[p for p in directory.glob('cache/*.json')
              if (r:=w.load(p)).get('request',{}).get('stage')=='match'
              and r.get('status')=='rejected model response; no evidence authority'
              and r.get('response_status')=='completed']
        if not paid or (Path(root)/'STOP').exists():
            continue
        try:
            process(root,db,view,cfg,resources)
            event(db,view['id'],'cached_matching_recovered',{})
        except (ValueError,KeyError):
            # Structural failures remain quarantined; no API client is supplied.
            continue


def run(root, max_pages=25, fixtures=None, clear_budget_stop=False, drain=False):
    root=w.private(root)
    with (root/'controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        db=database(root)
        cfg=config(db)
        if not cfg:
            raise ValueError('plan the campaign first')
        for stage, expected in cfg['prompt_hashes'].items():
            if w.a.digest(w.DATA/f'badw_model_{stage}_prompt.txt')!=expected:
                raise ValueError('prompt changed; create a separate campaign')
        if max_pages<1:
            raise ValueError('max-pages must be positive')
        resources=w.authoritative(Path(cfg['bodies']))
        current={r['source_url']:r for r in w.load(w.a.GENERATED)['witnesses']}
        if cfg.get('manual_sha256') and w.a.digest(w.DATA/'badw_html_print_pages.json')!=cfg['manual_sha256']:
            raise ValueError('protected manual attachments changed')
        if any(current.get(k)!=v for k,v in cfg['baseline_witnesses'].items()):
            raise ValueError('protected baseline changed')
        if not fixtures:
            recover_cached_matches(root,db,cfg,resources)
        spending=client=None
        if not fixtures:
            budget=w.private(Path(cfg['budget_root']))
            approval=w.load(budget/'approval.json')
            if not (approval.get('approved_usd',0)>=cfg['cap_usd'] and approval.get('approver')
                    and approval.get('rights_basis') and approval.get('transmission_authorized') is True):
                raise ValueError('source transmission and spending authorisation required')
            if clear_budget_stop:
                (budget/'STOP').unlink(missing_ok=True)
            from openai import OpenAI
            client=OpenAI(max_retries=0,timeout=600)
            spending=w.Spending(budget,cfg['cap_usd'],w.a.object_digest(approval))
        old_handlers={s:signal.signal(s,lambda *_:(root/'STOP').touch())
                      for s in (signal.SIGTERM,signal.SIGINT)}
        w.write(root/'runtime.json',dict(pid=os.getpid(),state='running',started=time.time(),drain=drain))
        try:
            rows=list(db.execute("SELECT * FROM views WHERE stage!='awaiting_review' AND attempts<3 ORDER BY rowid"))
            for view in (rows if drain else rows[:max_pages]):
                if (root/'STOP').exists():
                    break
                with db:
                    db.execute('UPDATE views SET attempts=attempts+1 WHERE id=?',(view['id'],))
                    event(db,view['id'],'started',{})
                print(json.dumps(dict(view=view['id'],event='started')),flush=True)
                try:
                    process(root,db,view,cfg,resources,spending,client,fixtures)
                except Exception as exc:
                    # Worker persists redacted diagnostics; never log raw SDK exceptions.
                    safe=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__
                    with db:
                        db.execute('UPDATE views SET error=?,updated=? WHERE id=?',
                                   (safe,time.time(),view['id']))
                        event(db,view['id'],'failed',dict(error=safe))
                    if ('spending cap' in safe.lower() or 'spending limit' in safe.lower()
                            or 'reservation retained' in safe.lower()):
                        (root/'STOP').touch()
                print(json.dumps(status(root,db)),flush=True)
        finally:
            w.write(root/'runtime.json',dict(pid=os.getpid(),state='stopped' if (root/'STOP').exists() else
                'invocation_finished',finished=time.time(),drain=drain))
            for s, handler in old_handlers.items():
                signal.signal(s,handler)
        return status(root,db)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['plan','run','resume','produce','stop','status','report','review','publish'])
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--pages',type=Path)
    p.add_argument('--bodies',type=Path)
    p.add_argument('--budget-root',type=Path)
    p.add_argument('--fixtures',type=Path)
    p.add_argument('--max-pages',type=int,default=25)
    p.add_argument('--drain',action='store_true',help='Process all eligible planned views until stop, budget or completion')
    p.add_argument('--starts',type=Path,help='Optional family-to-first-physical-page JSON for systematic planning')
    p.add_argument('--bindings',type=Path,help='Explicit source-reviewed page records and binding decisions')
    p.add_argument('--dpi',type=int,default=240)
    p.add_argument('--clear-budget-stop',action='store_true')
    p.add_argument('--sync-certificates',action='store_true',
                   help='Import reviewed decisions from validated canonical certificates only')
    p.add_argument('--output',type=Path,help='Fresh ignored directory for full reader publication')
    p.add_argument('--resume-build',action='store_true',help='Resume browser checks of an unchanged completed build')
    p.add_argument('--api-key-file',type=Path,help='Read a private API key without printing it or putting it in shell history')
    p.add_argument('--base-reader',type=Path,help='Reuse a complete reader, updating suggestion sources only at this milestone')
    args=p.parse_args()
    root=w.private(args.campaign)
    if args.api_key_file:
        os.environ['OPENAI_API_KEY']=args.api_key_file.read_text().strip()
    if args.command=='plan':
        if not all((args.bodies,args.budget_root)):
            p.error('plan requires --bodies and --budget-root')
        pages=w.load(args.pages) if args.pages else select_pages(args.max_pages,
            w.load(args.starts) if args.starts else None)
        result=plan(root,pages if isinstance(pages,list) else pages['pages'],args.bodies,args.budget_root,args.dpi)
    elif args.command in ('run','resume','produce'):
        if args.command=='produce' and (not args.output or args.drain):
            p.error('produce requires a fresh --output and a bounded --max-pages (no --drain)')
        if args.command=='produce' and any(w.private(args.output).iterdir()):
            p.error('produce requires a fresh output directory before buying work')
        if args.command in ('resume','produce'):
            (root/'STOP').unlink(missing_ok=True)
        result=run(root,args.max_pages,args.fixtures,args.clear_budget_stop,args.drain)
        if args.command=='produce':
            import badw_campaign_review
            # Consume the matched backlog and this batch before one milestone
            # build. Budget/STOP gates remain owned by the existing workers.
            badw_campaign_review.run(root,live=not bool(args.fixtures),fixtures=args.fixtures)
            result=publish(root,args.output,base_reader=args.base_reader)
    elif args.command=='stop':
        (root/'STOP').touch()
        result=status(root)
    elif args.command=='review':
        if args.bindings:
            if not args.output:
                p.error('review --bindings requires --output for the proposed ledger')
            print(json.dumps(review_batch(root,args.bindings,args.output),indent=2))
        if args.sync_certificates:
            print(json.dumps(sync_reviews(root),indent=2))
        result=dict(policy='Inspect original image, exact HTML and article boundaries; use existing certificate tools.',
                    queues=[str(x) for x in sorted(root.glob('pages/*/review.json'))],
                    automatic_promotion=False)
    elif args.command=='publish':
        if not args.output:
            p.error('publish requires --output pointing to a fresh ignored directory')
        result=publish(root,args.output,args.resume_build,args.base_reader)
    else:
        result=status(root)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
