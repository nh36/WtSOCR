#!/usr/bin/env python3
"""Check source-region observations against boundary hypotheses and evidence spans.

Provenance checks verify recorded inputs, not the truth of visual observations.
Whole QA rows containing several articles cannot establish sub-line ownership.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from badw_html_print_alignment import FAMILIES, object_digest
from badw_print_reconstruction import column_of
from badw_print_structure import heading_layout, source_barriers


def verify_region(root, region, images, db):
    registry = {r['label']: r for r in csv.DictReader(
        (root/'data/source_pdfs.tsv').open(), delimiter='\t')}
    family, page = region['family'], region['physical_page']
    if region['split'] not in ('development', 'held_out'):
        raise ValueError('invalid fixed split')
    if registry[FAMILIES[family]]['sha256'] != region['source_sha256']:
        raise ValueError('changed registered source')
    if Path(region['image_name']).name != region['image_name']:
        raise ValueError('unsafe image name')
    if hashlib.sha256((images/region['image_name']).read_bytes()).hexdigest() != region['image_sha256']:
        raise ValueError('changed observed image')
    with (root/f'release/current/qa/{family}/{family}_line_zones.tsv').open() as stream:
        rows = {int(r['line']): r for r in csv.DictReader(stream, delimiter='\t')
                if int(r['page']) == page}
    if object_digest([rows[n] for n in sorted(rows)]) != region['page_qa_sha256']:
        raise ValueError('changed page QA')
    indexed = {n: json.loads(body) for n, body in db.execute(
        'SELECT line,body FROM lines WHERE family=? AND page=?', (family, page))}
    if set(indexed) != set(rows) or any(
            indexed[n].get(k) != v for n, row in rows.items() for k, v in row.items()):
        raise ValueError('indexed QA differs from source')
    features = json.loads(db.execute('SELECT features FROM pages WHERE family=? AND page=?',
                                    (family, page)).fetchone()[0])
    if features['source_sha256'] != region['source_sha256']:
        raise ValueError('indexed scan differs from observation')
    for heading in region['headings']:
        for observation in [heading] + heading['definition_probes']:
            n = observation['qa_line']
            if n is not None and (object_digest(rows[n]) != observation['qa_row_sha256'] or
                                  rows[n]['line_text'] != observation['qa_text']):
                raise ValueError('changed observed QA row')
    return indexed, features


def compare(headings, predicted, extents, page):
    """Score complete-region headings; never invent a QA interval from line order."""
    gold = {h['qa_line'] for h in headings if h['qa_line'] is not None}
    missing = sum(h['qa_line'] is None for h in headings)
    counts = Counter(true_positive=len(gold & predicted), false_positive=len(predicted-gold),
                     false_negative=len(gold-predicted)+missing, missing_qa_heading=missing)
    cases = []
    for heading in headings:
        n = heading['qa_line']
        extent = extents.get(n)
        case = dict(printed_heading=heading['printed_heading'], qa_line=n,
                    detected=n in predicted if n is not None else False)
        if not extent or not extent.get('refs'):
            counts['without_testable_extent'] += 1
            case['ownership'] = 'no_testable_extent'
        else:
            refs = {tuple(ref) for ref in extent['refs']}
            own = {(page, p['qa_line']) for p in heading['definition_probes']}
            # Shared merged OCR rows are not negative or positive ownership truth.
            foreign = {(page, p['qa_line']) for h in headings if h is not heading
                       for p in [h] + h['definition_probes'] if p['qa_line'] is not None}
            shared = own & foreign
            own -= shared
            foreign -= shared | {(page, n)}
            contamination = sorted(refs & foreign)
            counts['testable_extent'] += 1
            counts['extents_with_foreign_observed_text'] += bool(contamination)
            counts['definition_probes_recovered'] += len(refs & own)
            counts['definition_probes_testable'] += len(own)
            case.update(ownership='observed_foreign_text' if contamination else 'no_observed_contamination',
                        foreign_observed_refs=contamination,
                        recovered_definition_probes=sorted(refs & own),
                        missing_definition_probes=sorted(own-refs),
                        shared_rows_not_assessable=sorted(shared), extent_status=extent['status'])
        cases.append(case)
    return dict(counts), cases


def evaluate(root, database, benchmark, images):
    labels = json.loads(benchmark.read_text())
    if labels.get('publication_eligible') is not False:
        raise ValueError('benchmark cannot authorise publication')
    if len({r['id'] for r in labels['regions']}) != len(labels['regions']):
        raise ValueError('duplicate observed region')
    db = sqlite3.connect('file:'+str(database.resolve())+'?mode=ro', uri=True)
    results, totals = [], {}
    try:
        for region in labels['regions']:
            rows, features = verify_region(root, region, images, db)
            family, page = region['family'], region['physical_page']
            model = json.loads(db.execute('SELECT body FROM reading_pages WHERE family=? AND page=?',
                                          (family, page)).fetchone()[0])['model']
            layout = heading_layout(rows, lambda b: column_of(b, model))
            starts = [(n, json.loads(body)) for n, body in db.execute(
                'SELECT line,body FROM starts WHERE family=? AND page=?', (family, page))]
            predicted = {n for n, _ in source_barriers(rows, starts, features['height'], layout)}
            extents = {n: json.loads(body) for n, body in db.execute(
                'SELECT s.line,e.body FROM starts s JOIN extents e ON e.aid=s.aid '
                'WHERE s.family=? AND s.page=?', (family, page))}
            counts, cases = compare(region['headings'], predicted, extents, page)
            counts['located_gold_headings'] = sum(
                bool(rows[h['qa_line']].get('coordinate')) for h in region['headings']
                if h['qa_line'] is not None)
            for group in ('all', region['split'], family):
                totals.setdefault(group, Counter()).update(counts)
            results.append(dict(id=region['id'], split=region['split'], counts=counts,
                                false_positive_lines=sorted(predicted-{h['qa_line'] for h in region['headings']}),
                                cases=cases))
    finally:
        db.close()
    summary = {}
    for group, c in totals.items():
        tp, fp, fn = c['true_positive'], c['false_positive'], c['false_negative']
        summary[group] = dict(c, precision=tp/(tp+fp) if tp+fp else None,
                              recall=tp/(tp+fn) if tp+fn else None)
    return dict(schema=1, benchmark_sha256=object_digest(labels), authority=labels['authority'],
                publication_eligible=False,
                limitations='Purposive source-region observations by development agent; not independent scholarly certification. '
                'No observed contamination is not proof of complete ownership. Merged rows and unobserved continuations remain uncertain.',
                summary=summary, regions=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--benchmark', type=Path, default=Path('data/article_ownership/regions.json'))
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(Path(__file__).resolve().parents[1], args.database, args.benchmark, args.images)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\n')
    temporary.replace(args.output)
    print(json.dumps(result['summary'], sort_keys=True))


if __name__ == '__main__':
    main()
