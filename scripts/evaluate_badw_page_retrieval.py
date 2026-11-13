#!/usr/bin/env python3
"""Read-only evaluation of an existing reconstruction against private source labels.

Labels are observations (family, physical_page, side, source_id, html_sha256),
not acceptance decisions. Null source_id means no acquired HTML counterpart.
Repeated heading anchors on one printed side consume only one shortlist place.
Unknown sides remain unknown; neither labels nor folio offsets fill them in.
This command imports no API client and writes no campaign or canonical data.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3


def load(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def candidate_side(proposal, destination, mapped):
    """Use the reconstruction coordinate frame, never source-label coordinates.

    An unreviewed gutter supplies a retrieval hypothesis, not certified geometry.
    Current reviewed map supplies single-page layout, but its original-PDF crop
    cannot safely be compared with a historical OCR bounding box directly.
    """
    pages = [p for p in mapped.values() if p['family'] == proposal['family']
             and p['physical_page'] == proposal['physical_page']]
    if any(p['side'] == 'single' for p in pages):
        return 'single', 'current reviewed single page'
    if destination.get('geometry_status') == 'single_page_mediabox':
        return 'single', 'reconstruction single-page hypothesis'
    coordinate = proposal.get('coordinate')
    if not coordinate:
        return None, 'missing heading coordinate'
    box = coordinate['box']
    x, y = (box[0]+box[2])/2, (box[1]+box[3])/2
    sides = set()
    for page in destination.get('candidates', []):
        a, b, c, d = page['crop']
        if a <= x < c and b <= y < d:
            sides.add(page['side'])
    return (next(iter(sides)), destination['geometry_status']) if len(sides) == 1 else (None, 'unresolved geometry')


def shortlist(proposals, destinations, mapped):
    result, seen = [], set()
    for proposal in proposals:
        physical = (proposal['family'], proposal['physical_page'])
        side, geometry = candidate_side(proposal, destinations.get(physical, {}), mapped)
        key = (*physical, side)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(family=physical[0], physical_page=physical[1], side=side,
                           geometry=geometry, anchor=proposal['anchor'], score=proposal['score'],
                           heading=proposal['heading_text'], risks=proposal.get('risks', [])))
    return result


def assess(label, candidates):
    physical = lambda c: (c['family'], c['physical_page']) == (label['family'], label['physical_page'])
    individual = lambda c: physical(c) and c['side'] == label['side']
    rank = next((i+1 for i, c in enumerate(candidates) if individual(c)), None)
    scan_rank = next((i+1 for i, c in enumerate(candidates) if physical(c)), None)
    return dict(rank=rank, physical_rank=scan_rank, missing=not candidates,
                correct_scan_unknown_side_top3=any(physical(c) and c['side'] is None for c in candidates[:3]),
                wrong_first=bool(candidates) and not physical(candidates[0]),
                wrong_side_first=bool(candidates) and physical(candidates[0])
                    and candidates[0]['side'] not in (None, label['side']))


def summarize(rows):
    return dict(n=len(rows), first=sum(r['rank'] == 1 for r in rows),
                top3=sum(r['rank'] is not None and r['rank'] <= 3 for r in rows),
                physical_first=sum(r['physical_rank'] == 1 for r in rows),
                physical_top3=sum(r['physical_rank'] is not None and r['physical_rank'] <= 3 for r in rows),
                no_candidate=sum(r['missing'] for r in rows),
                wrong_first_scan=sum(r['wrong_first'] for r in rows),
                wrong_first_side=sum(r['wrong_side_first'] for r in rows),
                correct_scan_unknown_side_top3=sum(r['correct_scan_unknown_side_top3'] for r in rows))


def evaluate(args):
    db = sqlite3.connect(f'file:{Path(args.run).resolve()}/index.sqlite?mode=ro', uri=True)
    destinations = {(f, p): json.loads(body)['destination'] for f, p, body in
                    db.execute('select family,page,body from reading_pages')}
    mapped = load(args.page_map)['pages']
    labels = load(args.labels)['observations']
    # Compare against actual saved requests, not merely planned campaign views.
    cached = {}
    for path in sorted((Path(args.campaign)/'pages').glob('*/pack.json')):
        pack = load(path)
        if not (path.parent/'match.json').exists():
            continue
        physical = (pack['family'], pack['physical_page'])
        entry = cached.setdefault(physical, dict(candidates=set(), supported=set(), reviewed=set()))
        match = load(path.parent/'match.json')
        # Inventory retrieval can enlarge the initial pack. Count what the
        # matcher actually received, including unsupported candidate identities.
        entry['candidates'].update(c['source_id'] for c in match['request']['evidence']['candidates'])
        entry['supported'].update(m['source_id'] for m in match['result']['matches']
                                  if m['outcome'] == 'supported')
        packet = path.parent/'source_review_packet.json'
        if packet.exists():
            entry['reviewed'].update(r['source_id'] for r in load(packet)['associations']
                                     if r['state'] == 'model-source-reviewed')
    compiled = load(args.compiled)
    certified = {r['source_url'] for r in compiled['witnesses']}
    certified.update(r['source_url'] for r in load(args.baseline)['witnesses'])
    rows = []
    for label in labels:
        sid = label.get('source_id')
        if sid is None:
            continue
        witness = db.execute('select body from witnesses where sid=?', (sid,)).fetchone()
        if not witness or json.loads(witness[0])['html_sha256'] != label['html_sha256']:
            raise ValueError(f'HTML identity changed: {sid}')
        proposals = [json.loads(r[0]) for r in db.execute(
            'select body from proposals where sid=? order by score desc,aid', (sid,))]
        candidates = shortlist(proposals, destinations, mapped)
        row = dict(label=label, candidates=candidates[:3], **assess(label, candidates))
        cache = cached.get((label['family'], label['physical_page']))
        row['campaign'] = None if cache is None else dict(
            retrieved=sid in cache['candidates'], supported=sid in cache['supported'],
            independently_reviewed=sid in cache['reviewed'],
            certified=sid.removeprefix('badw:') in certified)
        rows.append(row)
    db.close()
    groups = {'core': [r for r in rows if r['label'].get('stratum') != 'supplement'],
              'supplement': [r for r in rows if r['label'].get('stratum') == 'supplement']}
    comparison = [r for r in rows if r['campaign'] is not None]
    return dict(labels_sha256=digest(args.labels), reconstruction_manifest_sha256=digest(Path(args.run)/'manifest.json'),
                no_html_counterpart=sum(not r.get('source_id') for r in labels),
                metrics={k: summarize(v) for k, v in groups.items()},
                by_kind={k: summarize([r for r in rows if r['label']['kind'] == k])
                         for k in sorted({r['label']['kind'] for r in rows})},
                comparable_cached=dict(retrieval=summarize(comparison),
                    campaign=dict(n=len(comparison), **dict(Counter(
                        k for r in comparison for k, v in r['campaign'].items() if v)))),
                rows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--page-map', default='data/badw_print_page_map.json')
    parser.add_argument('--campaign', default='work/linking-campaign-20261112')
    parser.add_argument('--compiled', default='data/badw_html_print_alignment.generated.json')
    parser.add_argument('--baseline', default='data/badw_html_print_pages.json')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = evaluate(args)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
