#!/usr/bin/env python3
"""Private one-request-per-scan experiment. No generation or publication API.

Freeze/render sources before inspecting retrieval; prepare payloads; count only.
Nothing here grants certification authority or mutates the campaign/ledger.
"""
import argparse
import base64
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

from badw_model_worker import cost, obj, private, write

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {'wts_1_34': 'WtS 1-34', 'wts_35_51': 'WtS 35-51',
            'wts_8_b': 'WtS 8-b', 'wts_9_m': 'WtS 9-m'}
EXCLUDED = {'wts_1_34': [56,87,88,91,95,97,114,133,642],
            'wts_35_51': [684,690,696,723,859,1007],
            'wts_8_b': [22,34,39,435,436,437,438,439,440],
            'wts_9_m': [25,30,50,188]}
SEED = 'WtSOCR-single-scan-trial-v1-20261113'
PROMPT = '''Read the SOURCE IMAGE, not OCR as authority. Census EVERY independent dictionary article START on this physical scan, in reading order. A continuation from another page is not a start; a cited word or cross-reference target inside an article is not a start. Include brief reference articles and damaged/unnumbered headings. Report blank printed sides and continuation-only regions separately. A genuine single page may have two columns: do not call its columns left/right printed pages. Choose only supplied HTML IDs. Do not force a match: use ambiguous or no_supplied_match explicitly. Distinguish numbered homonyms using the printed numeral AND lexical/citation evidence. Editorial splits do not by themselves establish printed homonyms. For each start transcribe the heading, numeral (empty if none visible), and short distinguishing EXACT source quotation or exact reference target; explain how it distinguishes the chosen HTML entry. Report printed side single/left/right/unknown and a heading box in full image pixels (box accuracy is scored separately). Read printed folios if legible; leave blank otherwise. OCR and candidate passages are fallible retrieval aids. If the correct ID is absent, say so, never substitute the target article or a nearby heading. Do not claim independent certification. Return only the strict JSON result.'''


def load(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def binding(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def database(path):
    return sqlite3.connect(f'file:{Path(path).resolve()}/index.sqlite?mode=ro', uri=True)


def freeze(args):
    run = private(args.output)
    if (run/'selection.json').exists():
        raise ValueError('selection already frozen; reuse it')
    db = database(args.reconstruction)
    scans = []
    # Uses only source layout and OCR coverage, not proposed HTML identities.
    for family in FAMILIES:
        pool = []
        for page, raw in db.execute('select page,features from pages where family=?', (family,)):
            if page <= 10 or page in EXCLUDED[family]:
                continue
            g = json.loads(raw)
            count, located = db.execute(
                "select count(*),sum(json_extract(body,'$.coordinate.box') is not null) from lines where family=? and page=?",
                (family, page)).fetchone()
            if count < 20 or g['rotation']:
                continue
            pool.append(dict(family=family, physical_page=page, landscape=g['landscape'],
                             coordinate_coverage=(located or 0)/count))
        chosen = set()
        for stratum in ('landscape_if_available', 'portrait', 'low_ocr_coordinate_coverage'):
            eligible = [p for p in pool if p['physical_page'] not in chosen]
            if stratum == 'landscape_if_available' and any(p['landscape'] for p in eligible):
                eligible = [p for p in eligible if p['landscape']]
            elif stratum == 'portrait':
                eligible = [p for p in eligible if not p['landscape']] or eligible
            elif stratum == 'low_ocr_coordinate_coverage':
                eligible = sorted(eligible, key=lambda p:p['coordinate_coverage'])[:max(1,len(eligible)//4)]
            pick = min(eligible, key=lambda p:binding([SEED, stratum, family, p['physical_page']]))
            chosen.add(pick['physical_page'])
            scans.append(dict(pick, stratum=stratum))
    write(run/'selection.json', dict(seed=SEED, scans=scans, excluded=EXCLUDED,
          reconstruction_sha256=sha(Path(args.reconstruction)/'manifest.json'),
          policy='source-layout/OCR-only selection; no predictions used; all starts must be audited'))
    render(run, scans)
    write(run/'truth-template.json', dict(selection_sha256=sha(run/'selection.json'),
        scans=[dict(family=s['family'],physical_page=s['physical_page'], census_complete=False,
                    source_review_seconds=None, observations=[]) for s in scans]))
    print(json.dumps(scans, indent=2))


def render(run, scans):
    import pymupdf as fitz
    with (ROOT/'data/source_pdfs.tsv').open() as f:
        registry = {r['label']:r for r in csv.DictReader(f,delimiter='\t')}
    verified = set()
    for s in scans:
        f,p = s['family'],s['physical_page']
        row = registry[FAMILIES[f].replace(' ', '_', 1)]
        pdf = ROOT/row['filename']
        if f not in verified:
            if sha(pdf) != row['sha256']:
                raise ValueError('source checksum mismatch')
            verified.add(f)
        d = run/f'{f}-{p}'; d.mkdir(exist_ok=True)
        with fitz.open(pdf) as doc:
            page = doc[p-1]
            pix = page.get_pixmap(matrix=fitz.Matrix(240/72,240/72), alpha=False)
            pix.save(d/'source.png')
            # Full physical image avoids unreviewed automatic gutter cropping.
            write(d/'image.json', dict(source_sha256=row['sha256'], physical_page=p,
                pixels=[pix.width,pix.height], dpi=240, sha256=sha(d/'source.png'),
                mediabox=list(page.mediabox), rotation=page.rotation,
                pdf_to_mupdf=list(page.transformation_matrix),
                image_origin=[pix.x,pix.y], points_per_pixel=72/240,
                geometry_status='full original scan; model must distinguish printed sides'))


def ocr_readings(family, page, db):
    name = FAMILIES[family]
    paths = [ROOT/'work/full_twopass'/f'{name}_psm3_deu_bod.txt',
             ROOT/'work/full_twopass'/f'{name}_psm4_deu_bod_lat.txt']
    result = []
    for label,path in zip(('tesseract_psm3','tesseract_psm4'), paths):
        text = path.read_text().split('\f')[page-1]
        result.append(dict(reading=label, text=text, file_sha256=sha(path)))
    vision = ROOT/'pdfs'/f'{name}.vision.txt'
    pages = re.split(r'\n*=== page (\d+) ===\n*', vision.read_text())
    vp = {int(pages[i]):pages[i+1] for i in range(1,len(pages),2)}
    result.append(dict(reading='google_vision_raw', text=vp[page],file_sha256=sha(vision)))
    layout = json.loads(db.execute('select body from layouts where family=? and page=?',(family,page)).fetchone()[0])
    result.append(dict(reading='embedded_pdf_ocr', text='\n'.join(r['text'] for r in layout),
                       layout_sha256=binding(layout)))
    return result


def terms(s):
    return re.findall(r"[\w’']{3,}",s.casefold())


def snippet(text, words, limit=600):
    # Exact substring, not a summary or recomposed quote; offsets are reproducible.
    hits = [(m.start(),m.end()) for m in re.finditer(r"[\w’']{3,}",text)
            if m.group().casefold() in words]
    if len(text) <= limit:
        start,end = 0,len(text)
    elif hits:
        starts = [max(0,x-80) for x,y in hits]
        start = max(starts,key=lambda x:sum(x<=a<x+limit for a,b in hits))
        end = min(len(text),start+limit)
    else:
        start,end = 0,min(limit,len(text))
    return dict(start=start,end=end,text=text[start:end],text_sha256=binding(text))


def schema():
    string = {'type':'string'}
    item = obj(dict(start_id=string, heading=string, printed_numeral=string,
        source_id=string, side={'type':'string','enum':['single','left','right','unknown']},
        outcome={'type':'string','enum':['matched','ambiguous','no_supplied_match']},
        evidence=string, distinction=string, printed_folio=string,
        heading_box={'type':'array','items':{'type':'number'},'minItems':4,'maxItems':4}))
    return obj(dict(starts={'type':'array','items':item},
                    non_start_regions={'type':'array','items':string}, layout=string))


def stream_bodies(path):
    """Iterate a large JSON object without retaining its display-block corpus."""
    decoder=json.JSONDecoder()
    with path.open() as f:
        buffer=''; offset=0; eof=False
        while True:
            if not eof and len(buffer)-offset<1048576:
                buffer=buffer[offset:]+f.read(1048576); offset=0
                eof=len(buffer)==0 or f.tell()==path.stat().st_size
            while offset<len(buffer) and buffer[offset] in ' \n\r\t{,': offset+=1
            if offset<len(buffer) and buffer[offset]=='}': return
            try:
                key,end=decoder.raw_decode(buffer,offset)
                colon=end
                while buffer[colon].isspace(): colon+=1
                if buffer[colon]!=':': raise ValueError('invalid body object')
                start=colon+1
                while buffer[start].isspace(): start+=1
                value,end=decoder.raw_decode(buffer,start)
            except (json.JSONDecodeError,IndexError):
                if eof: raise ValueError('truncated body corpus')
                buffer=buffer[offset:]+f.read(1048576);offset=0
                eof=f.tell()==path.stat().st_size
                continue
            offset=end
            yield key,value


def reference_components(path,cache):
    source_hash=sha(path)
    if cache.exists():
        saved=load(cache)
        if saved.get('bodies_sha256')==source_hash: return saved['references']
    refs={}
    for sid,body in stream_bodies(path):
        rows=[dict(id=c['id'],type=c['type'],source_form=c['source_form'],
                   sha256=binding(c['source_form'])) for c in body['components']
              if c['type']=='cross_reference']
        if rows: refs[sid]=rows
    write(cache,dict(bodies_sha256=source_hash,references=refs))
    return refs


def prepare(args):
    run = private(args.output); selection=load(run/'selection.json')
    truth=load(run/'truth.json')
    if truth.get('selection_sha256') != sha(run/'selection.json') or not all(
            s.get('census_complete') and s.get('identity_review_complete') for s in truth['scans']):
        raise ValueError('complete source-first census required before retrieval')
    frozen=run/'truth-binding.json'
    truth_binding=dict(truth_sha256=sha(run/'truth.json'),selection_sha256=sha(run/'selection.json'))
    if frozen.exists() and load(frozen)!=truth_binding:
        raise ValueError('source-first truth changed after retrieval')
    write(frozen,truth_binding)
    db = database(args.reconstruction)
    # FTS uses acquired editorial text only; it grants no source authority.
    refs=reference_components(Path(args.bodies),run/'reference-components.json')
    search = sqlite3.connect(':memory:')
    search.execute('create virtual table entries using fts5(sid UNINDEXED,body)')
    witnesses = {sid:json.loads(b) for sid,b in db.execute('select sid,body from witnesses')}
    search.executemany('insert into entries values (?,?)',
        [(sid,w['headword']['loc']+' '+w['headword']['tibetan']+' '+w['definition']+' '+' '.join(w['citations'])+' '+' '.join(c['source_form'] for c in refs.get(sid,[]))) for sid,w in witnesses.items()])
    for s in selection['scans']:
        f,p=s['family'],s['physical_page']; d=run/f'{f}-{p}'
        readings=ocr_readings(f,p,db)
        votes=Counter(); reasons={}
        # Existing alignment: keep competitors per heading, not only accepted/top1 rows.
        for aid, in db.execute('select aid from starts where family=? and page=?',(f,p)):
            for sid,score in db.execute('select sid,score from proposals where aid=? order by score desc,sid limit 3',(aid,)):
                votes[sid]+=5; reasons.setdefault(sid,set()).add('existing_heading_alignment')
        # Damaged-heading fallback: local full-text queries from each reading's
        # line windows. BM25 chooses discriminating co-occurrences, not gloss-only equality.
        for reading in readings:
            lines=reading['text'].splitlines()
            for i,line in enumerate(lines):
                words=list(dict.fromkeys(terms(' '.join(lines[i:i+2]))))
                words=[w for w in words if len(w)>=4 and not w.isdigit()][:18]
                if len(words)<2: continue
                query=' OR '.join('"'+w.replace('"','""')+'"' for w in words)
                for sid, in search.execute('select sid from entries where entries match ? order by rank limit 2',(query,)):
                    votes[sid]+=1; reasons.setdefault(sid,set()).add('local_definition_citation_search')
        selected=[sid for sid,n in sorted(votes.items(),key=lambda x:(-x[1],x[0]))[:args.max_candidates]]
        # Preserve homonym rivals even when their evidence is less frequent.
        heads={witnesses[s]['headword']['loc'] for s in selected}
        selected+=sorted(sid for sid,w in witnesses.items() if w['headword']['loc'] in heads and sid not in selected)
        words=set(terms(' '.join(r['text'] for r in readings)))
        candidates=[]
        for sid in selected:
            w=witnesses[sid]
            candidates.append(dict(source_id=sid,html_sha256=w['html_sha256'],headword=w['headword'],
                homonym=w['homonym'],reference_components=refs.get(sid,[]),definition=snippet(w['definition'],words),
                citations=[snippet(c,words,240) for c in w['citations'][:3]],
                retrieval_reasons=sorted(reasons.get(sid,{'homonym_rival'}))))
        # Relevant OCR disagreements: retain local line windows containing candidate
        # headword/rare lexical hits, with separate readings rather than consensus.
        compact=[]
        keys=set()
        for c in candidates:
            keys.update(terms(c['headword']['loc']));keys.update(terms(c['headword']['tibetan']))
            keys.update(w for w in terms(c['definition']['text']) if len(w)>=7)
        for r in readings:
            lines=r['text'].splitlines(); indices=set()
            for i,line in enumerate(lines):
                if keys.intersection(terms(line)):
                    indices.update(range(max(0,i-1), min(len(lines),i+2)))
            compact.append(dict(reading=r['reading'], text='\n'.join(lines[i] for i in sorted(indices))))
        image=load(d/'image.json')
        common=dict(family=f, physical_page=p, image=image, candidates=candidates)
        for variant,ocr in [('compact',compact),('full_four_ocr',readings)]:
            evidence=dict(common,ocr=ocr)
            spec=dict(model='gpt-6-luna',max_output_tokens=args.max_output_tokens,
                input=[dict(role='user',content=[dict(type='input_text',text=PROMPT+'\n'+json.dumps(evidence,ensure_ascii=False,separators=(',',':'))),
                    dict(type='input_image',image_url='LOCAL:source.png',detail='original')])],
                text={'format':dict(type='json_schema',name='scan_verification',strict=True,schema=schema())})
            write(d/f'{variant}.json',spec)
        write(d/'retrieval.json',dict(candidate_count=len(candidates),ranked_pool=len(votes),
            supplied_ids=selected,readings=[{k:v for k,v in r.items() if k!='text'} for r in readings],
            selection_sha256=sha(run/'selection.json'), prediction_authority=False))
        print(f'{f}/{p}: {len(candidates)} supplied / {len(votes)} retrieved')


def materialize(path):
    spec=load(path); image=path.parent/'source.png'
    evidence=json.loads(spec['input'][0]['content'][0]['text'].split('\n',1)[1])
    if sha(image)!=evidence['image']['sha256']:
        raise ValueError('image changed')
    spec['input'][0]['content'][1]['image_url']='data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode()
    return spec


def count_request(spec, cached, client):
    key=binding(spec)
    if cached and cached.get('request_sha256')==key:
        n=cached.get('input_tokens')
        if type(n) is int and 0<n<=922000: return cached
    # No reservation and NO generation; exact same input/schema as proposed request.
    result=client.responses.input_tokens.count(model=spec['model'],input=spec['input'],text=spec['text'])
    n=getattr(result,'input_tokens',None)
    if type(n) is not int or not 0<n<=922000:
        raise ValueError('invalid exact request input-token count')
    return dict(request_sha256=key,input_tokens=n)


def count(args):
    import os
    from openai import OpenAI
    client=OpenAI(api_key=os.environ.get('OPENAI_API_KEY') or (ROOT/'work/openai-api-key').read_text().strip(),max_retries=0,timeout=120)
    run=private(args.output); rows=[]
    for path in sorted(run.glob('*/*.json')):
        if path.stem not in ('compact','full_four_ocr'):continue
        spec=materialize(path); cp=path.with_name(path.stem+'-tokens.json')
        result=count_request(spec,load(cp) if cp.exists() else None,client);write(cp,result)
        n=result['input_tokens']; margin=math.ceil(n*1.05)+256
        # Conservative standard bound includes potential cache-write uplift.
        standard=cost(spec['model'],margin,spec['max_output_tokens'],cache_write_tokens=margin)
        rows.append(dict(page=path.parent.name,variant=path.stem,**result,
                         output_ceiling=spec['max_output_tokens'],standard_cap_usd=standard,
                         batch_cap_usd=standard/2))
        print(path.parent.name,path.stem,n,flush=True)
    write(run/'pricing.json',dict(requests=rows,generation_requests=0,
        standard_cap_usd=sum(r['standard_cap_usd'] for r in rows if r['variant']=='compact'),
        batch_cap_usd=sum(r['batch_cap_usd'] for r in rows if r['variant']=='compact'),
        batch_account_eligibility='not established; model documentation supports Batch',
        rates_verified='2026-11-13 https://developers.openai.com/api/docs/models/gpt-6-luna'))


def validate_result(result,spec,check_boxes=True):
    if set(result) != {'starts','non_start_regions','layout'}:
        raise ValueError('invalid result fields')
    if not isinstance(result['layout'],str) or not isinstance(result['non_start_regions'],list) or any(
            not isinstance(r,str) for r in result['non_start_regions']):
        raise ValueError('invalid layout observations')
    if not isinstance(result['starts'],list):
        raise ValueError('invalid article starts')
    evidence=json.loads(spec['input'][0]['content'][0]['text'].split('\n',1)[1])
    supplied={c['source_id'] for c in evidence['candidates']}; seen=set()
    width,height=evidence['image']['pixels']
    for r in result['starts']:
        if set(r)!=set(schema()['properties']['starts']['items']['properties']):
            raise ValueError('invalid start fields')
        if any(not isinstance(v,str) for k,v in r.items() if k!='heading_box'):
            raise ValueError('invalid start text')
        if not r['start_id']: raise ValueError('missing start ID')
        if r['start_id'] in seen:raise ValueError('duplicate start ID')
        seen.add(r['start_id'])
        if r['outcome'] not in ('matched','ambiguous','no_supplied_match'):raise ValueError('invalid outcome')
        if r['side'] not in ('single','left','right','unknown'):raise ValueError('invalid side')
        if r['outcome']=='matched':
            if r['source_id'] not in supplied:raise ValueError('unsupplied HTML identity')
            if not r['heading'].strip() or not r['evidence'].strip() or not r['distinction'].strip():
                raise ValueError('missing source evidence')
        elif r['source_id']:raise ValueError('abstention cannot assign an identity')
        box=r['heading_box']
        if not check_boxes: continue  # Geometry quality is audited separately from identity/side.
        if len(box)!=4 or any(type(x) not in (int,float) or not math.isfinite(x) for x in box):raise ValueError('invalid box')
        if not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height:raise ValueError('box outside source image')
    return result


def score_scan(truth, result, supplied, audit):
    """Audit maps output start IDs to source-first truth IDs, or null for false starts.

    Mapping is source reviewed, never inferred from a matching prediction. Boxes
    are scored separately and cannot turn a wrong identity into a correct one.
    This evaluates the trial; it cannot create certificates.
    """
    expected={r['truth_id']:r for r in truth['starts']}
    if set(audit)!={r['start_id'] for r in result['starts']}:
        raise ValueError('source audit must dispose every predicted start')
    mapped=[t for t in audit.values() if t is not None]
    if len(mapped)!=len(set(mapped)) or not set(mapped)<=set(expected):
        raise ValueError('invalid or repeated source audit assignment')
    metrics=Counter(eligible=len(expected),linkable=sum(bool(r['html_ids']) for r in expected.values()),
        supplied=sum(bool(set(r['html_ids'])&set(supplied)) for r in expected.values()),
        omitted_correct_id=sum(bool(r['html_ids']) and not bool(set(r['html_ids'])&set(supplied))
                               for r in expected.values()))
    seen=set()
    for r in result['starts']:
        tid=audit[r['start_id']]
        if tid is None:
            metrics['false_starts']+=1
            if r['outcome']=='matched': metrics['wrong_assignments']+=1
            continue
        seen.add(tid); t=expected[tid]
        side_ok=r['side']==t['side'] and r['side']!='unknown'
        if not side_ok: metrics['wrong_side']+=1
        if r['side']=='unknown': metrics['unresolved_side']+=1
        if r['outcome']!='matched':
            metrics['abstentions']+=1
            if set(t['html_ids'])&set(supplied): metrics['missed_supplied']+=1
            if not t['html_ids'] and r['outcome']=='no_supplied_match' and side_ok:
                metrics['correct_no_html_dispositions']+=1
        elif r['source_id'] in t['html_ids'] and side_ok:
            metrics['correct_assignments']+=1
            if set(t['html_ids'])&set(supplied): metrics['correct_supplied_assignments']+=1
        else:
            metrics['wrong_assignments']+=1
            if r['source_id'] not in t['html_ids']: metrics['wrong_identity']+=1
    metrics['missing_starts']=len(set(expected)-seen)
    metrics['complete_scan']=int(not metrics['missing_starts'] and not metrics['false_starts']
        and not metrics['wrong_assignments'] and not metrics['wrong_side']
        and metrics['correct_assignments']==metrics['linkable'])
    metrics['complete_scan']=int(metrics['complete_scan'] and
        metrics['correct_no_html_dispositions']==metrics['eligible']-metrics['linkable'])
    return dict(metrics)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['freeze','prepare','count'])
    p.add_argument('--output',default='work/single-scan-trial-20261113')
    p.add_argument('--reconstruction',default='work/html-print-reconstruction-certified')
    p.add_argument('--bodies',default='work/html-print-inputs/bodies.json')
    p.add_argument('--max-candidates',type=int,default=48)
    p.add_argument('--max-output-tokens',type=int,default=6000)
    args=p.parse_args(); globals()[args.command](args)


if __name__=='__main__':main()
