"""Bounded, resumable source-inspection worker. Outputs are observations, never approvals.

All run artifacts must remain in ignored work/. Accepted certificates are deliberately
not an output format. Use prepare_badw_print_drafts and the ordinary compiler after
source review. The live gate requires a local rights/budget record and an API key.
"""
import argparse
import base64
import concurrent.futures
import csv
import fcntl
import json
import math
import os
from pathlib import Path
import threading
import time

import badw_html_print_alignment as a
import prepare_badw_print_drafts as drafts

VERSION = 1
DATA = a.ROOT/'data'
RATES = {'gpt-6-luna': (0.10, 0.01, 0.50), 'gpt-6.1-terra': (1.00, 0.05, 5.00)}
PRICING_CHECKED = '2026-11-11; standard service, including long-context adjustment; USD per million tokens'
PRICING_URL = 'https://developers.openai.com/api/docs/pricing'
# Official model pages specify these limits. Reserving the entire input allowance
# at the long-context tariff bounds image charges without assuming an undocumented
# image patch multiplier. Actual usage, including cached tokens, is reconciled.
# https://developers.openai.com/api/docs/models/gpt-6-luna
# https://developers.openai.com/api/docs/models/gpt-6.1-terra
MAX_INPUT_TOKENS = {'gpt-6-luna': 922000, 'gpt-6.1-terra': 922000}
RATE_LOCK = threading.Lock()
LAST_REQUEST = 0.0


def load(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def private(path):
    path = Path(path).resolve()
    if not path.is_relative_to((a.ROOT/'work').resolve()):
        raise ValueError('source material and worker outputs must stay in ignored work/')
    path.mkdir(parents=True, exist_ok=True)
    return path


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


S = dict(type='string')
NULL_S = dict(type=['string', 'null'])
BOX = dict(type='array', items=dict(type='number'), minItems=4, maxItems=4)
ITEM = obj(dict(item_id=S, heading_loc=NULL_S, heading_tibetan=NULL_S,
    printed_homonym=dict(type=['integer','null']), bbox=BOX, column=S,
    classification=dict(type='string', enum=['article','running_header','continuation','quotation','embedded_reference','uncertain']),
    printed_evidence=S, preceding=S, following=S, uncertainty=S))
SCHEMAS = {
 'inventory': obj(dict(visible_folios=S, completeness=dict(type='string', enum=['provisional_complete','partial','unreadable']),
                       limitations=S, items=dict(type='array', items=ITEM))),
 'match': obj(dict(matches=dict(type='array', items=obj(dict(item_id=S,
    outcome=dict(type='string', enum=['supported','ambiguous','unmatched','insufficient']),
    source_id=NULL_S, component_index=dict(type=['integer','null']), printed_evidence=S,
    html_evidence=S, boundary_evidence=S, homonym_evidence=S, alternatives=S, uncertainty=S)))))
}
SCHEMAS['source_review'] = obj(dict(inventory=SCHEMAS['inventory'], matching=SCHEMAS['match']))
SCHEMAS['layout'] = obj(dict(layout=dict(type='string', enum=['single','spread','blank','uncertain']),
    gutter_x=dict(type=['number','null']), evidence=S, uncertainty=S))


def validate(stage, result, pack):
    from jsonschema import validate as schema_validate
    schema_validate(result, SCHEMAS[stage])
    if stage == 'layout':
        if result['layout'] == 'spread':
            x = result['gutter_x']
            if x is None or not .25*pack['image']['pixels'][0] < x < .75*pack['image']['pixels'][0]:
                raise ValueError('spread gutter outside central region')
        elif result['gutter_x'] is not None:
            raise ValueError('gutter supplied without a spread')
        if not result['evidence'].strip():
            raise ValueError('layout observation missing')
        return
    if stage == 'source_review':
        validate('inventory', result['inventory'], pack)
        validate('match', result['matching'], dict(pack, inventory=result['inventory']))
        return
    if stage == 'inventory':
        ids = set()
        for item in result['items']:
            if not item['item_id'] or item['item_id'] in ids:
                raise ValueError('duplicate or empty inventory item ID')
            ids.add(item['item_id'])
            x0,y0,x1,y1 = item['bbox']
            w,h = pack['image']['pixels']
            if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
                raise ValueError('inventory coordinates outside supplied image')
        return
    items = {r['item_id']:r for r in pack['inventory']['items']}
    candidates = {r['source_id']:r for r in pack['candidates']}
    seen, assigned = set(), set()
    for r in result['matches']:
        if r['item_id'] not in items or r['item_id'] in seen:
            raise ValueError('unknown or repeated inventory item')
        seen.add(r['item_id'])
        sid = r['source_id']
        if sid is not None and sid not in candidates:
            raise ValueError('model invented an HTML identity')
        if r['outcome'] == 'supported':
            if items[r['item_id']]['classification'] != 'article' or sid is None or sid in assigned:
                raise ValueError('supported identity lacks a unique independent heading')
            assigned.add(sid)
            components = candidates[sid]['components']
            index = r['component_index']
            if index is None or not 0 <= index < len(components):
                raise ValueError('unsupported component locator')
            if not r['html_evidence'].strip() or r['html_evidence'] not in components[index]['source_form']:
                raise ValueError('HTML evidence is not an exact supplied component quote')
            if not all(r[k].strip() for k in ('printed_evidence','boundary_evidence','homonym_evidence')):
                raise ValueError('supported match lacks substantive evidence')
    if seen != set(items):
        raise ValueError('matching silently omitted inventory items')


def authoritative(bodies_path):
    cert = load(a.CERTIFICATE)
    for filename, checksum in cert['inputs'].items():
        if a.digest(a.ROOT/filename) != checksum:
            raise ValueError('stale pinned input: '+filename)
    bodies = load(bodies_path)
    anchors = {r['anchor_id']:r for r in map(json.loads, (a.ROOT/a.INPUTS['anchors']).open())}
    edges = list(map(json.loads, (a.ROOT/a.INPUTS['edges']).open()))
    registry = {r['label']:r for r in csv.DictReader((DATA/'source_pdfs.tsv').open(), delimiter='\t')}
    qa = {}
    for family in a.FAMILIES:
        for row in csv.DictReader((a.ROOT/f'release/current/qa/{family}/{family}_line_zones.tsv').open(), delimiter='\t'):
            qa[family,int(row['page']),int(row['line'])] = row
    return cert,bodies,anchors,edges,registry,qa


def candidate(body):
    # No accepted decisions, previous review prose, C11 ranking or confidence.
    return dict(source_id=body['inspection_id'], headword=body['headword'], homonym=body['homonym'],
                components=body['components'])


def prepare_page(spec, resources, directory, dpi=240):
    import pymupdf as fitz
    if not 72 <= dpi <= 600:
        raise ValueError('DPI must be between 72 and 600')
    cert,bodies,anchors,edges,registry,qa = resources
    family,physical = spec['family'],spec['physical_page']
    source = registry[a.FAMILIES[family]]
    pdf = a.ROOT/source['filename']
    if a.digest(pdf) != source['sha256']:
        raise ValueError('original scan checksum differs')
    directory = private(directory)
    with fitz.open(pdf) as document:
        if not isinstance(physical, int) or isinstance(physical, bool) or not 1 <= physical <= len(document):
            raise ValueError('physical PDF page must be a positive in-range integer')
        page = document[physical-1]
        if page.rotation:
            raise ValueError('rotated pages require an explicitly reviewed transform')
        # A spec may name a previously reviewed printed-page key, never an invented crop.
        reviewed = [p for p in cert['pages'] if p['key'] == spec.get('page_key')]
        if not reviewed and spec.get('page_key'):
            import badw_print_page_map
            mapped = badw_print_page_map.load()['pages'].get(spec['page_key'])
            if mapped:
                reviewed = [mapped]
        if spec.get('page_key') and len(reviewed) != 1:
            raise ValueError('unknown reviewed geometry')
        geometry = reviewed[0] if reviewed else None
        if geometry and (geometry['family'],geometry['physical_page']) != (family,physical):
            raise ValueError('reviewed geometry belongs to another source page')
        box = geometry['crop'] if geometry else list(page.mediabox)
        # PDF bottom-left → PyMuPDF top-left; store both and the exact image mapping.
        clip = fitz.Rect(box) * page.transformation_matrix
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72), clip=clip, alpha=False)
        # Explicit image cap; never silently rely on service resizing.
        if math.ceil(pix.width/32)*math.ceil(pix.height/32) > 30000:
            raise ValueError('image exceeds original-detail patch cap; lower DPI or supply reviewed side')
        image = directory/'page.png'
        pix.save(image)
        transform = dict(pdf_crop=box, image_device_origin=[pix.x,pix.y],
                         points_per_pixel=[72/dpi,72/dpi],
                         pdf_coordinate_system='bottom-left; image top-left; use page transformation matrix',
                         pdf_to_mupdf=list(page.transformation_matrix))
    page_anchors = {k:v for k,v in anchors.items() if (v['volume'],v['start_page']) == (family,physical)}
    ids = sorted({r['source_id'] for r in edges if r['local_anchor_id'] in page_anchors and r['source_id'] in bodies
                  and bodies[r['source_id']]['source_kind'] == 'html'})
    pack = dict(version=VERSION, status='preparation only; no attachment authority', family=family,
        physical_page=physical, source=source['label'], source_sha256=source['sha256'],
        geometry={k:geometry[k] for k in ('key','volume','printed_page','side','crop')} if geometry else None,
        image=dict(path='page.png', sha256=a.digest(image), pixels=[pix.width,pix.height], dpi=dpi, transform=transform),
        candidates=[candidate(bodies[sid]) for sid in ids],
        bindings={sid:dict(html_sha256=bodies[sid]['sources'][0]['sha256'], source_url=bodies[sid]['source_url'],
                          anchors=sorted({e['local_anchor_id'] for e in edges if e['source_id']==sid and e['local_anchor_id'] in page_anchors})) for sid in ids},
        input_hashes=cert['inputs'])
    write(directory/'pack.json', pack)
    return pack


def retrieve(inventory, pack, bodies):
    """Direct exact-heading retrieval supplements C6/C11 without manufacturing edges."""
    names = {a.proof_key(r['heading_loc']) for r in inventory['items'] if r['heading_loc']}
    result = {r['source_id']:r for r in pack['candidates']}
    for sid,body in bodies.items():
        if body['source_kind']=='html' and a.proof_key(body['headword']['loc']) in names:
            result[sid] = candidate(body)
            # Newly retrieved witnesses have exact HTML bindings but no invented
            # historical association. This distinction survives into review.
            pack.setdefault('bindings', {}).setdefault(sid, dict(
                html_sha256=body['sources'][0]['sha256'], source_url=body['source_url'], anchors=[]))
    return [result[k] for k in sorted(result)]


def image_to_pdf(box, transform):
    """Map a parent-image pixel rectangle back to registered PDF points."""
    aa,bb,cc,dd,ee,ff = transform['pdf_to_mupdf']
    determinant = aa*dd-bb*cc
    if not determinant:
        raise ValueError('singular source image transform')
    sx,sy = transform['points_per_pixel']
    ox,oy = transform['image_device_origin']
    corners=[]
    for x,y in ((box[0],box[1]),(box[2],box[3])):
        u,v=(x+ox)*sx-ee,(y+oy)*sy-ff
        corners.append(((dd*u-cc*v)/determinant,(-bb*u+aa*v)/determinant))
    return [min(x for x,y in corners),min(y for x,y in corners),
            max(x for x,y in corners),max(y for x,y in corners)]


def combined_prediction(pack, inventory, matching):
    """Lossless scorer adapter for the real two-stage outputs, never a review.

    Unmatched, excluded and abstaining inventory items remain present. A proposed
    identity on an abstention is retained as a proposal, never scored as a link.
    Callers loading saved observations must rebind them with checked_observation.
    """
    validate('inventory', inventory, pack)
    validate('match', matching, dict(pack, inventory=inventory))
    by_id={r['item_id']:r for r in matching['matches']}
    items=[]
    for observation in inventory['items']:
        match=by_id[observation['item_id']]
        row=dict(observation, source_id=match['source_id'] if match['outcome']=='supported' else None,
                 match=match)
        if pack['image']['transform']:
            row['pdf_bbox']=image_to_pdf(row['bbox'],pack['image']['transform'])
        items.append(row)
    return dict(status='model prediction; no source-review authority',
        source_image_sha256=pack['image']['sha256'],
        source_identity={k:pack.get(k) for k in ('family','physical_page','source_sha256','geometry')},
        image_transform=pack['image']['transform'], inventory_sha256=a.object_digest(inventory),
        matching_sha256=a.object_digest(matching), items=items)


def prepare_match_crops(pack, directory, padding=24):
    """Targeted provisional regions; coordinates always refer to the parent image.

    Inventory boxes may cover just headings. Include the space below each box up
    to the next observed start in its column. These are reading aids, not reviewed
    article boundaries or certificate geometry.
    """
    from PIL import Image
    directory=private(directory)
    image=directory/pack['image']['path']
    if a.digest(image) != pack['image']['sha256']:
        raise ValueError('prepared image changed')
    validate('inventory',pack['inventory'],pack)
    regions=[]
    with Image.open(image) as parent:
        width,height=parent.size
        for index,item in enumerate(pack['inventory']['items']):
            x0,y0,x1,y1=item['bbox']
            below=[r['bbox'][1] for r in pack['inventory']['items']
                   if r['column']==item['column'] and r['bbox'][1]>=y1 and r['item_id']!=item['item_id']]
            end=min(below) if below else min(height,y1+height/3)
            column=[r['bbox'] for r in pack['inventory']['items'] if r['column']==item['column']]
            # Heading boxes alone may omit the right-hand part of a definition.
            # Use the observed column envelope, bounded by neighbouring columns.
            left=min(r[0] for r in column)
            other_right=[r['bbox'][0] for r in pack['inventory']['items']
                         if r['column']!=item['column'] and r['bbox'][0]>max(q[2] for q in column)]
            right=min(other_right)-padding if other_right else width
            box=[max(0,math.floor(left-padding)),max(0,math.floor(y0-padding)),
                 min(width,math.ceil(max(x1,right))),min(height,math.ceil(max(y1,end)+padding))]
            # Different models may inventory this same page concurrently. Their
            # provisional regions must never overwrite one another's crops.
            inventory_key=a.object_digest(pack['inventory'])[:16]
            path=directory/f'article-{inventory_key}-{index:04d}.png'
            parent.crop(box).save(path)
            regions.append(dict(item_id=item['item_id'], path=path.name, sha256=a.digest(path),
                pixels=[box[2]-box[0],box[3]-box[1]],parent_bbox=box,
                pdf_bbox=image_to_pdf(box,pack['image']['transform']),
                coordinate_note='Crop pixel (x,y) = parent pixel (x+parent_bbox[0],y+parent_bbox[1]); provisional reading region'))
    pack['match_images']=regions
    return regions


def request_spec(stage, pack, model, detail, max_output_tokens):
    prompt = (DATA/f'badw_model_{stage}_prompt.txt').read_text()
    # Inventory is genuinely source-first. No candidates or previous answers.
    evidence = dict(image_pixels=pack['image']['pixels']) if stage in ('inventory','layout') else dict(
        candidates=[
            dict({k:v for k,v in row.items() if k in ('source_id','headword','homonym')},
                 # Keep original component indices and all lexical alternatives,
                 # but omit acquisition/layout metadata unnecessary to matching.
                 components=[{k:v for k,v in component.items() if k in ('type','source_form')}
                             for component in row['components']])
            for row in pack['candidates']])
    if stage == 'match':
        evidence['inventory'] = pack['inventory']
    if stage == 'layout':
        evidence['coordinate_layout_proposal'] = pack.get('layout_proposal')
    if stage == 'source_review':
        # Deliberately exclude earlier inventory, matches, confidence, verdicts,
        # source bindings and crop filenames derived from the first decision.
        evidence['image_pixels'] = pack['image']['pixels']
    if stage=='match' and pack.get('match_images'):
        evidence['article_images']=pack['match_images']
    return dict(version=VERSION, stage=stage, model=model, detail=detail, prompt=prompt,
        schema=SCHEMAS[stage], evidence=evidence, image_sha256=pack['image']['sha256'],
        service_tier='default', billing_bound='documented full input allowance at long-context tariff',
        source_binding_sha256=a.object_digest({k:pack.get(k) for k in
            ('family','physical_page','source_sha256','geometry','input_hashes','bindings')}),
        transform=pack['image']['transform'], max_output_tokens=max_output_tokens,
        pricing=PRICING_CHECKED, rates=list(RATES[model]))


def cost(model, input_tokens, output_tokens, cached_tokens=0, cache_write_tokens=0):
    # Default 30-minute cache writes replace ordinary input billing at 1.25x.
    # https://developers.openai.com/api/docs/guides/prompt-caching
    if (min(input_tokens,output_tokens,cached_tokens,cache_write_tokens)<0
            or cached_tokens+cache_write_tokens>input_tokens
            or input_tokens>MAX_INPUT_TOKENS[model] or output_tokens>128000):
        raise ValueError('invalid usage or model token limit exceeded')
    i,c,o = RATES[model]
    if input_tokens>272000:
        i,c,o=i*2,c*2,o*1.5
    return ((input_tokens-cached_tokens-cache_write_tokens)*i+cached_tokens*c
            +cache_write_tokens*i*1.25+output_tokens*o)/1_000_000


def checked_observation(path, stage, pack, model):
    """Rebind saved observations to current inputs and prompts before reuse."""
    record = load(path)
    saved = record.get('request', {})
    if saved.get('stage') != stage or saved.get('model') != model:
        raise ValueError('observation lacks the requested stage/model binding')
    expected = request_spec(stage, pack, model, saved['detail'], saved['max_output_tokens'])
    if (saved != expected or record['request_sha256'] != a.object_digest(expected)
            or record['result_sha256'] != a.object_digest(record['result'])):
        raise ValueError('stale or corrupt observation binding')
    image = Path(path).parent/pack['image']['path']
    if a.digest(image) != expected['image_sha256']:
        raise ValueError('prepared image changed')
    for crop in pack.get('match_images', []) if stage=='match' else []:
        if a.digest(Path(path).parent/crop['path']) != crop['sha256']:
            raise ValueError('article crop changed')
    validate(stage, record['result'], pack)
    return record


class Spending:
    """Cross-process reservation ledger. Ambiguous network outcomes remain reserved."""
    def __init__(self, directory, cap, approval):
        self.directory = private(directory)
        self.cap = cap
        self.approval = approval

    def extend(self, previous_approval, authorization):
        """Apply an explicitly renewed cap without erasing uncertain billing."""
        if not authorization or not self.approval or self.approval == previous_approval:
            raise ValueError('new explicit authorization required')
        with (self.directory/'spending.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = self.directory/'spending.json'
            state = load(path)
            if state['approval'] != previous_approval or self.cap <= state['cap']:
                raise ValueError('previous approval mismatch or cap not increased')
            state.setdefault('authorization_history', []).append(dict(
                approval=state['approval'], cap=state['cap'],
                renewed_by=authorization, renewed_at=time.time()))
            state.update(approval=self.approval, cap=self.cap)
            write(path, state)
            return state

    def change(self, key, reservation=None, actual=None, usage=None):
        with (self.directory/'spending.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = self.directory/'spending.json'
            state = load(path) if path.exists() else dict(approval=self.approval, cap=self.cap, requests={})
            if state['approval'] != self.approval or state['cap'] != self.cap:
                raise ValueError('run approval/cap changed; start a separately approved run')
            if reservation is not None:
                if key in state['requests']:
                    raise ValueError('request already reserved: reconcile uncertain outcome before retry')
                total = sum(r.get('actual',r['reserved']) for r in state['requests'].values())
                if total+reservation > self.cap:
                    raise ValueError('spending cap would be exceeded')
                state['requests'][key] = dict(reserved=reservation)
            if actual is not None:
                if actual > state['requests'][key]['reserved']:
                    raise ValueError('usage exceeded conservative reservation; stop and reconcile billing')
                state['requests'][key].update(actual=actual,usage=usage)
            write(path,state)
            return state


def execute(spec, pack, directory, spending=None, client=None, fixture=None, interval=1.0, attempts=3):
    directory = private(directory)
    key = a.object_digest(spec)
    path = directory/(key+'.json')
    image = directory.parent/pack['image']['path']
    if a.digest(image) != spec['image_sha256']:
        raise ValueError('prepared image changed')
    images=pack.get('match_images',[]) if spec['stage']=='match' else []
    for crop in images:
        if a.digest(directory.parent/crop['path']) != crop['sha256']:
            raise ValueError('article crop changed')
    if path.exists():
        cached = load(path)
        if cached.get('status') == 'rejected model response; no evidence authority':
            if (cached.get('request') != spec or cached.get('request_sha256') != key
                    or cached.get('output_sha256') != a.object_digest(cached.get('output_text'))):
                raise ValueError('corrupt cached rejected response')
            raise ValueError('cached rejected model response; inspect private cache; no repeated paid request')
        if cached.get('request') != spec or cached['request_sha256'] != key or cached['result_sha256'] != a.object_digest(cached['result']):
            raise ValueError('corrupt cached observation')
        validate(spec['stage'],cached['result'],pack)
        return cached
    if fixture is not None:
        result = fixture
        validate(spec['stage'],result,pack)
        output = dict(status='offline fixture; no source review or attachment authority', request_sha256=key,
                      request=spec, result=result, result_sha256=a.object_digest(result), usage=None, usd=0)
        write(path,output)
        return output
    if client is None or spending is None:
        raise ValueError('live execution requires client and approved spending ledger')
    if (spending.directory/'STOP').exists():
        raise ValueError('operator stop file present')
    content = [dict(type='input_text',text=spec['prompt']+'\n'+json.dumps(spec['evidence'],ensure_ascii=False))]
    for region in images or [dict(path=pack['image']['path'],item_id='entire printed page')]:
        content.append(dict(type='input_text',text='Image for '+region['item_id']))
        content.append(dict(type='input_image',image_url='data:image/png;base64,'+
            base64.b64encode((directory.parent/region['path']).read_bytes()).decode(),detail=spec['detail']))
    request_input = [dict(role='user',content=content)]
    request_text = dict(format=dict(type='json_schema',name='wts_'+spec['stage'],strict=True,schema=spec['schema']))
    # A request-bound count is mandatory, including on older SDKs. Cached
    # responses and offline fixtures return above without reaching this gate.
    tokens = MAX_INPUT_TOKENS[spec['model']]
    count_path = directory/(key+'-tokens.json')
    if count_path.exists():
        try:
            counted = load(count_path)
        except (OSError, ValueError):
            raise ValueError('unreadable cached token count; no generation request or reservation made') from None
        if not isinstance(counted, dict) or counted.get('request_sha256') != key:
            raise ValueError('token count request binding changed; no generation request or reservation made')
        count = counted.get('input_tokens')
    else:
        counter = getattr(getattr(getattr(client, 'responses', None),
                                  'input_tokens', None), 'count', None)
        if not callable(counter):
            raise RuntimeError('token-count preflight unavailable in SDK and no request-bound cached count; '
                               'no generation request or reservation made')
        try:
            counted = counter(model=spec['model'],input=request_input,text=request_text)
            count = getattr(counted, 'input_tokens', None)
        except Exception as exc:
            raise RuntimeError('token-count preflight failed ('+type(exc).__name__+'); no generation request or reservation made') from None
    if type(count) is not int or not 0 < count <= tokens:
        raise ValueError('invalid input token count; no generation request or reservation made')
    if not count_path.exists():
        write(count_path, dict(request_sha256=key,input_tokens=count))
    # Reserve the existing safety margin, highest cache-write tariff and the
    # entire configured output ceiling, using this exact request's input count.
    tokens = min(tokens,math.ceil(count*1.05)+256)
    reservation = cost(spec['model'],tokens,spec['max_output_tokens'],cache_write_tokens=tokens)
    start = time.monotonic()
    for attempt in range(attempts):
        if (spending.directory/'STOP').exists():
            raise ValueError('operator stop file present')
        attempt_key = key+':'+str(attempt)
        spending.change(attempt_key,reservation=reservation)
        global LAST_REQUEST
        with RATE_LOCK:
            time.sleep(max(0,interval-(time.monotonic()-LAST_REQUEST)))
            LAST_REQUEST = time.monotonic()
        try:
            response = client.responses.create(model=spec['model'],store=False,service_tier='default',
                input=request_input,max_output_tokens=spec['max_output_tokens'],text=request_text,
                extra_headers={'Idempotency-Key':attempt_key})
        except Exception as exc:
            # SDK retries are disabled. Only explicit rate-limit responses are
            # retried; timeouts/5xx may have incurred charges and stay unresolved.
            error_body = getattr(exc, 'body', None)
            error_body = error_body if isinstance(error_body, dict) else {}
            error_body = error_body.get('error', error_body)
            error_body = error_body if isinstance(error_body, dict) else {}
            # Log only bounded enum-like identifiers, never server messages,
            # credentials or echoed request content.
            error_code = error_body.get('code')
            error_type = error_body.get('type')
            safe_identifier = lambda value: value if isinstance(value, str) and len(value) <= 80 and all(c.isalnum() or c == '_' for c in value) else None
            error_code, error_type = map(safe_identifier, (error_code, error_type))
            rejected = getattr(exc,'status_code',None)==429
            quota_failure = error_type == 'insufficient_quota' or error_code in {
                'insufficient_quota', 'credit_balance_exhausted',
                'organization_spend_limit_exceeded', 'project_spend_limit_exceeded',
                'organization_usage_limit_exceeded'}
            if rejected:
                spending.change(attempt_key,actual=0)
                if not quota_failure and attempt+1 < attempts:
                    time.sleep(min(2**attempt,8))
                    continue
            write(directory/(key+'-failure.json'), dict(exception_type=type(exc).__name__,
                status_code=getattr(exc,'status_code',None),request_id=getattr(exc,'request_id',None),
                error_code=error_code,error_type=error_type,reservation_retained=not rejected))
            if not rejected:
                # Stop every process sharing this authorisation, not just this
                # page. Further calls would accumulate unresolved liabilities.
                (spending.directory/'STOP').touch()
            disposition = 'request rejected without usage' if rejected else 'reservation retained'
            raise RuntimeError('API request failed ('+type(exc).__name__+', '+str(error_code)+'); '+disposition+'; inspect local ledger') from None
        usage = response.usage.model_dump()
        cached_tokens = (usage.get('input_tokens_details') or {}).get('cached_tokens',0)
        written_tokens = (usage.get('input_tokens_details') or {}).get('cache_write_tokens',0) or 0
        usd = cost(spec['model'],usage['input_tokens'],usage['output_tokens'],cached_tokens,written_tokens)
        spending.change(attempt_key,actual=usd,usage=usage)
        # Persist paid observations before parsing or checking them. Invalid
        # quotations and truncated JSON are benchmark findings, not permission
        # to repeat a paid request or discard the evidence of failure.
        rejected = dict(status='rejected model response; no evidence authority',
            request=spec,request_sha256=key,output_text=response.output_text,
            output_sha256=a.object_digest(response.output_text),model=spec['model'],
            response_status=response.status,response_id=response.id,usage=usage,
            usd=usd,elapsed_seconds=time.monotonic()-start)
        write(path,rejected)
        if response.status != 'completed':
            raise ValueError('incomplete model response; not evidence')
        result = json.loads(response.output_text)
        validate(spec['stage'],result,pack)
        output = dict(status='model observation; source inspection required; no attachment authority',
            request=spec,request_sha256=key,result=result,result_sha256=a.object_digest(result),model=spec['model'],
            response_id=response.id,usage=usage,usd=usd,elapsed_seconds=time.monotonic()-start)
        write(path,output)
        return output
    raise RuntimeError('bounded attempts exhausted')


def review_drafts(pack, result, resources):
    cert,bodies,anchors,edges,registry,qa = resources
    pending,missing = [],[]
    for match in result['matches']:
        if match['outcome'] != 'supported':
            continue
        sid = match['source_id']
        if any(sid==r['source_id'] for p in cert['pages'] for r in p['accepted']):
            continue
        anchor_ids = pack['bindings'].get(sid,{}).get('anchors',[])
        if len(anchor_ids) != 1:
            missing.append(dict(source_id=sid,reason='missing or ambiguous historical heading association',observation=match))
            continue
        envelope = drafts.prepare(cert,bodies[sid],anchor_ids[0],anchors,edges,registry,qa,
                                  pack['geometry']['key'] if pack['geometry'] else None)
        pending.append(dict(draft=envelope,model_observation=match,
                            source_review=dict(decision=None,reviewer=None,observations=None)))
    return dict(status='non-publishable review queue',drafts=pending,direct_source_review_queue=missing)


def evaluate(reference, prediction):
    """References must independently bind inventory IDs to source regions first.

    This scorer deliberately refuses to estimate heading recall from certificates
    alone. A complete page census is required for recall, including unmatched starts.
    """
    if (not reference.get('reviewer') or not reference.get('source_image_sha256')
        or reference.get('review_decision') != 'source-reviewed reference'):
        raise ValueError('source-bound reference review required')
    if prediction.get('source_image_sha256') != reference['source_image_sha256']:
        raise ValueError('evaluation image binding differs')
    expected = reference['items']
    found = prediction['items']
    for name,rows in [('reference',expected),('prediction',found)]:
        ids=[r.get('item_id') for r in rows]
        if None in ids or len(ids)!=len(set(ids)):
            raise ValueError(name+' has missing or duplicate item IDs')
        for row in rows:
            box=row.get('bbox',[])
            if (len(box)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in box)
                    or box[0]>=box[2] or box[1]>=box[3]):
                raise ValueError(name+' has invalid source region')
    # Pair source regions by overlap, one-to-one, independent of model item IDs.
    def overlap(x,y):
        l,t,r,b=x; L,T,R,B=y
        inter=max(0,min(r,R)-max(l,L))*max(0,min(b,B)-max(t,T))
        return inter/((r-l)*(b-t)+(R-L)*(B-T)-inter)
    pairs = sorted(((overlap(x['bbox'],y['bbox']),i,j) for i,x in enumerate(expected)
                    for j,y in enumerate(found)),reverse=True)
    used_e,used_p=set(),set(); correct=wrong=homonym=abstain=located=correct_abstain=0
    for score,i,j in pairs:
        if score<0.3 or i in used_e or j in used_p:
            continue
        used_e.add(i);used_p.add(j)
        x,y=expected[i],found[j]
        if x['classification']==y['classification']=='article':
            located+=1
        if y.get('source_id') is None:
            abstain+=1
            correct_abstain+=int(x.get('source_id') is None)
        elif (x.get('source_id')==y['source_id'] and x['classification']==y['classification']=='article'
              and x['printed_homonym']==y['printed_homonym']):
            correct+=1
        else:
            wrong+=1
        if x['printed_homonym'] != y['printed_homonym']:
            homonym+=1
    false_positive=wrong+sum(y.get('source_id') is not None for j,y in enumerate(found) if j not in used_p)
    starts=sum(x['classification']=='article' for x in expected)
    linkable=sum(x['classification']=='article' and x.get('source_id') is not None for x in expected)
    def interval(success,total):
        # Wilson 95% interval: a small error-free sample does not prove perfection.
        if not total:return None
        z=1.95996398454;p=success/total;d=1+z*z/total
        c=(p+z*z/(2*total))/d
        h=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
        return [max(0,c-h),min(1,c+h)]
    return dict(reference_reviewer=reference['reviewer'],reference_starts=starts,
        heading_recall=located/starts if reference.get('complete_census') and starts else None,
        link_precision=correct/(correct+false_positive) if correct+false_positive else None,
        link_precision_95=interval(correct,correct+false_positive),
        link_recall=correct/linkable if reference.get('complete_census') and linkable else None,
        link_recall_95=interval(correct,linkable) if reference.get('complete_census') else None,
        correct_links=correct,false_positive_links=false_positive,homonym_errors=homonym,
        abstentions=abstain,correct_abstentions=correct_abstain,missed_regions=len(expected)-len(used_e),unpaired_observations=len(found)-len(used_p))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['plan','prepare','run','review','evaluate','report'])
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--pages',type=Path,help='frozen page manifest or list of page locators')
    p.add_argument('--bodies',type=Path)
    p.add_argument('--model',choices=list(RATES),default='gpt-6-luna')
    p.add_argument('--stage',choices=list(SCHEMAS),default='inventory')
    p.add_argument('--detail',choices=['low','high','original','auto'],default='original')
    p.add_argument('--dpi',type=int,default=240)
    p.add_argument('--max-output-tokens',type=int,default=12000)
    p.add_argument('--approval',type=Path,help='local record: approved USD cap, rights basis and approver')
    p.add_argument('--cap-usd',type=float,default=0)
    p.add_argument('--concurrency',type=int,choices=range(1,5),default=1)
    p.add_argument('--interval',type=float,default=1)
    p.add_argument('--fixture',type=Path)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--reference',type=Path)
    p.add_argument('--prediction',type=Path)
    p.add_argument('--page-pack',type=Path,help='Evaluate the bound inventory and match observations beside this prepared pack')
    p.add_argument('--article-crops',action='store_true',help='Supply provisional article regions to matching instead of the full page')
    args=p.parse_args()
    if args.command=='review':
        args.stage='match'
    if args.interval < 0 or not 1 <= args.max_output_tokens <= 128000:
        raise ValueError('invalid request limits')
    work=private(args.work)
    if args.command=='evaluate':
        if args.page_pack:
            pack=load(args.page_pack);directory=args.page_pack.parent
            inventory=checked_observation(directory/('inventory-'+args.model+'.json'),'inventory',pack,args.model)
            pack['inventory']=inventory['result']
            resources=authoritative(args.bodies)
            pack['candidates']=retrieve(pack['inventory'],pack,resources[1])
            if args.article_crops:prepare_match_crops(pack,directory)
            matching=checked_observation(directory/('match-'+args.model+'.json'),'match',pack,args.model)
            prediction=combined_prediction(pack,inventory['result'],matching['result'])
            write(directory/('prediction-'+args.model+'.json'),prediction)
        else:
            prediction=load(args.prediction)
        print(json.dumps(evaluate(load(args.reference),prediction)))
        return
    if args.command=='report':
        state=load(work/'spending.json') if (work/'spending.json').exists() else None
        print(json.dumps(dict(spending=state,observations=len(list(work.glob('*/cache/*.json'))),
            live_paid_responses=sum('actual' in r and r.get('usage') is not None for r in (state or {}).get('requests',{}).values()),publication_authority=False),indent=2))
        return
    manifest=load(args.pages) if args.pages else {}
    pages=manifest if isinstance(manifest,list) else manifest.get('pages',[])
    if args.command=='plan':
        print(json.dumps(dict(pages=len(pages),model=args.model,rates=RATES[args.model],pricing=PRICING_CHECKED,
            pricing_url=PRICING_URL,maximum_requests=len(pages)*2,
            note='Prepare first for conservative per-request cost bounds; no live authority granted.'),indent=2))
        return
    resources=authoritative(args.bodies) if args.command in ('prepare','review') or args.stage=='match' else None
    if args.command=='prepare':
        for spec in pages:
            key=spec['family']+'-'+str(spec['physical_page'])+('-'+spec['page_key'] if spec.get('page_key') else '')
            prepare_page(spec,resources,work/key,args.dpi)
        return
    spending=client=None
    if args.command=='run' and not args.dry_run and not args.fixture:
        approval=load(args.approval) if args.approval else {}
        if not (0<args.cap_usd<=approval.get('approved_usd',0) and approval.get('approver') and
                approval.get('rights_basis') and approval.get('transmission_authorized') is True):
            raise ValueError('explicit spending approval and source-transmission authority required')
        if not os.environ.get('OPENAI_API_KEY'):
            raise ValueError('OPENAI_API_KEY is not set')
        from openai import OpenAI
        client=OpenAI(max_retries=0,timeout=120)
        spending=Spending(work,args.cap_usd,a.object_digest(approval))
    def process(path):
        pack=load(path)
        directory=path.parent
        if args.stage=='match':
            inventory=checked_observation(directory/('inventory-'+args.model+'.json'),'inventory',pack,args.model)
            pack['inventory']=inventory['result']
            pack['candidates']=retrieve(pack['inventory'],pack,resources[1])
            if args.article_crops:prepare_match_crops(pack,directory)
        spec=request_spec(args.stage,pack,args.model,args.detail,args.max_output_tokens)
        if args.command=='review':
            result=checked_observation(directory/('match-'+args.model+'.json'),'match',pack,args.model)['result']
            write(directory/('review-'+args.model+'.json'),review_drafts(pack,result,resources))
        elif args.dry_run:
            write(directory/(args.stage+'-request-plan.json'),dict(request_sha256=a.object_digest(spec),
                model=args.model,image_sha256=spec['image_sha256'],publication_authority=False))
        else:
            # Cache namespaces distinguish offline fixtures from live observations.
            cache=directory/('fixtures' if args.fixture else 'cache')
            output=execute(spec,pack,cache,spending,client,load(args.fixture) if args.fixture else None,args.interval)
            write(directory/(args.stage+'-'+args.model+'.json'),output)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(process,sorted(work.glob('*/pack.json'))))


if __name__=='__main__':
    main()
