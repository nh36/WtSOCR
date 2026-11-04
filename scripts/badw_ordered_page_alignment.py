#!/usr/bin/env python3
"""Bounded, non-publishing experiment in catalogue/printed-heading alignment.

Reviewed page geometry is an input, not an inferred pagination offset. Held-out
acceptances never supply lexical anchors. C6 headings remain hypotheses.
"""
import argparse
from array import array
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import sqlite3
import unicodedata


def key(text):
    return ' '.join(unicodedata.normalize('NFC', text).translate(
        str.maketrans({'’': "'", '‘': "'", 'ʼ': "'"})).casefold().split())


def similarity(left, right):
    a, b = key(left), key(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def align(html, printed, fixed=()):
    """Weighted monotone alignment, with free gaps and immutable anchor pairs.

    Return hypotheses, not identity assertions. A repeated spelling can have
    several equally optimal paths; callers must retain its competing pages.
    """
    fixed = sorted(fixed)
    if any(a[0] >= b[0] or a[1] >= b[1]
           for a, b in zip(fixed, fixed[1:])):
        raise ValueError('fixed anchors contradict monotone order')
    if any(not (0 <= i < len(html) and 0 <= j < len(printed)) for i, j in fixed):
        raise ValueError('anchor outside sequence')
    result = []
    bounds = [(-1, -1), *fixed, (len(html), len(printed))]
    for (a, b), (c, d) in zip(bounds, bounds[1:]):
        n, m = c-a-1, d-b-1
        trace = [bytearray(m+1) for _ in range(n+1)]
        previous = array('d', [0.0]) * (m+1)
        for i in range(1, n+1):
            current = array('d', [0.0]) * (m+1)
            for j in range(1, m+1):
                score = similarity(html[a+i]['headword'], printed[b+j]['headword'])
                match = previous[j-1] + (score-0.72 if score >= 0.80 else -1)
                values = (previous[j], current[j-1], match)
                best = max(range(3), key=lambda k: values[k])
                current[j], trace[i][j] = values[best], best
            previous = current
        i, j = n, m
        segment = []
        while i and j:
            direction = trace[i][j]
            if direction == 2:
                segment.append((a+i, b+j, similarity(
                    html[a+i]['headword'], printed[b+j]['headword'])))
                i, j = i-1, j-1
            elif direction == 0:
                i -= 1
            else:
                j -= 1
        result.extend(reversed(segment))
        if c < len(html):
            result.append((c, d, 1.0))
    return result


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def ordering_diagnostics(html, manifest):
    """Compare reviewed page order with HTML-only catalogue order.

    Same-page pairs cannot establish heading order; fallback keys are reported
    separately because they do not participate in the ordinary lexical range.
    """
    identities = {(h['source_url'], h['html_sha256']): (i, h)
                  for i, h in enumerate(html)}
    pages = manifest['pages']
    groups = {}
    stale = 0
    for witness in manifest['witnesses']:
        identity = identities.get((witness['source_url'], witness['html_sha256']))
        if identity is None:
            stale += 1
            continue
        page = pages[witness['page']]
        groups.setdefault(str(page['volume']), []).append(
            (page['printed_page'], identity[0], identity[1]))
    result = {}
    for volume, rows in sorted(groups.items()):
        ordinary = sorted(r for r in rows if not r[2].get('collation_fallback'))
        inversions = []
        comparable = same_page = 0
        for n, left in enumerate(ordinary):
            for right in ordinary[n+1:]:
                if left[0] == right[0]:
                    same_page += 1
                    continue
                comparable += 1
                if left[1] > right[1]:
                    inversions.append({'earlier': left[2]['sid'],
                                       'later': right[2]['sid'],
                                       'pages': [left[0], right[0]]})
        result[volume] = {'reviewed': len(rows),
                          'fallback': len(rows)-len(ordinary),
                          'comparable_pairs': comparable,
                          'same_page_order_unchecked': same_page,
                          'page_inversions': len(inversions),
                          'inversion_examples': inversions[:20]}
    return {'volumes': result, 'stale_or_missing_identities': stale}


def experiment(index, catalogue, facsimiles, heldout=(16, 18, 22)):
    manifest = json.loads(Path(facsimiles).read_text())
    pages = {k: p for k, p in manifest['pages'].items()
             if p['volume'] == 1 and 14 <= p['printed_page'] <= 23}
    db = sqlite3.connect(Path(index).resolve().as_uri()+'?mode=ro', uri=True)
    try:
        witnesses = {w['id']: w for (body,) in db.execute('SELECT body FROM witnesses')
                     for w in [json.loads(body)]}
        catalogue_rows = json.loads(Path(catalogue).read_text())['entries']
        html = [{'sid': witnesses[e['id']]['sid'],
                 'source_url': witnesses[e['id']]['source_url'],
                 'html_sha256': witnesses[e['id']]['html_sha256'],
                 'headword': e['headword']['loc'], 'homonym': e.get('homonym'),
                 'collation_fallback': e.get('collation_fallback')}
                for e in catalogue_rows if e.get('source_kind') == 'html'
                and e['id'] in witnesses]
        if len(html) != 18038:
            raise ValueError(f'incomplete HTML catalogue: {len(html)}')
        by_identity = {(h['source_url'], h['html_sha256']): i for i, h in enumerate(html)}
        ordering = ordering_diagnostics(html, manifest)
        accepted = [w for w in manifest['witnesses'] if w['page'] in pages
                    and (w['source_url'], w['html_sha256']) in by_identity]
        # Restrict by reviewed lexical endpoints, not by withheld identities.
        training_all = [w for w in accepted if pages[w['page']]['printed_page'] not in heldout]
        # Unsupported Tibetan stacks live in the catalogue's fallback tail.
        # They cannot define a contiguous ordinary Tibetan lexical range.
        fallback_training = [w for w in training_all
                             if html[by_identity[w['source_url'], w['html_sha256']]]['collation_fallback']]
        training = [w for w in training_all if w not in fallback_training]
        endpoints = [by_identity[w['source_url'], w['html_sha256']] for w in training]
        lo, hi = min(endpoints), max(endpoints)
        html = html[lo:hi+1]
        by_identity = {(h['source_url'], h['html_sha256']): i for i, h in enumerate(html)}
        printed = []
        excluded = Counter()
        for (body,) in db.execute('SELECT body FROM anchors ORDER BY aid'):
            a = json.loads(body)
            if a['volume'] != 'wts_1_34' or not 40 <= a['start_page'] <= 44:
                continue
            row = db.execute('SELECT position,body FROM reading_lines WHERE family=? AND page=? AND line=?',
                             (a['volume'], a['start_page'], a['start_line'])).fetchone()
            if not row or not json.loads(row[1]).get('box'):
                excluded['missing_coordinate'] += 1
                continue
            box = json.loads(row[1])['box']
            candidates = [(k, p) for k, p in pages.items() if p['physical_page'] == a['start_page']
                          and p['crop'][0] <= (box[0]+box[2])/2 <= p['crop'][2]]
            if len(candidates) != 1:
                excluded['unreviewed_or_ambiguous_side'] += 1
                continue
            page_key, page = candidates[0]
            if box[1] < 30 or box[3] > page['crop'][3]-20:
                excluded['possible_page_furniture'] += 1
                continue
            printed.append({'anchor': a['anchor_id'], 'headword': a['headword_loc_display'],
                            'page': page_key, 'printed_page': page['printed_page'],
                            'physical_page': a['start_page'], 'side': page['side'],
                            'position': row[0], 'box': box,
                            'status': 'located_heading_hypothesis'})
    finally:
        db.close()
    printed.sort(key=lambda p: (p['printed_page'], p['position'], p['anchor']))
    fixed = []
    excluded_anchors = [{'source_url': w['source_url'],
                         'reason': 'catalogue_collation_fallback_outside_ordered_sequence'}
                        for w in fallback_training]
    for w in training:
        identity = (w['source_url'], w['html_sha256'])
        candidates = [j for j, p in enumerate(printed) if p['page'] == w['page']
                      and key(p['headword']) == key(w['printed_heading'])]
        if len(candidates) == 1:
            fixed.append((by_identity[identity], candidates[0]))
        else:
            excluded_anchors.append({'source_url': w['source_url'], 'reason': 'heading_missing_or_repeated'})
    fixed.sort()
    inversions = [(a, b) for a, b in zip(fixed, fixed[1:]) if a[1] >= b[1]]
    if inversions:
        raise ValueError(f'reviewed anchor order inversion: {inversions}')
    matches = {i: (j, score) for i, j, score in align(html, printed, fixed)}
    assignments = []
    for i, h in enumerate(html):
        before = max((p for k, p in fixed if k <= i), default=None)
        after = min((p for k, p in fixed if k >= i), default=None)
        lower = printed[before]['printed_page'] if before is not None else 14
        upper = printed[after]['printed_page'] if after is not None else 23
        alternatives = sorted({p['printed_page'] for p in printed
                               if lower <= p['printed_page'] <= upper
                               and similarity(h['headword'], p['headword']) >= .8})
        match = matches.get(i)
        assignments.append({**h, 'page_interval': [lower, upper],
                            'candidate_pages': alternatives,
                            'selected': printed[match[0]] if match else None,
                            'similarity': match[1] if match else None,
                            'eligible_for_reader_attachment': False})
    lookup = {(a['source_url'], a['html_sha256']): a for a in assignments}
    evaluation = []
    for w in accepted:
        expected = pages[w['page']]['printed_page']
        if expected not in heldout:
            continue
        a = lookup.get((w['source_url'], w['html_sha256']))
        observed = a['selected']['printed_page'] if a and a['selected'] else None
        evaluation.append({'source_url': w['source_url'], 'expected_page': expected,
                           'predicted_page': observed, 'correct': observed == expected,
                           'alternatives': a['candidate_pages'] if a else [],
                           'scope': 'previously reviewed page; withheld lexical acceptance'})
    return {'contract': 'wtsocr-ordered-page-experiment-v1',
            'ordering_diagnostics': ordering,
            'inputs': {str(p): digest(p) for p in (index, catalogue, facsimiles)},
            'heldout_pages': list(heldout), 'page_geometry': pages,
            'training_anchor_count': len(fixed), 'excluded_training': excluded_anchors,
            'excluded_heading_counts': dict(excluded), 'printed_headings': printed,
            'assignments': assignments, 'evaluation': evaluation,
            'summary': {'html_witnesses': len(html), 'heading_hypotheses': len(printed),
                        'heldout_count': len(evaluation),
                        'heldout_correct': sum(e['correct'] for e in evaluation)},
            'publication_authority': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('index', 'catalogue', 'facsimiles', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    result = experiment(args.index, args.catalogue, args.facsimiles)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(args.output)
    print(json.dumps(result['summary'], sort_keys=True))


if __name__ == '__main__':
    main()
