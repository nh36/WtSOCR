#!/usr/bin/env python3
"""Run full-corpus, offline HTML/print proposals; never alter reviewed acceptances.

Example: python3 scripts/run_badw_html_print_alignment.py --all-volumes --resume
  --output work/html-print-full-alignment
The SQLite cache is private. Serve only the report subdirectory, never this cache
or registered source directories. Machine-supported means provisional, not verified.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from badw_html_print_alignment import FAMILIES, digest, object_digest
from badw_html_print_engine import (VERSION, atomic_json, connection, completed, checkpoint,
    index_witnesses, index_family, index_history, discover, match_page, tokens, write_results, section_sequences)
import collections

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--all-volumes',action='store_true',required=True)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--disable-reconstructed-intervals',action='store_true',help='ablation: retain the local 48-line segmentation with identical coordinate inputs')
    p.add_argument('--disable-sequence-reranking',action='store_true',help='retain local scores; compute sequence diagnostics only')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inputs',type=Path,default=ROOT/'work/html-print-inputs',
                   help='portable bundle from prepare_badw_alignment_inputs.py')
    p.add_argument('--coordinate-inputs',type=Path,help='render-bound hOCR bundle from prepare_badw_coordinate_inputs.py')
    p.add_argument('--stop-after',help='Testing/recovery: exit after named atomic stage')
    args=p.parse_args(argv)
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'work').resolve()):
        p.error('outputs must stay in ignored work/, separate from reader and registered scans')
    output.mkdir(parents=True,exist_ok=True)
    bundle = json.loads((args.inputs/'manifest.json').read_text())
    if bundle['schema'] != 1 or bundle['counts'] != dict(html_witnesses=18038, catalogue_ranks=29878):
        raise ValueError('incomplete or unsupported input bundle')
    expected_files = {'bodies.json', 'catalogue.json'} | ({'anchors.jsonl', 'edges.jsonl'} if bundle['historical_corroboration'] else set())
    if set(bundle['files']) != expected_files:
        raise ValueError('inconsistent bundle file manifest')
    for name, checksum in bundle['files'].items():
        if digest(args.inputs/name) != checksum:
            raise ValueError('prepared input checksum changed: '+name)
    args.bodies, args.catalogue = args.inputs/'bodies.json', args.inputs/'catalogue.json'
    history = {k:args.inputs/(k+'.jsonl') for k in ('anchors','edges')} if bundle['historical_corroboration'] else {}
    registry={r['label']:r for r in csv.DictReader((ROOT/'data/source_pdfs.tsv').open(),delimiter='\t')}
    paths={**history,'prepared_manifest':args.inputs/'manifest.json','bodies':args.bodies,'catalogue':args.catalogue,
        'registry':ROOT/'data/source_pdfs.tsv','certificate':ROOT/'data/badw_html_print_alignment.json',
        'expanded':ROOT/'data/badw_html_print_alignment.generated.json','baseline':ROOT/'data/badw_html_print_pages.json',
        'preparer':Path(__file__).with_name('prepare_badw_alignment_inputs.py'),
        'reconstruction':Path(__file__).with_name('badw_print_reconstruction.py'),
        'coordinates':Path(__file__).with_name('badw_qa_pdf_coordinates.py'),
        'structure':Path(__file__).with_name('badw_print_structure.py'),
        'engine':Path(__file__).with_name('badw_html_print_engine.py'),'runner':Path(__file__),
        'certificate_compiler':ROOT/'scripts/badw_html_print_alignment.py',
        'facsimiles':ROOT/'scripts/badw_html_print_facsimiles.py',
        'matcher':ROOT/'scripts/badw_source_matcher.py','crosswalk':ROOT/'scripts/badw_print_crosswalk.py'}
    if args.coordinate_inputs:
        from prepare_badw_coordinate_inputs import validate_bundle
        validate_bundle(args.coordinate_inputs, registry)
        paths['coordinate_manifest'] = args.coordinate_inputs/'manifest.json'
        paths['coordinate_preparer'] = Path(__file__).with_name('prepare_badw_coordinate_inputs.py')
        for family in FAMILIES:
            paths['coordinate:'+family] = args.coordinate_inputs/(family+'.jsonl')
    for family,label in FAMILIES.items():
        paths['qa:'+family]=ROOT/f'release/current/qa/{family}/{family}_line_zones.tsv'
        paths['scan:'+family]=ROOT/registry[label]['filename']
    print('Pinning local input checksums...',flush=True)
    hashes={k:digest(v) for k,v in sorted(paths.items())}
    for family,label in FAMILIES.items():
        if hashes['scan:'+family]!=registry[label]['sha256']:
            raise ValueError('registered scan checksum differs: '+family)
    import pypdf
    poppler=subprocess.run(['pdftotext','-v'],capture_output=True,text=True,check=True).stderr.splitlines()[0]
    configuration=dict(version=VERSION,inputs=hashes,python=platform.python_version(),
        pypdf=pypdf.__version__,sqlite=__import__('sqlite3').sqlite_version,poppler=poppler,
        concurrency=1,reconstructed_intervals=not args.disable_reconstructed_intervals,sequence_reranking=not args.disable_sequence_reranking,definition_safety_cap_lines=48,sequence_section_pages=3,sample_seed='20261025')
    identity=object_digest(configuration)
    pin=output/'inputs.json'
    if pin.exists():
        if json.loads(pin.read_text())!=configuration:
            raise ValueError('input/configuration changed; choose a fresh output directory')
        if not args.resume:
            p.error('existing output requires --resume')
    else:
        atomic_json(pin,configuration)
    db=connection(output/'index.sqlite')
    timings=[]
    started=time.monotonic()
    def stage(name,operation):
        previous=completed(db,name)
        if previous is not None:
            print(name+': cached',flush=True)
            return previous
        begin=time.monotonic()
        print(name+': running',flush=True)
        try:
            result=operation()
            checkpoint(db,name,result)
        except BaseException:
            db.rollback()
            raise
        elapsed=time.monotonic()-begin
        timings.append(dict(stage=name,seconds=round(elapsed,3)))
        print(name+': '+json.dumps(result)+f' ({elapsed:.2f}s)',flush=True)
        atomic_json(output/'timing-latest.json',dict(stages=timings,seconds=round(time.monotonic()-started,3),
            max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,platform=sys.platform))
        if args.stop_after==name:
            raise SystemExit(0)
        return result
    stage('witnesses',lambda:index_witnesses(db,args.bodies,args.catalogue))
    stage('history',lambda:index_history(db,ROOT,history))
    for family in FAMILIES:
        stage('pages:'+family,lambda f=family:index_family(db,ROOT,f,registry,output,args.coordinate_inputs))
    witnesses={sid:json.loads(body) for sid,body in db.execute('SELECT * FROM witnesses')}
    stage('starts',lambda:discover(db,witnesses))
    from badw_print_reconstruction import reconstruct, sequence_rerank
    from badw_html_print_facsimiles import reviewed_records, REVIEWS
    from badw_html_print_engine import FAMILIES_INV
    reviewed,_=reviewed_records(REVIEWS)
    reviewed_pages=collections.defaultdict(list)
    for key,row in reviewed['pages'].items():
        reviewed_pages[FAMILIES_INV[row['source']],row['physical_page']].append(dict(key=key,**row))
    stage('reconstruction',lambda:reconstruct(db,reviewed_pages,witnesses))
    frequencies=collections.Counter()
    for w in witnesses.values():
        frequencies.update(tokens(w['definition']))
    for family in FAMILIES:
        def match_family(f=family):
            n=0
            for (page,) in db.execute('SELECT page FROM pages WHERE family=? ORDER BY page',(f,)).fetchall():
                n+=match_page(db,f,page,witnesses,frequencies,use_reconstructed_intervals=not args.disable_reconstructed_intervals)
                if page%100==0:
                    print(f'  {f}: physical page {page}',flush=True)
            return dict(proposals=n)
        stage('match:'+family,match_family)
    stage('section-sequences',lambda:section_sequences(db,witnesses))
    stage('sequence-rerank',lambda:sequence_rerank(db,witnesses,enabled=not args.disable_sequence_reranking))
    summary=write_results(db,output,ROOT,witnesses,identity)
    atomic_json(output/'timing-latest.json',dict(stages=timings,seconds=round(time.monotonic()-started,3),
        max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,platform=sys.platform))
    print(json.dumps(summary,indent=2),flush=True)
    db.close()


if __name__=='__main__':
    main()
