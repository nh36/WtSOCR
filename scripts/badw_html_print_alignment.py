"""Compile page-reviewed HTML alignment certificates; never accept candidates automatically.

Candidate edges and OCR anchors are locators, not identity assertions. Acceptance
requires a reviewed heading position, explicit printed homonym (including null),
and a distinguishing definition checked in both the scan and editorial witness.
The compact certificates are manual; the expanded, checksum-bound ledger is generated.
"""
import argparse
import collections
import csv
import hashlib
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CERTIFICATE = ROOT/'data/badw_html_print_alignment.json'
GENERATED = ROOT/'data/badw_html_print_alignment.generated.json'
FAMILIES = {'wts_1_34': 'WtS_1-34', 'wts_35_51': 'WtS_35-51',
            'wts_8_b': 'WtS_8-b', 'wts_9_m': 'WtS_9-m'}
INPUTS = {
    'anchors': 'work/badw_stage_c6_20260918/from_frozen_c5/local_heading_inventory.jsonl',
    'edges': 'work/badw_stage_c11_20260924/identity_handoff/candidate_identity_edges.jsonl',
    'handoff': 'work/badw_stage_c11_20260924/identity_handoff/source_identity_handoff.jsonl',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def object_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def proof_key(text):
    # Evidence comparison only; does not change dictionary/search text.
    return ''.join(c for c in unicodedata.normalize('NFC', text).casefold() if c.isalnum())


def validate_assertion(assertion, body, anchor, edges):
    if body['source_kind'] != 'html' or assertion['source_id'] != body['inspection_id']:
        raise ValueError('not an exact HTML witness')
    if assertion['anchor'] != anchor['anchor_id'] or not any(e['source_id'] == assertion['source_id'] and e['local_anchor_id'] == assertion['anchor'] for e in edges):
        raise ValueError('assertion has no pinned candidate edge')
    if assertion.get('heading_position') not in ('left column', 'right column'):
        raise ValueError('a running header or continuation is not a heading position')
    if 'printed_homonym' not in assertion:
        raise ValueError('printed homonym must be explicit, including absence')
    if assertion['html_sha256'] != body['sources'][0]['sha256'] or assertion['anchor_sha256'] != object_digest(anchor):
        raise ValueError('stale reviewed source evidence')
    printed = assertion['printed_homonym']
    if printed is not None and str(printed) != str(body.get('homonym')):
        raise ValueError('competing numbered homonym')
    quote = assertion['definition_evidence']
    if not proof_key(quote):
        raise ValueError('empty HTML evidence')
    components = [c for c in body['components'] if c['type'] == 'definition' and proof_key(quote) in proof_key(c['source_form'])]
    if not components:
        raise ValueError('reviewed definition not present in this HTML witness')
    if assertion['definition_component_sha256'] != object_digest(components[0]):
        raise ValueError('stale definition evidence')
    if not assertion.get('scan_review'):
        raise ValueError('scan identity review required, especially for unnumbered print')
    observation = assertion.get('print_observation', {})
    # These are human transcriptions, NOT an OCR verification of printed wording.
    # Bind the observed heading and evidence to the same inspected entry. The
    # compiler can reject a different anchor; only a reviewer can detect a false
    # transcription or a definition borrowed from a neighbour within the image.
    if observation.get('heading_anchor') != anchor['anchor_id'] or observation.get('evidence_anchor') != anchor['anchor_id']:
        raise ValueError('printed heading and evidence must belong to the same inspected entry')
    if observation.get('homonym') != printed or 'homonym' not in observation:
        raise ValueError('inconsistent printed homonym observation')
    if observation.get('column') != assertion['heading_position']:
        raise ValueError('inconsistent observed column')
    for field in ('heading', 'evidence', 'identity_context'):
        if not observation.get(field, '').strip():
            raise ValueError('independent printed observation required: '+field)
    if observation.get('verification') != 'visual transcription; not machine-verified':
        raise ValueError('visual scholarship must be labelled explicitly')
    return components[0]


def compile_records(certificate, bodies, anchors, edges, registry):
    """Pure deterministic expansion. Every emitted witness has an explicit certificate."""
    pages, witnesses, seen, used_anchors = {}, [], set(), {}
    decisions = {(d['source_id'], d['anchor']): d for d in certificate.get('decisions', [])}
    for page in certificate['pages']:
        key = page['key']
        if key in pages:
            raise ValueError('duplicate printed page')
        if FAMILIES.get(page['family']) != page['source']:
            raise ValueError('scan family differs from registered source')
        source = registry[page['source']]
        if page['source_sha256'] != source['sha256']:
            raise ValueError('stale source identity')
        pages[key] = {k: page[k] for k in ('source', 'source_sha256', 'physical_page', 'volume', 'printed_page', 'side', 'crop', 'geometry_review', 'page_evidence')}
        for assertion in page['accepted']:
            sid = assertion['source_id']
            if sid in seen:
                raise ValueError('witness assigned twice')
            seen.add(sid)
            body, anchor = bodies[sid], anchors[assertion['anchor']]
            if anchor['start_page'] != page['physical_page'] or anchor['volume'] != page['family']:
                raise ValueError('physical anchor differs from reviewed page')
            decision = decisions.get((sid, assertion['anchor']))
            if decision:
                reconsideration = assertion.get('reconsideration', {})
                if reconsideration.get('decision_sha256') != object_digest(decision) or not reconsideration.get('reason'):
                    raise ValueError('rejected/deferred decision requires explicit reconsideration')
            component = validate_assertion(assertion, body, anchor, edges)
            observation = assertion['print_observation']
            binding = {k: page[k] for k in ('source', 'source_sha256', 'physical_page', 'volume', 'printed_page', 'side', 'crop')}
            if observation.get('page_sha256') != object_digest(binding):
                raise ValueError('printed observation differs from reviewed folio/geometry')
            previous = used_anchors.get(assertion['anchor'])
            if previous:
                relation = assertion.get('multi_witness_relationship', {})
                if (relation != previous.get('multi_witness_relationship') or
                    not relation.get('reason') or
                    not {sid, previous['source_id']} <= set(relation.get('source_ids', [])) or
                    observation != previous['print_observation']):
                    raise ValueError('conflicting reuse of a printed heading anchor')
            used_anchors[assertion['anchor']] = assertion
            witnesses.append(dict(source_url=body['source_url'], html_sha256=body['sources'][0]['sha256'],
                headword=body['headword']['loc'], homonym=body['homonym'], page=key,
                printed_heading=observation['heading'], printed_homonym=observation['homonym'],
                evidence=dict(certificate=assertion, anchor_sha256=object_digest(anchor),
                    definition_component_sha256=object_digest(component)),
                review_basis='Human visual transcription and identity adjudication, not automatic verification of printed wording; compiler verifies source, page, anchor and HTML component bindings.'))
    result = dict(version=2, certificate_sha256=object_digest(certificate), pages=pages, witnesses=witnesses)
    result['content_sha256'] = object_digest(result)
    return result


def validate_expansion(certificate, expanded):
    """Check the reviewed projection even when private OCR/HTML inputs are absent.

    This checks consistency, not the truth of human visual transcriptions.
    Source-bound regeneration with --check remains the stronger certification.
    """
    if expanded.get('certificate_sha256') != object_digest(certificate):
        raise ValueError('stale generated alignment certificate')
    if expanded.get('content_sha256') != object_digest({k:v for k,v in expanded.items() if k != 'content_sha256'}):
        raise ValueError('changed generated alignment content')
    expected_pages = {p['key']:{k:p[k] for k in ('source','source_sha256','physical_page','volume','printed_page','side','crop','geometry_review','page_evidence')} for p in certificate['pages']}
    if expanded['pages'] != expected_pages:
        raise ValueError('generated page differs from certificate')
    assertions = [(p['key'], r) for p in certificate['pages'] for r in p['accepted']]
    if len(expanded['witnesses']) != len(assertions):
        raise ValueError('generated witness count differs from certificate')
    for witness, (key, assertion) in zip(expanded['witnesses'], assertions):
        observed = assertion['print_observation']
        if (witness['page'] != key or witness['evidence']['certificate'] != assertion or
            witness['printed_heading'] != observed['heading'] or witness['printed_homonym'] != observed['homonym'] or
            witness['html_sha256'] != assertion['html_sha256'] or
            witness['evidence']['definition_component_sha256'] != assertion['definition_component_sha256'] or
            witness['evidence']['anchor_sha256'] != assertion['anchor_sha256']):
            raise ValueError('generated witness differs from certificate')


def inventory(bodies, handoff, edges, accepted):
    by_source = collections.defaultdict(list)
    for e in edges:
        by_source[e['source_id']].append(e)
    counts = collections.Counter()
    families = collections.defaultdict(collections.Counter)
    for sid, body in bodies.items():
        es = by_source[sid]
        if body['source_url'] in accepted:
            category = 'reviewed_exact_heading_page'
        elif not es:
            category = 'no_usable_candidate'
        elif handoff.get(sid, {}).get('evidence_reason') == 'duplicate_exact_heading':
            category = 'competing_exact_headings'
        elif any(e['latin_exact'] and e['tibetan_exact'] for e in es):
            category = 'dual_heading_candidate_page_unverified'
        else:
            category = 'one_field_lexical_candidate'
        counts[category] += 1
        family = ','.join(sorted({e['local_coordinate']['volume'] for e in es})) or 'none'
        families[family][category] += 1
    return dict(total=len(bodies), categories=dict(counts), scan_families=dict(families),
        policy='Historical HTML handoff has no accepted source identities. Dual heading and competing heading categories remain candidates, not verified lexical identities or pages; unreviewed running headers/continuations cannot be counted separately without page review.')


def review_queue(certificate, baseline, bodies, anchors, edges):
    """Rank unreviewed physical-page locators; never emit accepted assignments.

    Printed folios, entry starts, geometry and candidate identities still need
    facsimile inspection. Density and dual-script agreement only prepare review.
    """
    accepted = {r['source_url'] for r in baseline['witnesses']}
    accepted.update(bodies[r['source_id']]['source_url'] for p in certificate['pages'] for r in p['accepted'])
    occupied = {(p['source'], p['physical_page']) for p in baseline['pages'].values()}
    occupied.update((p['source'], p['physical_page']) for p in certificate['pages'])
    # Includes inspected pages with no acceptance, retained as negative controls.
    occupied.update({('WtS_1-34', 43), ('WtS_35-51', 107)})
    grouped = collections.defaultdict(dict)
    alternatives = collections.defaultdict(set)
    for edge in edges:
        alternatives[edge['source_id']].add(edge['local_anchor_id'])
    for edge in edges:
        sid, aid = edge['source_id'], edge['local_anchor_id']
        if sid not in bodies or aid not in anchors or bodies[sid]['source_url'] in accepted:
            continue
        anchor = anchors[aid]
        family, physical = anchor['volume'], anchor['start_page']
        if family not in FAMILIES or (FAMILIES[family], physical) in occupied:
            continue
        definitions = [c['source_form'] for c in bodies[sid]['components'] if c['type']=='definition']
        grouped[family,physical][sid,aid] = dict(source_id=sid, anchor=aid,
            editorial_heading=bodies[sid]['headword']['loc'], editorial_homonym=bodies[sid].get('homonym'),
            dual_heading=bool(edge['latin_exact'] and edge['tibetan_exact']),
            competing_anchors=len(alternatives[sid]),
            definition_alphanumeric=sum(len(proof_key(d)) for d in definitions),
            anchor_sha256=object_digest(anchor))
    pages = []
    for (family, physical), candidates in grouped.items():
        values = sorted(candidates.values(), key=lambda r:(anchors[r['anchor']]['start_line'],r['source_id']))
        strong = sum(r['dual_heading'] and r['competing_anchors']==1 for r in values)
        pages.append(dict(family=family, source=FAMILIES[family], physical_page=physical,
            printed_volume=None, printed_folio=None, geometry=None, status='unreviewed candidate page',
            candidates=values, candidate_count=len({r['source_id'] for r in values}),
            unique_dual_heading=strong,
            homonym_controls=sum(r['editorial_homonym'] not in (None,1) or r['competing_anchors']>1 for r in values),
            sparse_definition_controls=sum(r['definition_alphanumeric']<=20 for r in values)))
    selected = []
    for family in FAMILIES:
        pool = [p for p in pages if p['family']==family]
        ranking = lambda p:(-p['unique_dual_heading'],-p['candidate_count'],p['physical_page'])
        chosen = []
        for reason, ordered, limit in (
            ('density and independent-review potential',sorted(pool,key=ranking),8),
            ('competing/numbered homonym control',sorted(pool,key=lambda p:(-p['homonym_controls'],*ranking(p))),2),
            ('sparse-definition control',sorted(pool,key=lambda p:(-p['sparse_definition_controls'],*ranking(p))),2)):
            available = [p for p in ordered if p not in chosen]
            for page in available[:limit]:
                page['selection_reason']=reason
                chosen.append(page)
        selected.extend(chosen)
    return dict(version=1, status='Review preparation only; no new acceptances',
        certificate_sha256=object_digest(certificate), inputs=certificate['inputs'],
        policy='Physical-page locators only. Printed folios, spread sides, headings, identity and gutter geometry require independent review. No pagination offset or crop is extrapolated. Includes density and difficult controls; lexical agreement is not proof.',
        physical_pages=len(selected), candidates=sum(p['candidate_count'] for p in selected), pages=selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--bodies', type=Path, help='Private JSON map of current HTML reader bodies by inspection_id')
    inputs.add_argument('--reader', type=Path, help='Existing reader whose HTML bodies supply the acquired source evidence')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--queue', type=Path, help='Write a deterministic candidate-only next review queue')
    args = parser.parse_args()
    cert = json.loads(CERTIFICATE.read_text())
    for name, expected in cert['inputs'].items():
        if digest(ROOT/name) != expected:
            raise ValueError('stale pinned evidence: '+name)
    if args.reader:
        catalog = json.loads((args.reader/'data.json').read_text())['entries']
        bodies = {}
        for entry in catalog:
            if entry['source_kind'] == 'html':
                body = json.loads((args.reader/entry['path']).read_text())
                bodies[body['inspection_id']] = body
    else:
        bodies = json.loads(args.bodies.read_text())
    anchors = {r['anchor_id']: r for r in map(json.loads, (ROOT/INPUTS['anchors']).open())}
    edges = list(map(json.loads, (ROOT/INPUTS['edges']).open()))
    registry = {r['label']: r for r in csv.DictReader((ROOT/'data/source_pdfs.tsv').open(), delimiter='\t')}
    generated = compile_records(cert, bodies, anchors, edges, registry)
    generated['inputs'] = cert['inputs']
    generated['content_sha256'] = object_digest({k:v for k,v in generated.items() if k != 'content_sha256'})
    text = json.dumps(generated, ensure_ascii=False, indent=2)+'\n'
    if args.check:
        if GENERATED.read_text() != text:
            raise ValueError('generated alignment ledger is stale')
    else:
        GENERATED.write_text(text)
    if args.inventory:
        handoff = {r['source_id']: r for r in map(json.loads, (ROOT/INPUTS['handoff']).open())}
        baseline = json.loads((ROOT/'data/badw_html_print_pages.json').read_text())
        accepted = {r['source_url'] for r in baseline['witnesses']+generated['witnesses']}
        args.inventory.write_text(json.dumps(inventory(bodies, handoff, edges, accepted), ensure_ascii=False, indent=2)+'\n')
    if args.queue:
        baseline = json.loads((ROOT/'data/badw_html_print_pages.json').read_text())
        args.queue.write_text(json.dumps(review_queue(cert, baseline, bodies, anchors, edges), ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(witnesses=len(generated['witnesses']), pages=len(generated['pages']))))


if __name__ == '__main__':
    main()
