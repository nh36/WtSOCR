#!/usr/bin/env python3
"""Private page-grouped exception evidence with explicitly requested PNG rendering.

Only report/ is suitable for local HTTP serving. Source PDFs are never copied,
linked, or embedded. Image hashes bind cached renders to registered source hashes.
Adjudications are separate observations; they cannot authorise reader attachment.
"""
import argparse
import csv
import html
import json
from pathlib import Path
import subprocess
import tempfile
from badw_html_print_alignment import FAMILIES, digest
from badw_html_print_engine import atomic_json
from evaluate_badw_alignment import causes, read_rows

ROOT=Path(__file__).resolve().parents[1]


def validate_decision(decision, row, scan_sha):
    p=row['proposed'][0]
    expected=dict(html_sha256=row['html_sha256'],scan_sha256=scan_sha,
                  anchor=p['anchor'],evidence_sha256=p['evidence_sha256'])
    if decision['binding'] != expected:
        raise ValueError('stale adjudication evidence')
    if decision['decision'] not in ('accept','reject','defer') or not decision.get('observation'):
        raise ValueError('explicit decision and source observation required')
    return dict(decision,attachment_authority=False)


def render(run, family, page, pin, registry):
    images=run/'report/pages'; images.mkdir(exist_ok=True)
    target=images/f'{family}-{page}.png'
    record=target.with_suffix('.json')
    expected=dict(scan_sha256=pin['inputs']['scan:'+family],family=family,physical_page=page,dpi=160)
    if record.exists() and target.exists():
        old=json.loads(record.read_text())
        if all(old.get(k)==v for k,v in expected.items()) and old['image_sha256']==digest(target):
            return
    source=ROOT/registry[FAMILIES[family]]['filename']
    if digest(source) != expected['scan_sha256']:
        raise ValueError('registered source changed')
    with tempfile.TemporaryDirectory(dir=run) as tmp:
        prefix=Path(tmp)/'page'
        subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-r','160',
                        '-png',str(source),str(prefix)],check=True,capture_output=True)
        prefix.with_suffix('.png').replace(target)
    atomic_json(record,dict(expected,image_sha256=digest(target),
        use='private physical-page review only; neither reviewed crop nor publication asset'))


def card(row):
    p=row['proposed'][0]
    esc=lambda x:html.escape(str(x))
    return ('<article id="'+esc(row['source_id'])+'"><h3>'+esc(row['editorial_headword']['loc'])+
        ' — HTML homonym '+esc(row['editorial_homonym'])+'</h3><p>'+esc(p['anchor'])+
        '; coordinates '+esc(p['coordinate'])+'</p><p>Uncertainties: '+esc(', '.join(causes(row)))+
        '</p><h4>Candidate heading (OCR, not a transcription)</h4><pre>'+esc(p['heading_text'])+
        '</pre><h4>Printed evidence within provisional boundaries</h4><pre>'+esc(p['printed_evidence'])+
        '</pre><h4>HTML definition</h4><pre>'+esc(row['editorial_definition'])+
        '</pre><p>Definition overlap: '+esc(p['definition_evidence'])+'</p><details><summary>Competing assignments</summary><pre>'+
        esc('\n'.join(q['anchor']+' '+q['heading_text']+' score='+str(q['score']) for q in row['proposed'][1:]))+
        '</pre></details><details><summary>Reconstructed source structure (machine evidence)</summary><pre>'+
        esc(json.dumps(p.get('reconstruction',{}),ensure_ascii=False,indent=2))+
        '</pre></details><p>Evidence identity: '+esc(p['evidence_sha256'])+'</p></article>')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--page',action='append',default=[],help='render only FAMILY:PHYSICAL_PAGE; repeatable')
    parser.add_argument('--selection',type=Path,help='render fixed evaluation-selection cases, no labels generated')
    parser.add_argument('--decisions',type=Path,help='separate checksum-bound human decision JSON; validate without attachment')
    args=parser.parse_args()
    run=args.run.resolve()
    if not run.is_relative_to(ROOT/'work'):
        parser.error('private review outputs must stay under work/')
    pin=json.loads((run/'inputs.json').read_text())
    registry={r['label']:r for r in csv.DictReader((ROOT/'data/source_pdfs.tsv').open(),delimiter='\t')}
    pages={tuple(x.split(':')) for x in args.page}
    selected=None
    if args.selection:
        selection=json.loads(args.selection.read_text())['cases']
        selected={x['source_id'] for x in selection}
        pages.update((x['family'],x['anchor'].split(':')[1]) for x in selection)
    report=run/'report';report.mkdir(exist_ok=True)
    if report.is_symlink() or any(p.is_symlink() for p in report.rglob('*')):
        raise ValueError('review serving tree must not contain symlinks')
    if args.decisions:
        decisions=json.loads(args.decisions.read_text())
        requested={d['source_id']:d for d in decisions}
        if len(requested)!=len(decisions):
            raise ValueError('duplicate adjudication')
        checked=[]
        for row in read_rows(run/'witnesses.jsonl'):
            if row['source_id'] in requested:
                family=row['proposed'][0]['family']
                checked.append(validate_decision(requested.pop(row['source_id']),row,pin['inputs']['scan:'+family]))
        if requested:
            raise ValueError('adjudicated witness absent from current corpus')
        atomic_json(run/'validated-adjudications.json',checked)
        print('validated decisions',len(checked),'; reader attachment remains disabled',flush=True)
    for family,page in sorted(pages):
        if family not in FAMILIES or not page.isdigit():
            raise ValueError('invalid physical page')
        render(run,family,int(page),pin,registry)
        print('rendered',family,page,flush=True)
    # Group compact IDs first; fetch full records only for one physical page at a
    # time using SQLite, avoiding a corpus-sized in-memory JSON report.
    import sqlite3
    db=sqlite3.connect(run/'review.sqlite')
    db.execute('DROP TABLE IF EXISTS cases')
    db.execute('CREATE TABLE cases (family TEXT,page INTEGER,sid TEXT,body TEXT)')
    for row in read_rows(run/'witnesses.jsonl'):
        if not row['proposed'] or (selected is not None and row['source_id'] not in selected):
            continue
        p=row['proposed'][0]
        db.execute('INSERT INTO cases VALUES (?,?,?,?)',(p['family'],p['physical_page'],row['source_id'],json.dumps(row,ensure_ascii=False)))
    db.commit()
    groups=db.execute('SELECT family,page,count(*) FROM cases GROUP BY family,page ORDER BY count(*) DESC,family,page').fetchall()
    index=['<!doctype html><meta charset="utf-8"><h1>Private page-grouped alignment review</h1>',
           '<p>Provisional evidence only. Review one printed page for multiple witnesses. Images render only on explicit CLI request; no source PDFs are served.</p>']
    styles='<style>body{font:16px system-ui;max-width:1100px;margin:auto;padding:1em;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}article{border-top:2px solid #999}img{max-width:100%}</style>'
    for family,page,n in groups:
        name=f'group-{family}-{page}.html'
        image=f'pages/{family}-{page}.png'
        content=['<!doctype html><meta charset="utf-8">',styles,f'<h1>{family} physical page {page}</h1>','<a href="groups.html">All groups</a>']
        if (report/image).exists():
            content.append(f'<a href="{image}"><img src="{image}" alt="Physical source page, private research"></a>')
        else:
            content.append(f'<p>Image not rendered. Run review_badw_alignment_cases.py --run RUN --page {family}:{page}</p>')
        content.extend(card(json.loads(r[0])) for r in db.execute('SELECT body FROM cases WHERE family=? AND page=? ORDER BY sid',(family,page)))
        target=report/name;tmp=target.with_suffix('.tmp');tmp.write_text('\n'.join(content));tmp.replace(target)
        index.append(f'<p><a href="{name}">{family}:{page}</a> — {n} cases</p>')
    (report/'groups.html').write_text('\n'.join(index))
    db.close()


if __name__=='__main__':
    main()
