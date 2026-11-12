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
    if any(anchor_id == r.get('anchor') for p in certificate['pages'] for r in p['accepted']):
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


def prepare_direct(certificate, body, page_key, anchors, edges, registry, reserved=()):
    """Bind clerical inputs for source review, without inventing an observation."""
    sid = body['inspection_id']
    if body['source_kind'] != 'html':
        raise ValueError('exact acquired HTML witness required')
    if sid in reserved or any(sid == r['source_id'] for p in certificate['pages'] for r in p['accepted']):
        raise ValueError('duplicate witness assignment')
    pages = [p for p in certificate['pages'] if p['key'] == page_key]
    if len(pages) != 1:
        raise ValueError('exactly one reviewed page required')
    page = pages[0]
    if registry[page['source']]['sha256'] != page['source_sha256']:
        raise ValueError('stale reviewed source')
    historical = [e for e in edges if e['source_id'] == sid]
    historical_anchors = [anchors[k] for k in sorted({e['local_anchor_id'] for e in historical} & set(anchors))]
    return dict(status='draft; no attachment authority', certificate_type=a.DIRECT_TYPE,
        source_id=sid, editorial=dict(source_url=body['source_url'], headword=body['headword']['loc'], homonym=body['homonym']),
        html_sha256=body['sources'][0]['sha256'], page=page_key,
        page_sha256=a.object_digest(a.page_binding(page)),
        historical_evidence=dict(edges_sha256=a.object_digest(historical), anchors_sha256=a.object_digest(historical_anchors)),
        historical_edges=historical, historical_anchors=historical_anchors,
        components=[dict(record=c, sha256=a.object_digest(c)) for c in body['components']],
        prior_decisions=[dict(record=d, sha256=a.object_digest(d)) for d in certificate.get('decisions', []) if d['source_id'] == sid],
        required_observations=['reviewed heading inventory item with precise PDF heading, article and evidence coordinates',
            'observed spelling, printed homonym or absence, neighbouring boundaries and lexical evidence',
            'historical association defect, exact HTML component agreement, explicit provenance and decision'])


def bind_reviewed_direct(certificate, body, page_key, item_id, component_index,
                        historical_issue, historical_reason, anchors, edges, registry):
    """Serialize an already reviewed inventory item, then run the ordinary gate.

    This is an operator-side clerical step, never called by the model worker.
    Provisional worker inventories lack the required explicit source review.
    No observation, provenance or acceptance decision is inferred here.
    """
    draft = prepare_direct(certificate, body, page_key, anchors, edges, registry)
    page = next(p for p in certificate['pages'] if p['key'] == page_key)
    inventory = page.get('source_heading_inventory', {})
    items = [i for i in inventory.get('items', []) if i.get('item_id') == item_id]
    if len(items) != 1:
        raise ValueError('exact reviewed inventory item required')
    item = items[0]
    decision = item.get('source_review', {})
    if (decision.get('decision') != 'accept' or not decision.get('reason')
            or not decision.get('reviewer') or decision['reviewer'] != inventory.get('reviewer')):
        raise ValueError('explicit source inspection and acceptance required')
    if not isinstance(component_index, int) or isinstance(component_index, bool) or component_index < 0:
        raise ValueError('explicit exact HTML component index required')
    if component_index >= len(body['components']):
        raise ValueError('exact HTML component index outside witness')
    component = body['components'][component_index]
    assertion = dict(certificate_type=a.DIRECT_TYPE, source_id=draft['source_id'],
        editorial=draft['editorial'], html_sha256=draft['html_sha256'],
        heading_id=item_id, heading_item_sha256=a.object_digest(item),
        printed_homonym=item['printed_homonym'], review_basis=inventory['review_basis'],
        source_review=dict(decision), historical_evidence=dict(draft['historical_evidence'],
            issue=historical_issue, reason=historical_reason),
        lexical_agreement_reason=item['identity_reason'],
        print_observation=dict(heading=item['heading'], homonym=item['printed_homonym'],
            evidence=item['printed_evidence'], identity_context=item['identity_reason'],
            page_sha256=draft['page_sha256'], verification='visual transcription; not machine-verified'))
    if draft['prior_decisions']:
        reconsider = item.get('reconsideration', {})
        assertion['reconsideration'] = reconsider
    if component['type'] == 'definition':
        assertion.update(definition_evidence=component['source_form'].strip(),
                         definition_component_sha256=a.object_digest(component))
    elif component['type'] == 'cross_reference':
        assertion.update(evidence_kind='cross_reference_only',
            cross_reference_evidence=component['source_form'].strip(),
            cross_reference_component_sha256=a.object_digest(component))
        for field in ('cross_reference', 'heading_variant'):
            if field in item:
                assertion['print_observation'][field] = item[field]
        if 'heading_variant' in item:
            variants = [c for c in body['components'] if c['type'] == 'tibetan'
                        and c['source_form'].strip() == item['heading_variant']]
            if len(variants) != 1:
                raise ValueError('exact reference variant binding required')
            assertion['variant_component_sha256'] = a.object_digest(variants[0])
    else:
        raise ValueError('reviewed definition or cross-reference component required')
    a.validate_direct(assertion, body, page, anchors, edges, certificate.get('decisions', []))
    return assertion


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
        if proposal.get('certificate_type') == a.DIRECT_TYPE:
            drafts.append(prepare_direct(cert, bodies[proposal['source_id']], proposal['page'], anchors, edges, registry, seen))
            seen.add(proposal['source_id'])
            continue
        if proposal['anchor'] in used:
            raise ValueError('duplicate proposed heading anchor')
        drafts.append(prepare(cert, bodies[proposal['source_id']], proposal['anchor'], anchors,
                              edges, registry, qa, proposal.get('page'), seen))
        seen.add(proposal['source_id']); used.add(proposal['anchor'])
    args.output.write_text(json.dumps(dict(status='drafts only; never compiler input', drafts=drafts), ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
