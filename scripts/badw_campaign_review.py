"""Blind source review of a campaign backlog. Never grants certificate authority.

Original responses remain immutable. Packets contain deterministic bindings and two
separate observations; agreement remains provisional pending a validated policy.
"""
import argparse
from collections import Counter
import copy
import fcntl
import json
import html
import os
import re
import signal
from pathlib import Path
import time

import badw_model_worker as w
import run_badw_linking_campaign as c


def recover_review(cached, spec, pack):
    """Reuse a paid, schema-valid reading without concealing failed quotations.

    Only whitespace may be repaired, at a unique exact component span. Invalid
    quotations or component locators become abstentions, never associations. The
    original paid response remains immutable in the worker cache.
    """
    if cached.get('response_status') == 'incomplete':
        raise ValueError('cached incomplete model response; excluded without a repeated paid request')
    if (cached.get('status') != 'rejected model response; no evidence authority'
            or cached.get('response_status') != 'completed'
            or cached.get('request') != spec
            or cached.get('request_sha256') != w.a.object_digest(spec)
            or cached.get('output_sha256') != w.a.object_digest(cached.get('output_text'))):
        raise ValueError('recovery requires an intact completed paid response')
    result = json.loads(cached['output_text'])
    from jsonschema import validate
    stage = spec['stage']
    if stage not in ('match', 'source_review'):
        raise ValueError('quotation recovery requires a matching response')
    validate(result, w.SCHEMAS[stage])
    candidates = {i['source_id']:i for i in pack['candidates']}
    changes = []
    for row in (result['matching']['matches'] if stage == 'source_review' else result['matches']):
        if row['outcome'] != 'supported':
            continue
        missing = [k for k in ('printed_evidence','boundary_evidence','homonym_evidence')
                   if not row[k].strip()]
        if missing:
            before = copy.deepcopy(row)
            row['outcome'] = 'insufficient'
            row['uncertainty'] += '; missing required evidence quarantined: ' + ', '.join(missing)
            changes.append(dict(item_id=row['item_id'],
                reason='missing required evidence quarantined without completing model testimony',
                before=before,after=copy.deepcopy(row)))
            continue
        body = candidates.get(row['source_id'])
        index = row['component_index']
        if body is None:
            raise ValueError('recovery cannot repair an identity binding')
        if index is None or not 0 <= index < len(body['components']):
            before = copy.deepcopy(row)
            row['outcome'] = 'insufficient'
            row['uncertainty'] += '; invalid component locator quarantined, not supported'
            changes.append(dict(item_id=row['item_id'],
                reason='invalid component locator quarantined without reassignment',
                before=before,after=copy.deepcopy(row)))
            continue
        source = body['components'][index]['source_form']
        quote = row['html_evidence']
        if quote.strip() and quote in source:
            continue
        words = quote.split()
        spans = list(re.finditer(r'\s+'.join(map(re.escape, words)), source)) if words else []
        before = copy.deepcopy(row)
        if len(spans) == 1:
            row['html_evidence'] = spans[0].group()
            reason = 'unique exact component span; whitespace-only repair'
        else:
            row['outcome'] = 'insufficient'
            row['uncertainty'] += '; exact HTML quotation failed; quarantined, not supported'
            reason = 'invalid or ambiguous quotation quarantined'
        changes.append(dict(item_id=row['item_id'],reason=reason,before=before,after=copy.deepcopy(row)))
    # All boundary, identity, homonym, omission and schema gates still apply.
    w.validate(stage, result, pack)
    if not changes:
        raise ValueError('no recoverable quotation failure')
    return dict(status='recovered provisional observation; no certificate authority',
        request=spec, request_sha256=w.a.object_digest(spec),
        result=result,result_sha256=w.a.object_digest(result),
        original_output_sha256=cached['output_sha256'], recovery=changes,
        model=cached['model'],response_id=cached['response_id'],
        usage=cached['usage'],usd=cached['usd'])


def overlap(a, b):
    area = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    return area / min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))


def reconcile(first_inventory, first_match, second):
    """Keep every proposal, including disagreements and unmatched second readings."""
    original = {i['item_id']: i for i in first_inventory['items']}
    observed = {i['item_id']: i for i in second['inventory']['items']}
    checks = second['matching']['matches']
    rows = []
    for match in first_match['matches']:
        if match['outcome'] != 'supported':
            continue
        heading = original[match['item_id']]
        nearby = [m for m in checks if overlap(heading['bbox'], observed[m['item_id']]['bbox']) >= .5]
        supported = [m for m in nearby if m['outcome'] == 'supported'
                     and m['source_id'] == match['source_id']
                     and observed[m['item_id']]['classification'] == 'article'
                     and observed[m['item_id']]['printed_homonym'] == heading['printed_homonym']]
        # A separately inventoried reference inside the heading region is not
        # another article. Retain it as evidence, but do not let an abstention
        # on that reference veto an otherwise unique article reading. A
        # competing supported identity of any classification still blocks it.
        articles = [m for m in nearby if observed[m['item_id']]['classification'] == 'article']
        competitors = [m for m in nearby if m['outcome'] == 'supported'
                       and m['source_id'] != match['source_id']]
        corroborated = len(supported) == 1 and len(articles) == 1 and not competitors
        rows.append(dict(item_id=match['item_id'], source_id=match['source_id'],
            state='model-source-reviewed' if corroborated else 'exception',
            reason='two blind source readings; not certification' if corroborated else
                   'second reading absent, ambiguous, conflicting or differently located',
            second_item_ids=[m['item_id'] for m in nearby]))
    return rows


def load_page(directory, resources, model, verified_sources=None):
    pack = w.load(directory/'pack.json')
    registry = resources[4][w.a.FAMILIES[pack['family']]]
    if pack['source_sha256'] != registry['sha256']:
        raise ValueError('registered source changed')
    if verified_sources is None or registry['sha256'] not in verified_sources:
        if w.a.digest(w.a.ROOT/registry['filename']) != registry['sha256']:
            raise ValueError('registered source changed')
        if verified_sources is not None:
            verified_sources.add(registry['sha256'])
    inv = w.checked_observation(directory/'inventory.json', 'inventory', pack, model)
    pack['inventory'] = inv['result']
    pack['candidates'] = w.retrieve(pack['inventory'], pack, resources[1])
    w.prepare_match_crops(pack, directory)
    match = w.checked_observation(directory/'match.json', 'match', pack, model)
    if match.get('recovery'):
        cached = w.load(directory/'cache'/(match['request_sha256']+'.json'))
        if recover_review(cached, match['request'], pack) != match:
            raise ValueError('recovered matching differs from immutable paid response')
    return pack, inv, match


def packet(pack, inv, match, second, resources, directory):
    bodies = resources[1]
    generated = w.load(w.a.GENERATED)['witnesses']
    accepted = {i['source_url'] for i in generated}
    manual = w.load(w.DATA/'badw_html_print_pages.json')
    # Manual attachments use the same authoritative source URL identities.
    def urls(value):
        if isinstance(value, dict):
            if 'source_url' in value: accepted.add(value['source_url'])
            for v in value.values(): urls(v)
        elif isinstance(value, list):
            for v in value: urls(v)
    urls(manual)
    headings = {i['item_id']:i for i in inv['result']['items']}
    crops = {i['item_id']:i for i in pack.get('match_images', [])}
    decisions = resources[0].get('decisions', [])
    rows = reconcile(inv['result'], match['result'], second['result']) if second else [
        dict(item_id=m['item_id'],source_id=m['source_id'],state='proposed',reason='blind source review pending',second_item_ids=[])
        for m in match['result']['matches'] if m['outcome']=='supported']
    for row in rows:
        sid = row['source_id']; body = bodies[sid]
        match_item = next(m for m in match['result']['matches'] if m['item_id']==row['item_id'])
        component = body['components'][match_item['component_index']]
        binding = pack['bindings'][sid]
        risks = []
        if not pack['geometry']: risks.append('printed folio and geometry need review')
        if not binding['anchors']: risks.append('direct-source pathway; no historical anchor')
        if headings[row['item_id']]['printed_homonym'] is not None: risks.append('numbered homonym')
        if len(match_item['html_evidence'].strip()) < 25: risks.append('short lexical evidence')
        if component.get('type') != 'definition': risks.append('non-definition component')
        previous = [d for d in decisions if isinstance(d,dict) and (d.get('source_id')==sid or d.get('source_url')==body['source_url'])]
        if previous: risks.append('previous decision requires explicit reconsideration')
        row.update(source_url=body['source_url'], html_sha256=binding['html_sha256'],
            already_certified=body['source_url'] in accepted,
            component_index=match_item['component_index'],component=component,
            component_sha256=w.a.object_digest(component),historical_anchors=binding['anchors'],
            previous_decisions=previous,heading=headings[row['item_id']],
            pdf_heading_bbox=w.image_to_pdf(headings[row['item_id']]['bbox'],pack['image']['transform']),
            image_crop=crops.get(row['item_id']),first_matching=match_item,risks=risks,
            publication_eligible=False)
    return dict(version=1,policy='provisional model source reading; no human or coding-agent source adjudication; no certificate authority',
        family=pack['family'],physical_page=pack['physical_page'],source_sha256=pack['source_sha256'],
        geometry=pack['geometry'],image=pack['image'],input_hashes=pack['input_hashes'],
        first_inventory_sha256=inv['result_sha256'],first_match_sha256=match['result_sha256'],
        second_observation_sha256=second['result_sha256'] if second else None,
        second_request_sha256=second['request_sha256'] if second else None,
        second_recovery=second.get('recovery',[]) if second else [],
        second_observation=second['result'] if second else None,associations=rows)


def unfinished_pages(pages, live=False, fixtures=None):
    """Consume paid caches first; bounded offline calls cannot starve behind gaps."""
    ready=[]
    for directory in pages:
        if (directory/'source_review.json').exists():
            continue
        cached=any(w.load(p).get('request',{}).get('stage')=='source_review'
                   for p in directory.glob('cache/*.json'))
        attempt=directory/'source-review-attempt.json'
        state=w.load(attempt) if attempt.exists() else {}
        if not cached and not live and not fixtures:
            continue
        if state.get('attempts',0)>=3:
            continue
        ready.append(((not cached,state.get('attempts',0),state.get('at',0),directory.name),directory))
    return [directory for _,directory in sorted(ready)]


def run(root, live=False, max_pages=None, fixtures=None, page=None):
    root=w.private(root)
    # Review has a separate stop flag: proposal STOP remains in force throughout.
    with (root/'source-review.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        db=c.database(root)
        cfg=c.config(db); resources=w.authoritative(Path(cfg['bodies']))
        client=spending=None
        if live:
            budget=w.private(cfg['budget_root']); approval=w.load(budget/'approval.json')
            if not (approval.get('approved_usd',0)>=cfg['cap_usd'] and approval.get('approver') and
                    approval.get('rights_basis') and approval.get('transmission_authorized') is True):
                raise ValueError('source transmission and spending approval required')
            from openai import OpenAI
            client=OpenAI(max_retries=0,timeout=600)
            spending=w.Spending(budget,cfg['cap_usd'],w.a.object_digest(approval))
        pages=sorted(p.parent for p in root.glob('pages/*/match.json'))
        if page:
            pages=[p for p in pages if p.name == page]
            if not pages: raise ValueError('unknown matched page')
        counts=Counter(); errors=[]
        summary=dict(counts={},errors=[],certified_additions=0)
        stopping=False
        def stop(signum, frame):
            nonlocal stopping
            stopping=True
        handlers={sig:signal.signal(sig,stop) for sig in (signal.SIGINT,signal.SIGTERM)}
        w.write(root/'source-review-runtime.json',dict(pid=os.getpid(),state='running',started=time.time()))
        try:
            # Bounded invocations advance past completed reviews. Offline full
            # refreshes still revalidate every saved observation without billing.
            if max_pages is not None or live:
                pages = unfinished_pages(pages,live,fixtures)
            verified_sources = set()
            attempted=0
            for directory in pages:
                if max_pages is not None and attempted>=max_pages: break
                if stopping or (root/'REVIEW_STOP').exists(): break
                try:
                    pack,inv,match=load_page(directory,resources,cfg['model'],verified_sources)
                    review_pack=copy.deepcopy(pack)
                    review_pack.pop('inventory',None); review_pack.pop('match_images',None)
                    spec=w.request_spec('source_review',review_pack,cfg['model'],cfg['detail'],cfg['max_output_tokens'])
                    cache=directory/'cache'/(w.a.object_digest(spec)+'.json')
                    second=None
                    # An interrupted request is not permission to buy it again.
                    # Keep it in the review queue while allowing other pages to
                    # use the explicitly approved remaining budget.
                    if live and not cache.exists():
                        requests=w.load(spending.directory/'spending.json')['requests']
                        prefix=w.a.object_digest(spec)+':'
                        if any(k.startswith(prefix) and 'actual' not in v for k,v in requests.items()):
                            errors.append(dict(page=directory.name,error='uncertain prior billing; skipped without retry'))
                            counts['billing_blocked_pages']+=1
                            continue
                    attempted+=1
                    if live or fixtures or cache.exists():
                        fixture=w.load(Path(fixtures)/directory.name/'source_review.json') if fixtures else None
                        try:
                            second=w.execute(spec,review_pack,directory/'cache',spending,client,fixture)
                        except ValueError:
                            if not cache.exists(): raise
                            second=recover_review(w.load(cache),spec,review_pack)
                        w.write(directory/'source_review.json',second)
                    result=packet(pack,inv,match,second,resources,directory)
                    w.write(directory/'source_review_packet.json',result)
                    with db:
                        c.event(db,directory.name,'source_reviewed',dict(associations=len(result['associations'])))
                    for row in result['associations']:
                        counts[row['state']]+=1
                        counts['already_certified']+=int(row['already_certified'])
                    counts['pages']+=1
                except Exception as exc:
                    safe=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__
                    errors.append(dict(page=directory.name,error=safe))
                    attempt=directory/'source-review-attempt.json'
                    previous=w.load(attempt) if attempt.exists() else {}
                    w.write(attempt,dict(attempts=previous.get('attempts',0)+1,at=time.time(),error=safe))
                    if 'spending' in safe.lower() or 'reservation retained' in safe.lower():
                        (root/'REVIEW_STOP').touch()
                        break
                summary=dict(counts=dict(counts),errors=errors,proposal_generation_stopped=(root/'STOP').exists(),
                    certified_additions=0,updated=time.time(),policy='No automatic certification; source-first accuracy audit pending')
                w.write(root/'source-review-status.json',summary)
                print(json.dumps(dict(page=directory.name,counts=dict(counts),last_error=errors[-1] if errors else None)),flush=True)
        finally:
            summary=dict(counts=dict(counts),errors=errors,certified_additions=0,
                updated=time.time(),policy='No automatic certification; source-first accuracy audit pending')
            w.write(root/'source-review-status.json',summary)
            for sig,handler in handlers.items(): signal.signal(sig,handler)
            w.write(root/'source-review-runtime.json',dict(pid=os.getpid(),state='stopped' if stopping or (root/'REVIEW_STOP').exists() else 'invocation_finished',finished=time.time()))
        return summary



def report(root):
    """Expose source packets, conflicts and spending; never install reader links."""
    root = w.private(root)
    def bound_file(directory, name):
        target=(directory/name).resolve()
        if not target.is_relative_to(root):
            raise ValueError('review asset escaped campaign directory')
        return target
    counts = Counter(); risks = Counter(); assignments = {}; packets = []
    for path in sorted(root.glob('pages/*/source_review_packet.json')):
        data = w.load(path)
        # The desk must fail closed on source/image mutation, even though none of
        # these provisional records has publication authority.
        if w.a.digest(bound_file(path.parent,data['image']['path'])) != data['image']['sha256']:
            raise ValueError('review image changed: '+path.parent.name)
        for row in data['associations']:
            crop = row.get('image_crop')
            if crop and w.a.digest(bound_file(path.parent,crop['path'])) != crop['sha256']:
                raise ValueError('review crop changed: '+path.parent.name)
            if w.a.object_digest(row['component']) != row['component_sha256']:
                raise ValueError('review component changed: '+row['source_id'])
            counts[row['state']] += 1
            counts['already_certified'] += int(row['already_certified'])
            risks.update(row['risks'])
            assignments.setdefault(row['source_id'], []).append(path.parent.name+':'+row['item_id'])
        packets.append((path,data))
    conflicts = {key:values for key,values in assignments.items() if len(values)>1}
    cfg = c.config(c.database(root))
    budget = Path(cfg['budget_root'])/'spending.json'
    requests = w.load(budget)['requests'] if budget.exists() else {}
    actual = sum(r.get('actual',0) for r in requests.values())
    reserved = sum(r['reserved'] for r in requests.values() if 'actual' not in r)
    result = dict(pages=len(packets),counts=dict(counts),risks=dict(risks),
        duplicate_source_assignments=conflicts,certified_additions=0,
        actual_usd=actual,unresolved_reserved_usd=reserved,
        remaining_usd=cfg['cap_usd']-actual-reserved,
        proposal_stop=(root/'STOP').exists(),review_stop=(root/'REVIEW_STOP').exists(),
        policy='Provisional evidence only. No automatic certificate authority.',updated=time.time())
    esc = lambda value:html.escape(str(value),quote=True)
    parts = ['<!doctype html><meta charset="utf-8"><title>Provisional source review</title>',
        '<style>body{font:16px sans-serif;max-width:1200px;margin:auto}img{max-width:100%}article{border-top:2px solid;padding:1em}pre{white-space:pre-wrap}</style>',
        '<h1>Provisional source review — not certified links</h1>',
        '<p>Model observations are not human or coding-agent image adjudication. Geometry, lexical identity and publication policy require review.</p>',
        '<pre>'+esc(json.dumps(result,ensure_ascii=False,indent=2))+'</pre>']
    for path,data in packets:
        parts.append('<h2>'+esc(path.parent.name)+'</h2>')
        relative = path.relative_to(root).as_posix()
        parts.append('<a href="'+esc(relative)+'">Checksum-bound source packet</a>')
        for row in data['associations']:
            parts.append('<article><h3>'+esc(row['heading']['heading_loc'])+' — '+esc(row['state'])+'</h3>')
            parts.append('<p>'+esc(row['source_id'])+'; printed homonym: '+esc(row['heading']['printed_homonym'])+'</p>')
            # HTML sources are authoritative BAdW HTTP(S) URLs. Never render a
            # model-supplied URL or arbitrary script URI as a clickable link.
            url = row['source_url']
            if url.startswith(('https://','http://')):
                parts.append('<a rel="noreferrer" href="'+esc(url)+'">Acquired HTML identity</a>')
            crop = row.get('image_crop')
            image = crop['path'] if crop else data['image']['path']
            target = (path.parent/image).resolve().relative_to(root).as_posix()
            parts.append('<p><a href="'+esc(target)+'"><img loading="lazy" alt="Original source crop" src="'+esc(target)+'"></a></p>')
            second = data.get('second_observation')
            checks = [] if not second else [dict(heading=i,matching=m)
                for i in second['inventory']['items'] for m in second['matching']['matches']
                if i['item_id'] == m['item_id'] and i['item_id'] in row['second_item_ids']]
            parts.append('<pre>'+esc(json.dumps(dict(heading=row['heading'],first_matching=row['first_matching'],
                independent_readings=checks,component=row['component'],risks=row['risks']),ensure_ascii=False,indent=2))+'</pre></article>')
    (root/'source-review.html').write_text('\n'.join(parts),encoding='utf-8')
    w.write(root/'source-review-report.json',result)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--live',action='store_true')
    p.add_argument('--report',action='store_true',help='Build a private provisional review desk without paid calls')
    p.add_argument('--max-pages',type=int)
    p.add_argument('--page',help='Process one named existing page, including a cached review')
    p.add_argument('--api-key-file',type=Path,help='Read a private API key without putting it in shell history')
    p.add_argument('--fixtures',type=Path)
    args=p.parse_args()
    if args.api_key_file:
        os.environ['OPENAI_API_KEY']=args.api_key_file.read_text().strip()
    if args.max_pages is not None and args.max_pages<1: p.error('max-pages must be positive')
    if args.report:
        print(json.dumps(report(args.campaign),indent=2))
    else:
        run(args.campaign,args.live,args.max_pages,args.fixtures,args.page)

if __name__=='__main__': main()
