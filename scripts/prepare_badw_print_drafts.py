"""Prepare deterministic, non-publishable HTML-to-print review drafts.

No visual observations or approval fields are generated. The ordinary certificate
compiler remains the only attachment route. A draft is a preparation envelope,
not an accepted assertion, even if all historical bindings are available.
"""
import argparse
import csv
import json
from pathlib import Path

import badw_html_print_alignment as a


def prepare(certificate, body, anchor_id, anchors, edges, registry, qa_rows,
            page_key=None, reserved=()):
    sid = body['inspection_id']
    if body['source_kind'] != 'html':
        raise ValueError('exact acquired HTML witness required')
    if sid in reserved or any(sid == r['source_id'] for p in certificate['pages'] for r in p['accepted']):
        raise ValueError('duplicate witness assignment')
    if any(anchor_id == r['anchor'] for p in certificate['pages'] for r in p['accepted']):
        raise ValueError('heading anchor already assigned')
    anchor = anchors.get(anchor_id)
    missing = []
    if anchor is None:
        missing.append('C6 heading anchor')
    matching = [e for e in edges if e['source_id'] == sid and e['local_anchor_id'] == anchor_id]
    if not matching:
        missing.append('C11 identity edge (reviewed correction may be required)')
    pages = [p for p in certificate['pages'] if p['key'] == page_key] if page_key else []
    if len(pages) > 1:
        raise ValueError('duplicate page records')
    page = pages[0] if pages else None
    if page and anchor and (page['family'], page['physical_page']) != (anchor['volume'], anchor['start_page']):
        raise ValueError('anchor outside reviewed page')
    if page_key and page is None:
        raise ValueError('unknown reviewed page key')
    source = registry.get(a.FAMILIES.get(anchor['volume'])) if anchor else None
    if page and (not source or page['source_sha256'] != source['sha256']):
        raise ValueError('stale reviewed source')
    if page is None:
        missing.append('visually reviewed folio, side and geometry')
    rows = [r for (family, physical, _), r in sorted(qa_rows.items())
            if anchor and (family, physical) == (anchor['volume'], anchor['start_page'])]
    if not rows:
        missing.append('source-bound QA rows')
    return dict(status='draft; no attachment authority', source_id=sid,
        editorial=dict(source_url=body['source_url'], headword=body['headword']['loc'], homonym=body['homonym']),
        html_sha256=body['sources'][0]['sha256'], proposed_anchor=anchor_id,
        anchor=anchor, anchor_sha256=a.object_digest(anchor) if anchor else None,
        candidate_edges=[dict(record=e, sha256=a.object_digest(e)) for e in matching],
        source=source, reviewed_page={k:v for k,v in page.items() if k != 'accepted'} if page else None,
        components=[dict(record=c, sha256=a.object_digest(c)) for c in body['components']],
        qa_rows=rows, qa_rows_sha256=a.object_digest(rows), missing_bindings=missing,
        required_observations=['printed heading and homonym (including absence)',
            'independent article boundary and physical location',
            'discriminating printed lexical evidence and exact HTML agreement',
            'explicit reviewer provenance and acceptance decision'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bodies', type=Path, required=True)
    parser.add_argument('--proposals', type=Path, required=True,
                        help='JSON list: source_id, anchor, optional existing page key')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cert = json.loads(a.CERTIFICATE.read_text())
    for name, expected in cert['inputs'].items():
        if a.digest(a.ROOT/name) != expected:
            raise ValueError('stale pinned input: '+name)
    bodies = json.loads(args.bodies.read_text())
    anchors = {r['anchor_id']:r for r in map(json.loads, (a.ROOT/a.INPUTS['anchors']).open())}
    edges = list(map(json.loads, (a.ROOT/a.INPUTS['edges']).open()))
    registry = {r['label']:r for r in csv.DictReader((a.ROOT/'data/source_pdfs.tsv').open(), delimiter='\t')}
    qa = {}
    for family in a.FAMILIES:
        for row in csv.DictReader((a.ROOT/f'release/current/qa/{family}/{family}_line_zones.tsv').open(), delimiter='\t'):
            qa[family,int(row['page']),int(row['line'])] = row
    drafts, seen, used = [], set(), set()
    for proposal in json.loads(args.proposals.read_text()):
        if proposal['anchor'] in used:
            raise ValueError('duplicate proposed heading anchor')
        drafts.append(prepare(cert, bodies[proposal['source_id']], proposal['anchor'], anchors,
                              edges, registry, qa, proposal.get('page'), seen))
        seen.add(proposal['source_id']); used.add(proposal['anchor'])
    args.output.write_text(json.dumps(dict(status='drafts only; never compiler input', drafts=drafts), ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
