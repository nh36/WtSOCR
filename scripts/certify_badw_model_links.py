"""Certify cached source readings under a bounded, explicitly model-reviewed policy.

Offline: no API client or spending action. Publication uses the ordinary compiler.
The initial pool is frozen independently of subsequent acceptance/rejection results.
"""
import argparse
from collections import Counter, defaultdict
import copy
from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import json
import re
from pathlib import Path

import badw_html_print_alignment as a

TYPE = 'model-source-verified-v1'
BASIS = ('Model source-image reading and independent blind source verification; '
         'no human or coding-agent per-article adjudication. Deterministic compiler '
         'checks cached observations, exact HTML identity, lexical evidence and original-page geometry.')
POLICY = 'unique-unnumbered-lexical-v1'
FRESH_POLICY = 'independent-source-lexical-reference-v2'
CONTROLS = a.ROOT/'data/badw_model_certification_controls.json'
# Closed benign observations, separate from unresolved interpretation. Unknown
# wording abstains; an absence of a numeral never becomes an inferred numeral 1.
BENIGN = {a.proof_key(x) for x in ('', 'None', 'None material',
    'None material to the match', 'No printed homonym numeral visible',
    'No numeral visible', 'No printed homonym numeral', 'No homonym numeral visible',
    'No printed homonym number', 'No printed numeral visible')}
LEXICAL = {'definition', 'example', 'lexical_parallel', 'translation', 'citation'}
_VERIFIED_SOURCES = set()


def readings(row):
    other = row.get('second_reading') or {}
    return [row['heading']] + other.get('inventory', []), [row['first_matching']] + other.get('matching', [])


def policy_reason(row, body, headword_count, fresh=False):
    """Semantic model judgments plus independent deterministic exclusions.

    A length threshold is only a minimum corroborating quotation, never a
    substitute for the two lexical/identity/boundary readings retained in full.
    """
    hs, ms = readings(row)
    if row.get('previous_decisions'):
        return 'prior decision'
    if row.get('state') != 'model-source-reviewed' or len(hs) != 2 or len(ms) != 2:
        return 'independent source verification missing or disputed'
    if body['source_kind'] != 'html' or row['source_id'] != body['inspection_id'] or row['source_url'] != body['source_url'] or row['html_sha256'] != body['sources'][0]['sha256']:
        return 'exact HTML identity'
    key = a.proof_key(body['headword']['loc'])
    def heading_identity(h):
        if a.proof_key(h['heading_loc']) == key:
            return True
        # Some inventories interpret “loc” as location. Preserve that response,
        # and require its independently transcribed Tibetan heading to match
        # the exact acquired headword instead. A different lexical reading is
        # never excused by this narrowly recognised layout description.
        location = re.fullmatch(r'(?:left|right) column, .+', h.get('heading_loc') or '', re.I)
        tibetan = body['headword'].get('tibetan')
        return bool(fresh and location and tibetan and
                    a.proof_key(h.get('heading_tibetan') or '') == a.proof_key(tibetan))
    if any(h['classification'] != 'article' or not heading_identity(h) for h in hs):
        return 'independent heading identity'
    numbered = all(h['printed_homonym'] is not None and str(h['printed_homonym']) == str(body['homonym']) for h in hs)
    if (headword_count != 1 or any(h['printed_homonym'] is not None for h in hs)) and not (fresh and numbered):
        return 'numbered or editorially split homonym needs separate policy'
    def benign(x):
        text = a.proof_key(x.get('uncertainty', ''))
        return text in BENIGN or (fresh and numbered and bool(re.fullmatch(r'superscript[1-9][0-9]*isvisiblyprinted', text)))
    if any(not benign(x) for x in hs + ms):
        return 'unresolved source interpretation'
    overlaps = []
    for h, m in zip(hs, ms):
        if not all(h.get(k, '').strip() for k in ('printed_evidence', 'preceding', 'following')):
            return 'article boundary observation missing'
        if m['outcome'] != 'supported' or m['source_id'] != row['source_id']:
            return 'conflicting identity'
        if not all(m.get(k, '').strip() for k in ('boundary_evidence','homonym_evidence','printed_evidence','html_evidence')):
            return 'lexical identity observation missing'
        index = m['component_index']
        if not isinstance(index, int) or not 0 <= index < len(body['components']):
            return 'component index'
        component = body['components'][index]
        quote = a.proof_key(m['html_evidence'])
        if component['type'] not in LEXICAL and not (fresh and component['type'] == 'cross_reference'):
            return 'reference or nonlexical component needs separate policy'
        if not quote or quote not in a.proof_key(component['source_form']):
            return 'exact component quotation'
        if fresh and component['type'] == 'cross_reference':
            if quote != a.proof_key(component['source_form']):
                return 'complete reference component required'
            reference = ' '.join(m['html_evidence'].casefold().split()).rstrip('.')
            target = reference.lstrip('↑↓→ ').strip()
            # Complete target and token boundaries, in BOTH independent printed
            # readings, prevent a short reference being matched by a prefix.
            if len(target) < 4 or not re.fullmatch(r'[↑↓→]\s*[^↑↓→]+', reference):
                return 'reference target not explicit'
            pattern = r'(?<![\w])' + re.escape(target) + r'(?=\s*(?:[.,;:!?…“”"\u0027’)]|$))'
            if not all(re.search(pattern, ' '.join(x['printed_evidence'].casefold().split())) for x in (h,m)):
                return 'independent exact reference target missing'
            overlaps.append(100)
            continue
        observations = (h, m) if fresh else (m,)
        overlaps.append(max(SequenceMatcher(None, a.proof_key(x['printed_evidence']), quote,
                                            autojunk=False).find_longest_match().size for x in observations))
    if (min(overlaps) if fresh else max(overlaps)) < 20:
        return 'insufficient discriminating verbatim evidence'
    if row['component_index'] != row['first_matching']['component_index']:
        return 'component index binding'
    if row['component_sha256'] != a.object_digest(body['components'][row['component_index']]):
        return 'component checksum'
    return None


@lru_cache(maxsize=256)
def source_geometry(campaign, page_key, source_json, image_json, directory_override=None):
    """Re-render the ORIGINAL physical scan; compare exact cached image bytes.

    Crops must occur in the shared original-page map. No pagination extrapolation.
    This rejects an image swapped from another scan even if its own hash is valid.
    """
    import pymupdf as fitz
    source, image = json.loads(source_json), json.loads(image_json)
    directory = Path(directory_override) if directory_override else Path(campaign)/'pages'/page_key
    original = a.ROOT/source['filename']
    if original_digest(str(original)) != source['sha256']:
        raise ValueError('original source checksum')
    pack = json.loads((directory/'pack.json').read_text())
    if (pack['source'] != source['label'] or pack['source_sha256'] != source['sha256']
            or pack['image'] != image or not (page_key == f"{pack['family']}-{pack['physical_page']}" or page_key.startswith(f"{pack['family']}-{pack['physical_page']}-"))):
        raise ValueError('source page binding')
    with fitz.open(original) as pdf:
        n = pack['physical_page']
        if not isinstance(n, int) or not 1 <= n <= len(pdf):
            raise ValueError('physical page range')
        page = pdf[n-1]
        transform = image['transform']; box = list(page.mediabox)
        crop = transform['pdf_crop']
        if crop != box:
            import badw_print_page_map as page_map
            candidates = page_map.load()['pages'].values()
            if not any(p['source_sha256'] == source['sha256'] and p['physical_page'] == n and p['crop'] == crop for p in candidates):
                raise ValueError('unresolved original-page geometry')
        if page.rotation or transform['pdf_to_mupdf'] != list(page.transformation_matrix):
            raise ValueError('unresolved original-page geometry')
        dpi = image['dpi']
        if transform['points_per_pixel'] != [72/dpi,72/dpi]:
            raise ValueError('image scale')
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72), clip=fitz.Rect(crop)*page.transformation_matrix, alpha=False)
        rendered = hashlib.sha256(pix.tobytes('png')).hexdigest()
        if (rendered != image['sha256'] or a.digest(directory/image['path']) != rendered
                or image['pixels'] != [pix.width,pix.height]
                or transform['image_device_origin'] != [pix.x,pix.y]):
            raise ValueError('cached image is not the registered physical scan rendering')
    # MuPDF exposes float32 coordinates. Publication retains the exact PDF
    # numbers, rather than extending a page by float32 rounding (e.g. 893.64).
    exact_box = original_media_box(str(original), n)
    if any(abs(x-y) > max(1e-6, abs(y)*1.2e-7) for x,y in zip(box, exact_box)):
        raise ValueError('PDF engines disagree on original media box')
    return exact_box if crop == box else crop


@lru_cache(maxsize=256)
def original_media_box(path, physical_page):
    from pypdf import PdfReader
    return list(map(float, PdfReader(path).pages[physical_page-1].mediabox))


@lru_cache(maxsize=8)
def original_digest(path):
    return a.digest(path)


def checked_row(row, evidence, resources, campaign):
    """Reconstruct both observations from immutable paid caches; never execute API."""
    import badw_campaign_review as review
    import badw_model_worker as w
    directory = Path(campaign)/'pages'/row['page']
    pack, inv, match = review.load_page(directory, resources, evidence['model'], _VERIFIED_SOURCES)
    spec_path = directory/'cache'/(evidence['second_request_sha256']+'.json')
    cached = w.load(spec_path)
    blind = copy.deepcopy(pack); blind.pop('inventory',None); blind.pop('match_images',None)
    spec = cached['request']
    expected = w.request_spec('source_review', blind, evidence['model'], spec['detail'], spec['max_output_tokens'])
    if expected != spec or cached['request_sha256'] != a.object_digest(spec):
        raise ValueError('independent request source binding')
    if cached.get('status') == 'rejected model response; no evidence authority':
        second = review.recover_review(cached,spec,blind)
    else:
        if cached['result_sha256'] != a.object_digest(cached['result']):
            raise ValueError('independent response checksum')
        w.validate('source_review',cached['result'],blind); second = cached
    if (evidence['inventory_request_sha256'] == evidence['second_request_sha256']
            or evidence['inventory_sha256'] != inv['result_sha256']
            or evidence['match_sha256'] != match['result_sha256']
            or evidence['inventory_request_sha256'] != inv['request_sha256']
            or evidence['match_request_sha256'] != match['request_sha256']
            or evidence['second_observation_sha256'] != second['result_sha256']):
        raise ValueError('source observation bindings')
    packet = review.packet(pack,inv,match,second,resources,directory)
    matches = [r for r in packet['associations'] if r['source_id']==row['source_id'] and r['item_id']==row['item_id']]
    if len(matches) != 1:
        raise ValueError('cached association missing or duplicated')
    actual = matches[0]
    for k in ('state','source_url','html_sha256','component_index','component_sha256','heading','first_matching','pdf_heading_bbox','image_crop','previous_decisions'):
        if actual[k] != row[k]:
            raise ValueError('cached association differs: '+k)
    second_rows = dict(inventory=[h for h in second['result']['inventory']['items'] if h['item_id'] in actual['second_item_ids']],
                       matching=[m for m in second['result']['matching']['matches'] if m['item_id'] in actual['second_item_ids']])
    if second_rows != row['second_reading']:
        raise ValueError('independent source reading differs')
    return pack


def validate_model(assertion, body, page, resources):
    if assertion.get('certificate_type') != TYPE or assertion.get('review_basis') != BASIS or assertion.get('policy') not in (POLICY, FRESH_POLICY):
        raise ValueError('unknown model-review provenance/policy')
    if assertion.get('controls_sha256') != a.digest(CONTROLS):
        raise ValueError('changed empirical controls')
    row, evidence = assertion['model_evidence'], assertion['page_observations']
    frozen = json.loads(CONTROLS.read_text())['candidates']
    fresh = assertion['policy'] == FRESH_POLICY
    if not fresh and row not in frozen:
        raise ValueError('association outside validated production pool')
    count = sum(b['source_kind']=='html' and a.proof_key(b['headword']['loc'])==a.proof_key(body['headword']['loc']) for b in resources[1].values())
    reason = policy_reason(row,body,count,fresh=fresh)
    if reason:
        raise ValueError(reason)
    if any(d.get('source_id')==row['source_id'] or d.get('source_url')==row['source_url'] for d in resources[0].get('decisions',[])):
        raise ValueError('prior decision')
    pack = checked_row(row,evidence,resources,assertion['campaign'])
    source = resources[4][page['source']]
    box = source_geometry(assertion['campaign'],row['page'],json.dumps(source,sort_keys=True),json.dumps(evidence['image'],sort_keys=True))
    if fresh:
        import badw_print_page_map as page_map
        mapped = page_map.load()['pages']
        key = page_map.assign(row,evidence,mapped)
        if any(page[k] != mapped[key][k] for k in a.page_binding(page)):
            raise ValueError('printed page map binding')
        box = page['crop']
    if (page['crop'] != box or (not fresh and page['side'] != 'single') or (not fresh and page['printed_page'] is not None)
            or page['physical_page'] != pack['physical_page'] or page['family'] != pack['family']
            or page['source_sha256'] != pack['source_sha256'] or evidence['image'] != pack['image']):
        raise ValueError('whole physical scan geometry binding')
    import badw_model_worker as w
    for heading in readings(row)[0]:
        bounds = heading['bbox']; width,height=evidence['image']['pixels']
        if not (0 <= bounds[0] < bounds[2] <= width and 0 <= bounds[1] < bounds[3] <= height):
            raise ValueError('heading outside source image')
        pdfbox=w.image_to_pdf(bounds,evidence['image']['transform'])
        if not (box[0] <= pdfbox[0] < pdfbox[2] <= box[2] and box[1] <= pdfbox[1] < pdfbox[3] <= box[3]):
            raise ValueError('heading outside original physical scan')
    expected = make_assertion(row,evidence,body,page,assertion['campaign'],fresh=fresh)
    if assertion != expected:
        raise ValueError('model certificate projection differs from source evidence')


def make_assertion(row,evidence,body,page,campaign,fresh=False):
    m=row['first_matching']; heading=row['heading']
    return dict(certificate_type=TYPE,policy=FRESH_POLICY if fresh else POLICY,review_basis=BASIS,controls_sha256=a.digest(CONTROLS),
        source_id=row['source_id'],html_sha256=row['html_sha256'],printed_homonym=heading['printed_homonym'],
        editorial=dict(source_url=body['source_url'],headword=body['headword']['loc'],homonym=body['homonym']),
        heading_id=heading['item_id'],heading_item_sha256=a.object_digest(heading),
        definition_component_sha256=row['component_sha256'],
        print_observation=dict(heading=heading['heading_loc'],homonym=heading['printed_homonym'],
            evidence=m['printed_evidence'],identity_context=m['boundary_evidence'],
            page_sha256=a.object_digest(a.page_binding(page)),verification='model source verified; not human reviewed'),
        model_evidence=copy.deepcopy(row),page_observations=copy.deepcopy(evidence),campaign=campaign)


def competing_assignments(rows, evidence, mapped):
    """Compare source geometry, not cache aliases for the same physical page."""
    import badw_print_page_map as page_map
    physical=defaultdict(set); sides=defaultdict(set)
    for row in rows:
        page=evidence[row['page']]; url=row['source_url']
        physical[url].add((page['source_sha256'],page['physical_page']))
        try:
            sides[url].add(page_map.assign(row,page,mapped))
        except (KeyError,ValueError):
            pass  # This row still must pass its own geometry check to certify.
    return {url for url in physical if len(physical[url])>1 or len(sides[url])>1}


def certify(campaign, bodies_path, output, fresh=False, stage=False):
    import time
    import badw_model_worker as w
    import badw_provisional_print_links as provisional
    campaign = Path(campaign).resolve().relative_to(a.ROOT)
    started=time.monotonic(); output=w.private(output); output.mkdir(parents=True,exist_ok=True)
    resources=w.authoritative(bodies_path); certificate=copy.deepcopy(resources[0])
    dataset=provisional.export(campaign,output/'rebound-cache.json')
    frozen=w.load(CONTROLS); pool={r['source_id'] for r in frozen['candidates']}
    if fresh:
        pool={r['source_id'] for r in dataset['witnesses']+dataset['review_queue']}
    import badw_print_page_map as page_map
    mapped=page_map.load()['pages']
    bodies=resources[1]; counts=Counter(a.proof_key(b['headword']['loc']) for b in bodies.values() if b['source_kind']=='html')
    existing={r['source_id'] for p in certificate['pages'] for r in p['accepted']}
    pages={p['key']:p for p in certificate['pages']}; outcomes=[]
    allrows=dataset['witnesses']+dataset['review_queue']
    conflicts=competing_assignments(allrows,dataset['pages'],mapped)
    for row in allrows:
        if row['source_id'] not in pool or row['source_id'] in existing: continue
        body=bodies[row['source_id']]; reason=policy_reason(row,body,counts[a.proof_key(body['headword']['loc'])],fresh=fresh)
        if row['source_url'] in conflicts: reason='competing physical pages or printed sides'
        if reason:
            outcomes.append(dict(source_id=row['source_id'],result='unresolved',reason=reason)); continue
        evidence=dataset['pages'][row['page']]; source=resources[4][evidence['source']]
        key='model-physical-'+row['page']; family={v:k for k,v in a.FAMILIES.items()}[evidence['source']]
        try:
            box=source_geometry(str(campaign),row['page'],json.dumps(source,sort_keys=True),json.dumps(evidence['image'],sort_keys=True))
            page=pages.get(key) or dict(key=key,family=family,source=evidence['source'],source_sha256=evidence['source_sha256'],
                physical_page=evidence['physical_page'],volume={'wts_1_34':'1–7','wts_35_51':'3–7','wts_8_b':8,'wts_9_m':9}[family],
                printed_page=None,side='single',crop=box,
                geometry_review='Deterministic original PDF media box and exact source rendering verified; whole physical scan, no folio/side inference.',
                page_evidence='Registered source checksum and physical page; independently read headings; no asserted printed folio.',accepted=[])
            if fresh:
                key=page_map.assign(row,evidence,mapped)
                page=pages.get(key) or dict(copy.deepcopy(mapped[key]),accepted=[])
            assertion=make_assertion(row,evidence,body,page,str(campaign),fresh=fresh)
            validate_model(assertion,body,page,resources)
        except (ValueError,KeyError) as exc:
            outcomes.append(dict(source_id=row['source_id'],result='unresolved',reason=str(exc)));continue
        if key not in pages: certificate['pages'].append(page); pages[key]=page
        page['accepted'].append(assertion); existing.add(row['source_id'])
        outcomes.append(dict(source_id=row['source_id'],result='certified',page=key))
    # Validate entire canonical ledger before changing either public artifact.
    expanded=a.compile_records(certificate,bodies,resources[2],resources[3],resources[4],resources[5])
    a.validate_expansion(certificate,expanded)
    summary=dict(Counter(r['result'] for r in outcomes))
    summary['already_certified']=len(pool & {r['source_id'] for p in resources[0]['pages'] for r in p['accepted']})
    w.write(output/'outcomes.json',dict(outcomes=outcomes,summary=summary,
        elapsed_seconds=round(time.monotonic()-started,2),new_api_cost_usd=0))
    if stage:
        w.write(output/'certificate.json',certificate); w.write(output/'generated.json',expanded)
        return summary
    w.write(a.CERTIFICATE,certificate);w.write(a.GENERATED,expanded)
    baseline=w.load(a.ROOT/'data/badw_html_print_pages.json')
    w.write(a.ROOT/'data/badw_html_print_review_queue.json',
        a.review_queue(certificate,baseline,bodies,resources[2],resources[3]))
    # Preserve unresolved suggestions without increasing their count or leaving stale bindings.
    prior=w.load(provisional.DATA); urls={r['source_url'] for r in expanded['witnesses']}
    prior['witnesses']=[r for r in prior['witnesses'] if r['source_url'] not in urls]
    prior['certified_ledger_sha256']=a.digest(a.GENERATED)
    prior['summary']['published_provisional']=len(prior['witnesses'])
    w.write(provisional.DATA,prior)
    print(json.dumps(w.load(output/'outcomes.json')['summary']),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--bodies',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();certify(args.campaign,args.bodies,args.output)

if __name__=='__main__': main()
