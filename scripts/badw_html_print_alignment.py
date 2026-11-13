"""Compile source-reviewed HTML alignment certificates under closed review policies.

Candidate edges and OCR anchors are locators, not identity assertions. Acceptance
requires a reviewed heading position, explicit printed homonym (including null),
and a distinguishing definition checked in both the scan and editorial witness.
Certificates retain their human, agent or model review provenance; the expanded,
checksum-bound ledger is generated.
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


REVIEW_BASIS = 'Human visual transcription and identity adjudication, not automatic verification of printed wording; compiler verifies source, page, anchor, QA spans and HTML component bindings.'
AGENT_REVIEW_BASIS = 'Agent visual inspection and identity adjudication; no independent human review and no automatic verification of printed wording; compiler verifies source, page, anchor, QA spans and HTML component bindings.'
DIRECT_TYPE = 'direct-source-heading-v1'
DIRECT_REVIEW_BASIS = 'Agent source-image inspection and identity adjudication; no independent human review; compiler verifies registered source, reviewed geometry, heading inventory and exact HTML component bindings, not printed transcription.'


def review_basis(assertion):
    """Closed provenance vocabulary; absent labels preserve legacy certificates.

    A label describes the reviewer, never supplies article or identity evidence.
    Each certificate type enforces its source and identity gates.
    """
    basis = assertion.get('review_basis', REVIEW_BASIS)
    from certify_badw_model_links import TYPE, BASIS
    allowed = ((BASIS,) if assertion.get('certificate_type') == TYPE else
               (DIRECT_REVIEW_BASIS,) if assertion.get('certificate_type') == DIRECT_TYPE else (REVIEW_BASIS, AGENT_REVIEW_BASIS))
    if basis not in allowed:
        raise ValueError('unknown review basis; use the fixed label for the certificate type')
    return basis


def witness_record(page_key, assertion):
    editorial = assertion['editorial']
    observed = assertion['print_observation']
    component_key = ('cross_reference_component_sha256' if assertion.get('evidence_kind') == 'cross_reference_only'
                     else 'definition_component_sha256')
    location = (dict(heading_item_sha256=assertion['heading_item_sha256'])
                if assertion.get('certificate_type') in (DIRECT_TYPE, 'model-source-verified-v1') else dict(anchor_sha256=assertion['anchor_sha256']))
    return dict(source_url=editorial['source_url'], html_sha256=assertion['html_sha256'],
        headword=editorial['headword'], homonym=editorial['homonym'], page=page_key,
        printed_heading=observed['heading'], printed_homonym=observed['homonym'],
        evidence=dict(certificate=assertion, **location,
            **{component_key: assertion[component_key]}), review_basis=review_basis(assertion))


def validate_cross_reference(assertion, body):
    """A separately headed reference article, never an embedded reference.

    Exact component/target bindings supplement (and do not replace) the common
    image, article-boundary, candidate-anchor, homonym and page gates.
    """
    if 'review_basis' not in assertion:
        raise ValueError('cross-reference review provenance must be explicit')
    allowed = {'headword', 'source_division', 'cross_reference', 'tibetan'}
    components = body['components']
    refs = [c for c in components if c['type'] == 'cross_reference']
    if (len(refs) != 1 or any(c['type'] not in allowed for c in components) or
        any(c['type'] == 'source_division' and c['source_form'].strip() for c in components)):
        raise ValueError('not a cross-reference-only HTML article')
    reference = refs[0]['source_form'].strip()
    if len(reference) < 2 or reference[0] not in '↑↓' or not proof_key(reference[1:]):
        raise ValueError('explicit cross-reference arrow and target required')
    if (assertion.get('cross_reference_evidence') != reference or
        assertion.get('cross_reference_component_sha256') != object_digest(refs[0]) or
        assertion.get('print_observation', {}).get('cross_reference') != reference):
        raise ValueError('cross-reference target or component differs from inspected evidence')
    if assertion.get('print_observation', {}).get('heading') != body['headword']['loc']:
        raise ValueError('cross-reference article requires the independently observed exact heading')
    variants = [c for c in components if c['type'] == 'tibetan']
    observed = assertion.get('print_observation', {})
    if variants:
        if (len(variants) != 1 or assertion.get('variant_component_sha256') != object_digest(variants[0]) or
            observed.get('heading_variant') != variants[0]['source_form'].strip()):
            raise ValueError('cross-reference heading variant requires exact source binding')
    elif 'variant_component_sha256' in assertion or 'heading_variant' in observed:
        raise ValueError('unexpected cross-reference heading variant')
    return refs[0]


def validate_boundary(assertion, anchor, qa_rows):
    """Validate source bindings of a visual article-boundary adjudication.

    QA headword_line includes running headers and is not an article classifier.
    Selected lines may be noncontiguous because QA reading order interleaves columns.
    """
    boundary = assertion['article_boundary']
    heading, evidence = boundary['heading_lines'], boundary['evidence_lines']
    if (boundary.get('classification') != 'reviewed lexical article start' or
        not heading or not evidence or anchor['start_line'] != min(heading) or
        set(heading + evidence) & set(boundary['excluded_lines'])):
        raise ValueError('anchor is not the reviewed article beginning')
    selected = sorted(set(heading + evidence))
    rows = [qa_rows[(anchor['volume'], anchor['start_page'], line)] for line in selected]
    if boundary['qa_rows_sha256'] != object_digest(rows):
        raise ValueError('stale article-boundary QA evidence')
    if not boundary.get('review_reason'):
        raise ValueError('manual article-boundary adjudication required')


def page_binding(page):
    return {k: page[k] for k in ('source', 'source_sha256', 'physical_page', 'volume', 'printed_page', 'side', 'crop')}


def validate_direct(assertion, body, page, anchors, edges, decisions):
    """Separate source-reviewed pathway. Never synthesizes historical OCR evidence.

    Geometry and hashes make the visual claim reproducible, not machine-proven.
    Inventory review and an explicit acceptance remain mandatory.
    """
    review_basis(assertion)
    if any(k in assertion for k in ('anchor', 'anchor_sha256', 'candidate_anchor_correction')):
        raise ValueError('direct certificate must not manufacture a historical anchor')
    inventory = page.get('source_heading_inventory', {})
    if (inventory.get('version') != 1 or inventory.get('page_sha256') != object_digest(page_binding(page))
        or inventory.get('review_basis') != DIRECT_REVIEW_BASIS or not inventory.get('reviewer')):
        raise ValueError('source-bound reviewed heading inventory required')
    items = inventory.get('items', []) + inventory.get('exclusions', [])
    ids = [i['item_id'] for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate source heading inventory ID')
    accepted_locations = [tuple(i.get('heading_bbox', [])) for i in inventory.get('items', [])
                          if i.get('status') == 'accepted']
    if len(accepted_locations) != len(set(accepted_locations)):
        raise ValueError('duplicate accepted source heading location')
    matches = [i for i in inventory.get('items', []) if i['item_id'] == assertion.get('heading_id')]
    if len(matches) != 1:
        raise ValueError('direct heading not in reviewed article inventory')
    item = matches[0]
    if assertion.get('heading_item_sha256') != object_digest(item):
        raise ValueError('stale reviewed heading inventory item')
    if (item.get('classification') != 'independent article start' or item.get('status') != 'accepted'
        or item.get('source_id') != body['inspection_id']):
        raise ValueError('heading is not an accepted independent article for this HTML identity')
    review = assertion.get('source_review', {})
    if (review.get('decision') != 'accept' or review.get('reviewer') != inventory['reviewer']
        or not review.get('reason')):
        raise ValueError('explicit source-review acceptance required')
    def contains(outer, inner):
        import math
        return (len(inner) == 4 and all(isinstance(x, (int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in inner)
                and outer[0] <= inner[0] < inner[2] <= outer[2]
                and outer[1] <= inner[1] < inner[3] <= outer[3])
    if (item.get('coordinate_system') != 'PDF points; bottom-left origin'
        or not contains(page['crop'], item.get('article_bbox', []))
        or not contains(item['article_bbox'], item.get('heading_bbox', []))
        or not contains(item['article_bbox'], item.get('evidence_bbox', []))):
        raise ValueError('invalid precise source heading/evidence location')
    for field in ('heading', 'printed_evidence', 'preceding', 'following', 'boundary_reason', 'homonym_review', 'identity_reason'):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise ValueError('independent source observation required: '+field)
    if (body['source_kind'] != 'html' or assertion['source_id'] != body['inspection_id']
        or assertion['editorial'] != dict(source_url=body['source_url'], headword=body['headword']['loc'], homonym=body['homonym'])
        or assertion['html_sha256'] != body['sources'][0]['sha256']):
        raise ValueError('stale exact acquired HTML identity')
    if 'printed_homonym' not in item or assertion.get('printed_homonym') != item['printed_homonym']:
        raise ValueError('explicit printed homonym observation required')
    if item['printed_homonym'] is not None and str(item['printed_homonym']) != str(body['homonym']):
        raise ValueError('competing numbered homonym')
    observation = assertion.get('print_observation', {})
    expected_observation = dict(heading=item['heading'], homonym=item['printed_homonym'],
                           evidence=item['printed_evidence'], identity_context=item['identity_reason'],
                           page_sha256=inventory['page_sha256'], verification='visual transcription; not machine-verified')
    if assertion.get('evidence_kind') == 'cross_reference_only':
        for field in ('cross_reference', 'heading_variant'):
            if field in item:
                expected_observation[field] = item[field]
    if observation != expected_observation:
        raise ValueError('direct printed observation differs from reviewed inventory')
    historical = assertion.get('historical_evidence', {})
    actual_edges = [e for e in edges if e['source_id'] == assertion['source_id']]
    actual_anchors = [anchors[k] for k in sorted({e['local_anchor_id'] for e in actual_edges} & set(anchors))]
    if (historical.get('edges_sha256') != object_digest(actual_edges)
        or historical.get('anchors_sha256') != object_digest(actual_anchors)
        or historical.get('issue') not in ('missing_heading', 'missing_identity_edge', 'defective_association')
        or not historical.get('reason')):
        raise ValueError('historical evidence absence/defect must be recorded and bound')
    prior = [d for d in decisions if d['source_id'] == assertion['source_id']]
    reconsider = assertion.get('reconsideration', {})
    if prior and (reconsider.get('decision_sha256s') != [object_digest(d) for d in prior] or not reconsider.get('reason')):
        raise ValueError('all earlier decisions require explicit source-bound reconsideration')
    if assertion.get('evidence_kind', 'definition') == 'cross_reference_only':
        # Preserve the existing strict reference controls, with the independently
        # observed heading supplied by the reviewed inventory.
        return validate_cross_reference(assertion, body)
    if assertion.get('evidence_kind', 'definition') != 'definition':
        raise ValueError('unknown direct article evidence kind')
    quote = assertion.get('definition_evidence', '')
    components = [c for c in body['components'] if c['type'] == 'definition'
                  and proof_key(quote) and proof_key(quote) in proof_key(c['source_form'])]
    if not components or assertion.get('definition_component_sha256') != object_digest(components[0]):
        raise ValueError('direct lexical evidence is not bound to this HTML definition')
    if not assertion.get('lexical_agreement_reason'):
        raise ValueError('printed/HTML lexical agreement must be reviewed explicitly')
    return components[0]


def validate_assertion(assertion, body, anchor, edges):
    review_basis(assertion)
    if body['source_kind'] != 'html' or assertion['source_id'] != body['inspection_id']:
        raise ValueError('not an exact HTML witness')
    if assertion['anchor'] != anchor['anchor_id']:
        raise ValueError('assertion has no pinned candidate edge')
    candidates = [e for e in edges if e['source_id'] == assertion['source_id']]
    if not any(e['local_anchor_id'] == assertion['anchor'] for e in candidates):
        correction = assertion.get('candidate_anchor_correction', {})
        old = [e for e in candidates if e['local_anchor_id'] == correction.get('previous_anchor')]
        if (len(old) != 1 or object_digest(old[0]) != correction.get('previous_edge_sha256') or
            not correction.get('reason')):
            raise ValueError('assertion has no pinned candidate edge or reviewed anchor correction')
    if assertion['editorial'] != dict(source_url=body['source_url'], headword=body['headword']['loc'], homonym=body['homonym']):
        raise ValueError('stale editorial identity')
    if assertion.get('heading_position') not in ('left column', 'right column'):
        raise ValueError('a running header or continuation is not a heading position')
    if 'printed_homonym' not in assertion:
        raise ValueError('printed homonym must be explicit, including absence')
    if assertion['html_sha256'] != body['sources'][0]['sha256'] or assertion['anchor_sha256'] != object_digest(anchor):
        raise ValueError('stale reviewed source evidence')
    printed = assertion['printed_homonym']
    if printed is not None and str(printed) != str(body.get('homonym')):
        raise ValueError('competing numbered homonym')
    kind = assertion.get('evidence_kind', 'definition')
    if kind == 'cross_reference_only':
        component = validate_cross_reference(assertion, body)
    elif kind == 'definition':
        quote = assertion['definition_evidence']
        if not proof_key(quote):
            raise ValueError('empty HTML evidence')
        components = [c for c in body['components'] if c['type'] == 'definition' and proof_key(quote) in proof_key(c['source_form'])]
        if not components:
            raise ValueError('reviewed definition not present in this HTML witness')
        if assertion['definition_component_sha256'] != object_digest(components[0]):
            raise ValueError('stale definition evidence')
        component = components[0]
    else:
        raise ValueError('unknown article evidence kind')
    if not assertion.get('scan_review'):
        raise ValueError('scan identity review required, especially for unnumbered print')
    observation = assertion.get('print_observation', {})
    # These are reviewer transcriptions, NOT an OCR verification of printed wording.
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
    return component


def compile_records(certificate, bodies, anchors, edges, registry, qa_rows=None):
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
            if str(assertion.get('status', '')).startswith('draft'):
                raise ValueError('draft preparation has no attachment authority')
            sid = assertion['source_id']
            if sid in seen:
                raise ValueError('witness assigned twice')
            seen.add(sid)
            if assertion.get('certificate_type') == 'model-source-verified-v1':
                from certify_badw_model_links import validate_model
                validate_model(assertion, bodies[sid], page, (certificate,bodies,anchors,edges,registry,qa_rows))
                location = (page['source'], page['physical_page'], assertion['heading_id'])
                if assertion.get('policy') == 'independent-source-lexical-reference-v2':
                    location += (assertion['page_observations']['image']['sha256'],)
                if location in used_anchors:
                    raise ValueError('model heading assigned twice')
                used_anchors[location] = assertion
                witnesses.append(witness_record(key, assertion))
                continue
            if assertion.get('certificate_type') == DIRECT_TYPE:
                validate_direct(assertion, bodies[sid], page, anchors, edges, certificate.get('decisions', []))
                location = (key, assertion['heading_id'])
                if location in used_anchors:
                    raise ValueError('direct heading assigned twice')
                used_anchors[location] = assertion
                witnesses.append(witness_record(key, assertion))
                continue
            if assertion.get('certificate_type') is not None:
                raise ValueError('unknown certificate type')
            body, anchor = bodies[sid], anchors[assertion['anchor']]
            if anchor['start_page'] != page['physical_page'] or anchor['volume'] != page['family']:
                raise ValueError('physical anchor differs from reviewed page')
            decision = decisions.get((sid, assertion['anchor']))
            if decision:
                reconsideration = assertion.get('reconsideration', {})
                if reconsideration.get('decision_sha256') != object_digest(decision) or not reconsideration.get('reason'):
                    raise ValueError('rejected/deferred decision requires explicit reconsideration')
            component = validate_assertion(assertion, body, anchor, edges)
            if qa_rows is None:
                raise ValueError('source-bound QA records required')
            validate_boundary(assertion, anchor, qa_rows)
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
            witnesses.append(witness_record(key, assertion))
    result = dict(version=2, certificate_sha256=object_digest(certificate), pages=pages, witnesses=witnesses, inputs=certificate.get('inputs', {}))
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
    expected = dict(version=2, certificate_sha256=object_digest(certificate),
        pages=expected_pages, witnesses=[witness_record(key, r) for key, r in assertions], inputs=certificate.get('inputs', {}))
    expected['content_sha256'] = object_digest(expected)
    if expanded != expected:
        raise ValueError('generated witness differs from certificate or unexpected generated fields')


def inventory(bodies, handoff, edges, accepted):
    by_source = collections.defaultdict(list)
    for e in edges:
        by_source[e['source_id']].append(e)
    counts = collections.Counter()
    families = collections.defaultdict(collections.Counter)
    for sid, body in bodies.items():
        es = by_source[sid]
        if (body['source_url'], body['sources'][0]['sha256']) in accepted:
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
    accepted = {(r['source_url'], r['html_sha256']) for r in baseline['witnesses']}
    accepted.update((r['editorial']['source_url'], r['html_sha256']) for p in certificate['pages'] for r in p['accepted'])
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
        if sid not in bodies or aid not in anchors or (bodies[sid]['source_url'], bodies[sid]['sources'][0]['sha256']) in accepted:
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
    qa_rows = {}
    for family in FAMILIES:
        path = ROOT/f'release/current/qa/{family}/{family}_line_zones.tsv'
        for row in csv.DictReader(path.open(), delimiter='\t'):
            qa_rows[family, int(row['page']), int(row['line'])] = row
    generated = compile_records(cert, bodies, anchors, edges, registry, qa_rows)
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
        accepted = {(r['source_url'], r['html_sha256']) for r in baseline['witnesses']+generated['witnesses']}
        args.inventory.write_text(json.dumps(inventory(bodies, handoff, edges, accepted), ensure_ascii=False, indent=2)+'\n')
    if args.queue:
        baseline = json.loads((ROOT/'data/badw_html_print_pages.json').read_text())
        args.queue.write_text(json.dumps(review_queue(cert, baseline, bodies, anchors, edges), ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(witnesses=len(generated['witnesses']), pages=len(generated['pages']))))


if __name__ == '__main__':
    main()
