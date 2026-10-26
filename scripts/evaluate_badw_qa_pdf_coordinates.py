#!/usr/bin/env python3
"""Evaluate coordinates against separately recorded source-image regions.

These coarse observations test placement, not lexical identity or article extent.
They are purposive development-agent observations, not a scholarly gold standard.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from badw_html_print_alignment import FAMILIES, object_digest


def placement(coordinate, region, width, height):
    if not coordinate:
        return 'unlocated'
    x, y, r, b = coordinate['box']
    cx, cy = (x+r)/2/width, (y+b)/2/height
    return 'within_observed_region' if region[0] <= cx <= region[2] and region[1] <= cy <= region[3] else 'outside_observed_region'


def verify_sequence_assessments(root, assessments, witnesses, coordinates, images):
    """Check observation provenance, without claiming to verify visual judgments."""
    labels = json.loads(assessments.read_text())
    cases = labels['cases']
    wanted = {c['source_id']: c for c in cases}
    if len(wanted) != len(cases):
        raise ValueError('duplicate assessed witness')
    matched = set()
    with witnesses.open() as stream:
        for text in stream:
            witness = json.loads(text)
            case = wanted.get(witness['source_id'])
            if case:
                if case['html_sha256'] != witness['html_sha256']:
                    raise ValueError('changed assessed HTML identity')
                # Labels bind the particular compared predictions, never a later top.
                local = witness['local_ranking'][0]['anchor']
                adjusted = witness['sequence_ranking'][0]['anchor']
                if [(c['label'], c['anchor']) for c in case['candidates']] != [('local', local), ('adjusted', adjusted)]:
                    raise ValueError('changed assessed predictions')
                matched.add(witness['source_id'])
    if matched != set(wanted):
        raise ValueError('missing assessed HTML witness')
    registry = {r['label']: r for r in csv.DictReader((root/'data/source_pdfs.tsv').open(), delimiter='\t')}
    anchors = {}
    for case in cases:
        for candidate in case['candidates']:
            identity = {k: v for k, v in candidate.items() if k != 'label'}
            prior = anchors.setdefault(candidate['anchor'], identity)
            if prior != identity:
                raise ValueError('inconsistent repeated assessed anchor')
    for family in sorted({a.split(':')[0] for a in anchors}):
        with (root/f'release/current/qa/{family}/{family}_line_zones.tsv').open() as stream:
            for row in csv.DictReader(stream, delimiter='\t'):
                anchor = f"{family}:{row['page']}:{row['line']}"
                candidate = anchors.get(anchor)
                if candidate:
                    if (object_digest(row), row['line_text']) != (candidate['qa_row_sha256'], candidate['qa_text']):
                        raise ValueError('changed assessed QA evidence')
                    if registry[FAMILIES[family]]['sha256'] != candidate['source_sha256']:
                        raise ValueError('changed assessed registered scan')
                    page = json.loads((coordinates/'verified'/family/f"{int(row['page']):04d}.json").read_text())
                    record = page['record']
                    if (object_digest(record) != page['record_sha256'] or
                        record['raster_sha256'] != candidate['raster_sha256'] or
                        record['source_sha256'] != candidate['source_sha256'] or
                        record['family'] != family or
                        record['physical_page'] != int(row['page'])):
                        raise ValueError('changed assessed source rendering')
                    candidate['_checked'] = True
    if not all(c.pop('_checked', False) for c in anchors.values()):
        raise ValueError('missing assessed QA anchor')
    for case in cases:
        if case['publication_eligible'] is not False:
            raise ValueError('assessment cannot authorise publication')
        if hashlib.sha256((images/case['comparison_image']).read_bytes()).hexdigest() != case['comparison_image_sha256']:
            raise ValueError('changed assessed comparison image')
    return dict(authority=labels['authority'], count=len(cases),
                assessments=dict(collections.Counter(c['assessment'] for c in cases)),
                homonyms=dict(collections.Counter(c['homonym_assessment'] for c in cases)),
                interpretation='Provenance checked; visual judgments remain development-agent observations, not independent scholarly verification.')


def evaluate(root, database, benchmark, images):
    labels = json.loads(benchmark.read_text())
    registry = {r['label']: r for r in csv.DictReader((root/'data/source_pdfs.tsv').open(), delimiter='\t')}
    db = sqlite3.connect('file:'+str(database.resolve())+'?mode=ro', uri=True)
    observed = {}
    for family in sorted({c['family'] for c in labels['cases']}):
        wanted = {(c['physical_page'],c['qa_line']) for c in labels['cases'] if c['family']==family}
        with (root/f'release/current/qa/{family}/{family}_line_zones.tsv').open() as f:
            for row in csv.DictReader(f, delimiter='\t'):
                key = (int(row['page']),int(row['line']))
                if key in wanted:
                    observed[family,*key] = row
    results = []
    counts = collections.defaultdict(collections.Counter)
    for case in labels['cases']:
        family, page, line = case['family'], case['physical_page'], case['qa_line']
        if case['source_sha256'] != registry[FAMILIES[family]]['sha256']:
            raise ValueError('stale registered source: '+case['id'])
        image = images/case['image_name']
        if hashlib.sha256(image.read_bytes()).hexdigest() != case['image_sha256']:
            raise ValueError('changed inspected rendering: '+case['id'])
        stored = db.execute('SELECT body FROM lines WHERE family=? AND page=? AND line=?', (family,page,line)).fetchone()
        if not stored:
            raise ValueError('missing indexed QA observation: '+case['id'])
        row = json.loads(stored[0])
        source = observed.get((family,page,line))
        if source is None:
            raise ValueError('missing current QA observation: '+case['id'])
        if object_digest(source) != case['qa_row_sha256'] or source['line_text'] != case['qa_text']:
            raise ValueError('changed QA observation: '+case['id'])
        if any(row.get(k)!=v for k,v in source.items()):
            raise ValueError('stale indexed QA observation: '+case['id'])
        geometry = json.loads(db.execute('SELECT features FROM pages WHERE family=? AND page=?',(family,page)).fetchone()[0])
        result = dict(id=case['id'], split=case['split'], family=family,
                      observation=case['observation'])
        for method, key in [('legacy','legacy_coordinate'), ('reconciled','coordinate')]:
            value = placement(row.get(key), case['region'], geometry['width'], geometry['height'])
            result[method] = value
            for group in ['all', case['split'], family]:
                counts[group][method+':'+value] += 1
        results.append(result)
    return dict(authority=labels['authority'], selection=labels['selection'],
                cases=results, counts={k:dict(v) for k,v in sorted(counts.items())},
                benchmark_sha256=hashlib.sha256(benchmark.read_bytes()).hexdigest(),
                interpretation='Centre-in-region placement only. Abstentions are not correct placements; no population precision or full-extent claim.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True)
    p.add_argument('--benchmark',type=Path,default=Path('data/qa_pdf_coordinates/benchmark.json'))
    p.add_argument('--images',type=Path,default=Path('work/qa-coordinate-benchmark'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sequence-witnesses',type=Path,
                   help='Frozen baseline witnesses.jsonl whose forty rerankings were inspected')
    p.add_argument('--sequence-assessments',type=Path,default=Path('data/qa_pdf_coordinates/sequence_assessments.json'))
    p.add_argument('--coordinate-inputs',type=Path,default=Path('work/qa-coordinate-inputs'))
    p.add_argument('--sequence-images',type=Path,default=Path('work/qa-sequence-coordinate-review'))
    a=p.parse_args()
    report=evaluate(Path('.'),a.database,a.benchmark,a.images)
    if a.sequence_witnesses:
        report['sequence_assessments']=verify_sequence_assessments(
            Path('.'),a.sequence_assessments,a.sequence_witnesses,a.coordinate_inputs,a.sequence_images)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['counts'],sort_keys=True))


if __name__ == '__main__':
    main()
