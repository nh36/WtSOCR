"""Resumable source-page production and transactional certified-only publication.

Uses the existing campaign, immutable responses and shared spending ledger.
Exceptions retire an attempt, never an HTML identity or a whole physical scan.
"""
import copy
import fcntl
import json
import os
from pathlib import Path
import signal
import shutil
import sqlite3
import subprocess
import sys
import time

import badw_model_worker as w
import badw_print_page_map as pm
import certify_badw_model_links as certifier
import run_badw_linking_campaign as c


def refresh_reader(baseline, manifest, output):
    """Publish sources only; verify every baseline shard and preserve all text/references.

    This is a complete reader build from a checked complete reader, not a partial
    catalogue. A changed lexical input requires the ordinary full builder instead.
    """
    from badw_html_print_facsimiles import Facsimiles
    baseline=Path(baseline); output=Path(output)
    meta=w.load(baseline/'manifest.json'); catalog=w.load(baseline/'data.json')
    if (meta['entries']!=29878 or len(catalog['entries'])!=29878 or
        meta['catalog_sha256']!=w.a.digest(baseline/'data.json')):
        raise ValueError('baseline reader is incomplete or corrupt')
    mutable={'data/badw_html_print_alignment.json','data/badw_html_print_alignment.generated.json'}
    for item in meta['inputs']:
        # Code changes do not alter saved lexical bodies. All lexical, editorial,
        # bibliography and reviewed relationship inputs must still be identical.
        if item['path'].startswith('scripts/') or item['path'] in mutable:
            continue
        if w.a.digest(w.a.ROOT/item['path'])!=item['sha256']:
            raise ValueError('lexical baseline input changed: '+item['path'])
    shutil.copytree(baseline,output)
    facsimiles=Facsimiles(manifest,output)
    changed=0
    for entry in catalog['entries']:
        path=output/entry['path']
        if w.a.digest(path)!=entry['sha256']:
            raise ValueError('baseline witness checksum changed: '+entry['id'])
        before=w.load(path); after=copy.deepcopy(before)
        after['sources']=[s for s in after['sources'] if not s.get('print_provenance') and not s.get('suggested_print_provenance')]
        facsimiles.attach(after)
        if {k:v for k,v in before.items() if k!='sources'}!={k:v for k,v in after.items() if k!='sources'}:
            raise ValueError('print publication changed witness text or references')
        if before!=after:
            w.write(path,after);entry['sha256']=w.a.digest(path);changed+=1
    if len(facsimiles.witnesses)!=sum(bool(s.get('print_provenance')) for e in catalog['entries']
        for s in w.load(output/e['path'])['sources']):
        raise ValueError('certified identities did not all attach exactly once')
    w.write(output/'data.json',catalog)
    w.write(output/'print_facsimiles.json',dict(**{k:facsimiles.data[k] for k in
        ('alignment_sha256','certificate_sha256','page_map_sha256','reviews_sha256','registry_sha256') if k in facsimiles.data},
        pages={k:p for k,p in facsimiles.data['pages'].items() if p['id'] in facsimiles.used},witnesses=facsimiles.data['witnesses']))
    (output/'provisional_print_links.json').unlink(missing_ok=True)
    meta.pop('provisional_print_links',None)
    meta['catalog_sha256']=w.a.digest(output/'data.json')
    for item in meta['inputs']:
        if item['path'] in mutable:item['sha256']=w.a.digest(w.a.ROOT/item['path'])
    meta['print_source_refresh']=dict(baseline_manifest_sha256=w.a.digest(baseline/'manifest.json'),checked_witnesses=29878,
        unchanged_text_and_references=29878,changed_sources=changed,page_map_sha256=w.a.digest(pm.PATH))
    w.write(output/'manifest.json',meta)
    print(json.dumps(dict(event='complete reader source refresh',witnesses=29878,changed=changed)),flush=True)


def recover(output):
    """Roll back an interrupted publication unless its reader pointer committed."""
    journal = output/'transaction.json'
    if not journal.exists():
        return
    tx = w.load(journal)
    current = output/'current'
    committed = current.is_symlink() and current.resolve() == Path(tx['generation']).resolve()
    if not committed:
        for dest, backup in tx['backups'].items():
            Path(dest).write_bytes(Path(backup).read_bytes())
    journal.unlink()


def publish(root, output):
    """Re-read and compile the latest ledger while holding the publication lock.

    Canonical files are restored on any build failure; the served generation
    changes only after all checks succeed. Recovery also covers SIGKILL.
    """
    output = w.private(output)
    with (root/'publication.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        recover(output)
        cfg = c.config(c.database(root))
        generation = output/('generation-'+str(time.time_ns()))
        stage = generation/'certification'
        summary = certifier.certify(root, cfg['bodies'], stage, fresh=True, stage=True)
        changed = (w.a.digest(stage/'certificate.json') != w.a.digest(w.a.CERTIFICATE))
        current = output/'current'
        if current.exists() and not changed:
            manifest = w.load(current/'pages/manifest.json')
            if (manifest.get('page_map_sha256') == w.a.digest(pm.PATH)
                    and manifest.get('certificate_sha256') == w.a.digest(w.a.CERTIFICATE)):
                return summary
        backups = {}
        queue_path=w.DATA/'badw_html_print_review_queue.json'
        provisional_path=w.DATA/'badw_html_print_provisional.generated.json'
        for dest in (w.a.CERTIFICATE, w.a.GENERATED, queue_path, provisional_path):
            backup = generation/('prior-'+dest.name)
            backup.write_bytes(dest.read_bytes())
            backups[str(dest)] = str(backup)
        w.write(output/'transaction.json', dict(generation=str(generation.resolve()), backups=backups))
        try:
            w.write(w.a.CERTIFICATE, w.load(stage/'certificate.json'))
            w.write(w.a.GENERATED, w.load(stage/'generated.json'))
            resources=w.authoritative(Path(cfg['bodies']))
            w.write(queue_path,w.a.review_queue(resources[0],w.load(w.DATA/'badw_html_print_pages.json'),
                resources[1],resources[2],resources[3]))
            prior=w.load(provisional_path)
            urls={r['source_url'] for r in w.load(w.a.GENERATED)['witnesses']}
            prior['witnesses']=[r for r in prior['witnesses'] if r['source_url'] not in urls]
            prior['certified_ledger_sha256']=w.a.digest(w.a.GENERATED)
            prior['summary']['published_provisional']=len(prior['witnesses'])
            w.write(provisional_path,prior)
            environment=dict(os.environ)
            environment['PYTHONPATH']=os.pathsep.join(sys.path)
            for command in (
                [sys.executable,'scripts/badw_html_print_alignment.py','--bodies',cfg['bodies'],'--check'],
                [sys.executable,'scripts/badw_html_print_facsimiles.py','--scans-root','.', '--output',str(generation/'pages')]):
                subprocess.run(command, cwd=w.a.ROOT, env=environment, check=True)
            baseline=current/'reader' if current.exists() else w.a.ROOT/'work/model-certified-20261113/reader'
            if baseline.exists():
                refresh_reader(baseline,generation/'pages/manifest.json',generation/'reader')
            else:
                subprocess.run([sys.executable,'scripts/build_badw_full_reader.py','--output',str(generation/'reader'),
                    '--print-facsimiles',str(generation/'pages/manifest.json')],cwd=w.a.ROOT,env=environment,check=True)
            manifest = w.load(generation/'reader/print_facsimiles.json')
            if manifest.get('certificate_sha256') != w.a.digest(w.a.CERTIFICATE):
                raise ValueError('reader is not bound to compiled certificates')
            if (generation/'reader/provisional_print_links.json').exists():
                raise ValueError('certified publication contains suggestions')
            count = len(manifest['witnesses'])
            w.write(generation/'publication.json', dict(certified=count, new=summary.get('certified',0),
                certificate_sha256=w.a.digest(w.a.CERTIFICATE), page_map_sha256=w.a.digest(pm.PATH)))
            temporary = output/'next'
            temporary.unlink(missing_ok=True)
            temporary.symlink_to(generation.resolve(), target_is_directory=True)
            os.replace(temporary, current)
            (output/'transaction.json').unlink()
            publication_db=c.database(root)
            with publication_db:
                c.event(publication_db,None,'local_reader_published',dict(output=str(current),
                    certified=count,certificate_sha256=w.a.digest(w.a.CERTIFICATE)))
            print(json.dumps(dict(event='published',certified=count,new=summary.get('certified',0),
                                  reader=str(current/'reader'))), flush=True)
            return summary
        except BaseException:
            recover(output)
            raise


def proposal(pack, resources):
    """Use the existing content-gap detector, with no midpoint fallback."""
    from badw_print_reconstruction import column_model, page_destination
    path = w.a.ROOT/'work/html-print-coordinate-hocr/index.sqlite'
    rows = {}
    if path.exists():
        with sqlite3.connect(path) as db:
            for n, text in db.execute('SELECT line,body FROM reading_lines WHERE family=? AND page=?',
                                      (pack['family'],pack['physical_page'])):
                coordinate = json.loads(text)
                qa = resources[5].get((pack['family'],pack['physical_page'],n), {})
                rows[n] = dict(coordinate=coordinate,line_text=qa.get('line_text',''))
    transform = pack['image']['transform']; box = transform['pdf_crop']
    geometry = dict(width=box[2]-box[0],height=box[3]-box[1],rotation=0,
                    landscape=box[2]-box[0]>box[3]-box[1],mediabox=box,
                    source_sha256=pack['source_sha256'],physical_page=pack['physical_page'])
    return page_destination(rows,geometry,column_model(rows,geometry),[])


def printed_pages(root, spec, resources, cfg, spending, client):
    """Source-check unreviewed layouts; never infer folios or split two columns."""
    from badw_html_print_facsimiles import derivative_id
    data = pm.load()
    source = resources[4][w.a.FAMILIES[spec['family']]]
    known = {k:p for k,p in data['pages'].items() if p['source_sha256']==source['sha256']
             and p['physical_page']==spec['physical_page']}
    # An older reviewed left crop is not a completed physical-scan census.
    # Its reviewed gutter also establishes the complementary right side;
    # numbering and article identities on that side remain unasserted.
    if known:
        box=certifier.original_media_box(str(w.a.ROOT/source['filename']),spec['physical_page'])
        sides={p['side'] for p in known.values()}
        if len(known)==1 and sides in ({'left'},{'right'}):
            p=next(iter(known.values())); crop=p['crop']
            if crop[1]==box[1] and crop[3]==box[3] and (
                (p['side']=='left' and crop[0]==box[0]) or
                (p['side']=='right' and crop[2]==box[2])):
                side='right' if p['side']=='left' else 'left'
                complement=[crop[2],box[1],box[2],box[3]] if side=='right' else [box[0],box[1],crop[0],box[3]]
                key='printed-'+derivative_id(source['sha256'],spec['physical_page'],complement)
                known[key]=dict(key=key,family=spec['family'],source=source['label'],source_sha256=source['sha256'],
                    physical_page=spec['physical_page'],crop=complement,side=side,volume=None,printed_page=None,
                    geometry_review='Complement of the previously source-reviewed full-height gutter crop: '+p['key'],
                    page_evidence='Registered physical scan; printed volume and folio not inferred.')
                data['pages'].update(known);w.write(pm.PATH,data)
    if not known:
        directory = w.private(root/'layouts'/(spec['family']+'-'+str(spec['physical_page'])))
        pack = w.load(directory/'pack.json') if (directory/'pack.json').exists() else w.prepare_page(spec,resources,directory,cfg['dpi'])
        if pack['family'] != spec['family'] or pack['physical_page'] != spec['physical_page']:
            raise ValueError('layout physical scan binding')
        certifier.source_geometry(str(root),directory.name,json.dumps(source,sort_keys=True),
            json.dumps(pack['image'],sort_keys=True),str(directory))
        pack['layout_proposal'] = proposal(pack,resources)
        request = w.request_spec('layout',pack,cfg['model'],cfg['detail'],cfg['max_output_tokens'])
        observed = w.execute(request,pack,directory/'cache',spending,client)
        w.write(directory/'layout.json',observed)
        layout = observed['result']
        if layout['layout'] in ('uncertain','blank') or layout['uncertainty'].strip():
            raise ValueError('layout '+layout['layout']+': '+layout['evidence'])
        source_path = str(w.a.ROOT/source['filename'])
        box = certifier.original_media_box(source_path,spec['physical_page'])
        candidates = [('single',box)]
        if layout['layout']=='spread':
            # Transform the independently observed image gutter into original PDF coordinates.
            x = w.image_to_pdf([layout['gutter_x'],0,layout['gutter_x']+1,1],pack['image']['transform'])[0]
            candidates = [('left',[box[0],box[1],x,box[3]]),('right',[x,box[1],box[2],box[3]])]
        for side,crop in candidates:
            key = 'printed-'+derivative_id(source['sha256'],spec['physical_page'],crop)
            known[key] = dict(key=key,family=spec['family'],source=source['label'],source_sha256=source['sha256'],
                physical_page=spec['physical_page'],crop=crop,side=side,volume=None,printed_page=None,
                geometry_review='Model source-layout verification; not human reviewed. '+layout['evidence'],
                page_evidence='Original physical scan and checksum; folio and volume not inferred.',
                layout_observation=observed)
        data['pages'].update(known)
        w.write(pm.PATH,data)
    # Historical duplicate geometries yield only one view.
    unique = {}
    for key,p in sorted(known.items()):
        unique.setdefault(tuple(p['crop']),dict(family=spec['family'],physical_page=spec['physical_page'],page_key=key))
    return list(unique.values())


def catalogue(root, resources):
    """Every acquired HTML identity is accounted for, including no candidate."""
    linked = {x['source_url'] for x in w.load(w.a.GENERATED)['witnesses']}
    linked.update(x['source_url'] for x in w.load(w.DATA/'badw_html_print_pages.json')['witnesses'])
    states = {}
    for path in root.glob('pages/*/source_review_packet.json'):
        for row in w.load(path)['associations']:
            states[row['source_url']] = row['state']
    rows = [dict(source_id=b['inspection_id'],source_url=b['source_url'],
                 state='certified' if b['source_url'] in linked else states.get(b['source_url'],'no candidate yet'))
            for b in resources[1].values() if b['source_kind']=='html']
    from collections import Counter
    w.write(root/'catalogue-progress.json',dict(entries=rows,counts=dict(Counter(x['state'] for x in rows)),updated=time.time()))


def complete(root, output, cache_only=False, limit=None, stop_after_response=False):
    """One invocation drains caches first, then source pages within the SAME cap."""
    import badw_campaign_review as review
    root=w.private(root); output=w.private(output)
    with (root/'controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        db=c.database(root); cfg=c.config(db)
        resources=w.authoritative(Path(cfg['bodies']))
        recover(output)
        publish(root,output)
        catalogue(root,resources)
        if cache_only:
            return dict(state='cache published',reader=str(output/'current/reader'))
        budget=w.private(cfg['budget_root']); approval=w.load(budget/'approval.json')
        state=w.load(budget/'spending.json')
        if (state['approval']!=w.a.object_digest(approval) or state['cap']>approval['approved_usd']
            or cfg['cap_usd']!=state['cap'] or state['cap']>20 or not approval['transmission_authorized']):
            raise ValueError('campaign, authorisation and shared ledger disagree')
        spending=w.Spending(budget,cfg['cap_usd'],w.a.object_digest(approval))
        from openai import OpenAI
        client=OpenAI(max_retries=0,timeout=600)
        (root/'STOP').unlink(missing_ok=True)
        (root/'REVIEW_STOP').unlink(missing_ok=True)
        stopping=False
        def stop(*_):
            nonlocal stopping
            stopping=True
        handlers={s:signal.signal(s,stop) for s in (signal.SIGTERM,signal.SIGINT)}
        w.write(root/'runtime.json',dict(pid=os.getpid(),state='running',started=time.time(),command='complete'))
        db.execute('CREATE TABLE IF NOT EXISTS production_scans(family TEXT,physical INTEGER,state TEXT,attempts INTEGER DEFAULT 0,reason TEXT,PRIMARY KEY(family,physical))')
        # Entire registered corpus, not the original 200-page plan. Prior article
        # links do not retire a physical page's remaining article census.
        with db:
            for family,n in db.execute('SELECT family,physical FROM coverage').fetchall():
                db.execute('INSERT OR IGNORE INTO production_scans(family,physical,state) VALUES(?,?,?)',(family,n,'pending'))
        completed=0; reason='corpus pass finished'
        try:
            # Reuse unfinished blind reviews before buying any new inventory.
            review.run(root,live=True)
            publish(root,output)
            mapped={(p['family'],p['physical_page']) for p in pm.load()['pages'].values()}
            queue=db.execute("SELECT * FROM production_scans WHERE state!='processed' AND attempts<3 ORDER BY attempts,physical,family").fetchall()
            queue.sort(key=lambda s:(s['attempts'],(s['family'],s['physical']) not in mapped,s['physical'],s['family']))
            for scan in queue:
                if stopping or (root/'STOP').exists() or (root/'REVIEW_STOP').exists() or (limit and completed>=limit):
                    reason='stopped; resume with the same command';break
                spec=dict(family=scan['family'],physical_page=scan['physical'])
                with db:
                    db.execute('UPDATE production_scans SET attempts=attempts+1 WHERE family=? AND physical=?',(scan['family'],scan['physical']))
                try:
                    views=printed_pages(root,spec,resources,cfg,spending,client)
                    for view_spec in views:
                        key=view_spec['family']+'-'+str(view_spec['physical_page'])+'-'+view_spec['page_key']
                        with db:
                            db.execute('INSERT OR IGNORE INTO views(id,spec,updated) VALUES(?,?,?)',(key,json.dumps(view_spec),time.time()))
                        view=db.execute('SELECT * FROM views WHERE id=?',(key,)).fetchone()
                        if view['stage']!='awaiting_review':
                            c.process(root,db,view,cfg,resources,spending,client)
                        if stop_after_response:
                            reason='commissioning stop after saved response';stopping=True;break
                        review.run(root,live=True,page=key)
                    if not stopping:
                        with db:
                            db.execute("UPDATE production_scans SET state='processed',reason=NULL WHERE family=? AND physical=?",(scan['family'],scan['physical']))
                    completed+=1
                    if completed%10==0:
                        publish(root,output);catalogue(root,resources)
                except Exception as exc:
                    safe=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__
                    with db:
                        db.execute("UPDATE production_scans SET state='unresolved',reason=? WHERE family=? AND physical=?",(safe,scan['family'],scan['physical']))
                        c.event(db,None,'production_exception',dict(**spec,reason=safe))
                    print(json.dumps(dict(event='abstained',**spec,reason=safe)),flush=True)
                    if 'spending' in safe.lower() or 'reservation retained' in safe.lower() or 'token-count preflight failed' in safe:
                        reason=safe;break
                print(json.dumps(dict(event='scan checkpoint',**spec,processed=completed)),flush=True)
        finally:
            publish(root,output);catalogue(root,resources)
            for sig,handler in handlers.items():signal.signal(sig,handler)
            w.write(root/'runtime.json',dict(pid=os.getpid(),state='invocation_finished',finished=time.time(),reason=reason))
        report=c.status(root,db)
        return dict(state=reason,processed=completed,reader=str(output/'current/reader'),
                    budget={k:report[k] for k in ('api_actual_usd','api_unresolved_reservations_usd','remaining_authorized_usd')})
