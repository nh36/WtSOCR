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
    if len(proof_key(quote)) < 8:
        raise ValueError('insufficient distinguishing definition')
    components = [c for c in body['components'] if c['type'] == 'definition' and proof_key(quote) in proof_key(c['source_form'])]
    if not components:
        raise ValueError('reviewed definition not present in this HTML witness')
    if assertion['definition_component_sha256'] != object_digest(components[0]):
        raise ValueError('stale definition evidence')
    if not assertion.get('scan_review'):
        raise ValueError('scan identity review required, especially for unnumbered print')
    return components[0]


def compile_records(certificate, bodies, anchors, edges, registry):
    """Pure deterministic expansion. Every emitted witness has an explicit certificate."""
    pages, witnesses, seen = {}, [], set()
    for page in certificate['pages']:
        key = page['key']
        if key in pages:
            raise ValueError('duplicate printed page')
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
            component = validate_assertion(assertion, body, anchor, edges)
            witnesses.append(dict(source_url=body['source_url'], html_sha256=body['sources'][0]['sha256'],
                headword=body['headword']['loc'], homonym=body['homonym'], page=key,
                printed_heading=body['headword']['loc'],
                evidence=dict(certificate=assertion, anchor_sha256=object_digest(anchor),
                    definition_component_sha256=object_digest(component)),
                review_basis='Page-driven visual heading and distinguishing definition; candidate edge only supplies the locator.'))
    return dict(version=1, certificate_sha256=object_digest(certificate), pages=pages, witnesses=witnesses)


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--bodies', type=Path, help='Private JSON map of current HTML reader bodies by inspection_id')
    inputs.add_argument('--reader', type=Path, help='Existing reader whose HTML bodies supply the acquired source evidence')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--inventory', type=Path)
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
    print(json.dumps(dict(witnesses=len(generated['witnesses']), pages=len(generated['pages']))))


if __name__ == '__main__':
    main()
