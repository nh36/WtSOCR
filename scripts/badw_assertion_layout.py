"""Derived physical geometry for passage validation over immutable PDF runs.

Old observations used unscaled Td/TD moves. Re-decode the exact cached PDF,
require identical run indices, CIDs, fonts and Unicode, and use only the new
coordinates. Neither source text nor observation geometry is rewritten.
"""
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT / 'work/badw_verified_rebuild_20261003/canonical_v2'
CACHE = ROOT / 'work/badw_source_cache/objects/sha256'


@lru_cache(maxsize=64)
def decoded_pdf(digest, url):
    from badw_pdf_decoder import decode_pdf_bytes
    body = (CACHE / digest[:2] / digest).read_bytes()
    if hashlib.sha256(body).hexdigest() != digest:
        raise ValueError('assertion layout PDF hash mismatch')
    return decode_pdf_bytes(body, canonical_url=url, catalogue_lemma='')


@lru_cache(maxsize=128)
def page_runs(canonical, canonical_digest, digest, url):
    body = (CANON / canonical).read_bytes()
    if hashlib.sha256(body).hexdigest() != canonical_digest:
        raise ValueError('assertion layout canonical hash mismatch')
    original = json.loads(gzip.decompress(body))
    page = original['representative_source']['pdf_page_index']
    decoded = decoded_pdf(digest, url)
    old = original['positioned_page']['positioned_text_runs']
    new = decoded['pages'][page-1]['positioned_text_runs']
    fields = ('run_index', 'operation_index', 'font_id', 'decoded_unicode')
    if len(old) != len(new) or any(any(a[k] != b[k] for k in fields) or tuple(a['source_cids']) != tuple(b['source_cids']) for a,b in zip(old,new)):
        return None
    return new


def physical_lines(projection):
    """Return derived line boxes, or no evidence if exact replay is unavailable."""
    sources = {s['page_id']: s for s in projection.get('source', {}).get('source_objects', [])}
    result = []
    for line in projection['original_structure'].get('visual_lines', []):
        source = sources.get(line.get('page_id'))
        if not source:
            return []
        runs = page_runs(source['canonical_object'], source['canonical_object_sha256'],
                         source['pdf_sha256'], source['pdf_url'])
        if runs is None:
            return []
        glyphs = [g for run in runs[line['run_start']:line['run_end_exclusive']] for g in run['glyphs']]
        if not glyphs:
            return []
        result.append(dict(page_id=line['page_id'], printed_page=line.get('printed_page'),
            x=min(g['x'] for g in glyphs), right=max(g['x']+g['advance'] for g in glyphs),
            y= glyphs[0]['y'], bottom=min(g['y'] for g in glyphs), top=max(g['y'] for g in glyphs),
            pdf_sha256=source['pdf_sha256'], run_start=line['run_start'],
            run_end_exclusive=line['run_end_exclusive']))
    return result


def continuous(lines, left, right):
    if left == right:
        return bool(lines)
    if right != left+1 or right >= len(lines):
        return False
    a,b = lines[left], lines[right]
    if (a['page_id'],a['printed_page']) != (b['page_id'],b['printed_page']):
        return False
    # WTS has two columns separated at x=300 PDF points. No crossing allowed.
    if int(a['x'] >= 300) != int(b['x'] >= 300):
        return False
    dy = a['y']-b['y']
    # Font changes split one physical baseline into multiple observation lines.
    if abs(dy) <= .5:
        return a['x'] <= b['x'] <= a['right']+5
    # Ordinary body leading is 14–16 points. Superscript-only observations are
    # not silently folded into a paragraph; those need their own production.
    return 8 <= dy <= 18 and abs(a['x']-b['x']) <= 220


def passage_layout(projection, spans):
    """Exact replay geometry and consecutive line evidence for one passage."""
    if not spans:
        return None
    lines = physical_lines(projection)
    indices = sorted({s['line'] for s in spans})
    if not lines or any(not continuous(lines,a,b) for a,b in zip(indices,indices[1:])):
        return None
    return [dict(line_index=i, **lines[i]) for i in indices]
