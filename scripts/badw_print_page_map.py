"""Shared checksum-bound printed-page geometry and certificate destinations."""
import copy
import json
from pathlib import Path
import badw_html_print_alignment as a

PATH = a.ROOT/'data/badw_print_page_map.json'


def load():
    result = json.loads(PATH.read_text()) if PATH.exists() else dict(version=1, pages={}, destinations={})
    families = {v:k for k,v in a.FAMILIES.items()}
    for key, page in result['pages'].items():
        page.setdefault('key', key)
        page.setdefault('family', families[page['source']])
    return result


def assign(row, evidence, pages):
    from badw_model_worker import image_to_pdf
    from certify_badw_model_links import readings
    boxes = [image_to_pdf(h['bbox'], evidence['image']['transform']) for h in readings(row)[0]]
    matches = []
    for key, page in pages.items():
        c = page['crop']
        if (page['source_sha256'] == evidence['source_sha256'] and page['physical_page'] == evidence['physical_page']
            and all(c[0] <= b[0] < b[2] <= c[2] and c[1] <= b[1] < b[3] <= c[3] for b in boxes)):
            matches.append(key)
    # Overlapping historical crops never authorize an arbitrary destination.
    geometry = {(tuple(pages[k]['crop']), pages[k]['source_sha256']) for k in matches}
    if len(geometry) != 1:
        raise ValueError('printed side unresolved or independent coordinates disagree')
    return sorted(matches)[0]


def project(reviewed):
    data = load(); result = copy.deepcopy(reviewed)
    for witness in result['witnesses']:
        destination = data['destinations'].get(witness['source_url'])
        if not destination:
            continue
        original = result['pages'][witness['page']]
        page = data['pages'][destination['page']]
        if (original['source_sha256'], original['physical_page']) != (page['source_sha256'], page['physical_page']):
            raise ValueError('printed destination changed original scan')
        # Bind the redirect to the original, unchanged certificate evidence.
        if a.object_digest(witness) != destination['witness_sha256']:
            raise ValueError('printed destination evidence changed')
        result['pages'][destination['page']] = page
        witness['page'] = destination['page']
    used = {r['page'] for r in result['witnesses']}
    result['pages'] = {k:v for k,v in result['pages'].items() if k in used}
    return result
