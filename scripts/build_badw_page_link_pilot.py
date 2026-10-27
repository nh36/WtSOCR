"""Bounded page-first review pack; never grants source-attachment authority.

Uses existing proposals and reviewed derivatives, not a new matching engine.
Run locally; neither the report nor its PDF derivatives is a public edition.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
from pathlib import Path
import random
import re
import shutil
from urllib.parse import urlsplit

FAMILIES = {'wts_1_34': 'WtS_1-34', 'wts_35_51': 'WtS_35-51',
            'wts_8_b': 'WtS_8-b', 'wts_9_m': 'WtS_9-m'}

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def safe_url(value):
    url = urlsplit(value)
    if (url.scheme != 'https' or url.netloc != 'wts-digital.badw.de'
            or url.username or not url.path.startswith('/lemma/')):
        raise ValueError('unexpected editorial source URL')
    return value


def select(stream, manifest):
    accepted = {(w['source_url'], w['html_sha256']) for w in manifest['witnesses']}
    pages = manifest['pages']
    selected = []
    seen = set()
    for line in stream:
        row = json.loads(line)
        if (row['source_url'], row['html_sha256']) in accepted:
            continue
        proposals = row.get('proposed', [])
        if not proposals or not proposals[0].get('reviewed_page_geometry'):
            continue
        top = proposals[0]
        keys = []
        for geometry in top['reviewed_page_geometry']:
            key = geometry['key']
            page = pages[key]
            for field in ('source', 'source_sha256', 'physical_page', 'crop', 'side',
                          'volume', 'printed_page'):
                if geometry[field] != page[field]:
                    raise ValueError('proposal geometry differs from reviewed manifest')
            if page['physical_page'] != top['physical_page']:
                raise ValueError('proposal physical page mismatch')
            if FAMILIES.get(top['family']) != page['source']:
                raise ValueError('proposal source family mismatch')
            keys.append(key)
        if row['source_id'] in seen:
            raise ValueError('duplicate witness identity')
        seen.add(row['source_id'])
        selected.append(dict(
            source_id=row['source_id'], source_url=safe_url(row['source_url']),
            html_sha256=row['html_sha256'], input_identity=row['input_identity'],
            headword=row['editorial_headword'], homonym=row['editorial_homonym'],
            definition=row['editorial_definition'], citations=row['editorial_citations'],
            family=top['family'], physical_page=top['physical_page'], page_keys=sorted(keys),
            anchor=top['anchor'], line=top['line'], printed_heading=top['heading_text'],
            printed_evidence=top['printed_evidence'], evidence_lines=top['evidence_lines'],
            risks=top['risks'], definition_evidence=top['definition_evidence'],
            alternatives=[{k: p.get(k) for k in ('anchor', 'heading_text', 'score')}
                          for p in proposals[1:4]],
            decision='pending', eligible_for_original_print_link=False))
    return sorted(selected, key=lambda r: (r['family'], r['physical_page'], r['line'], r['source_id']))


def build(proposals, facsimiles, output, seed=20261027):
    proposals, facsimiles, output = map(Path, (proposals, facsimiles, output))
    manifest = json.loads(facsimiles.read_text())
    with proposals.open() as stream:
        rows = select(stream, manifest)
    if output.exists() or output.is_symlink():
        raise ValueError('use a fresh output directory; never reuse a served tree')
    if any(parent.is_symlink() for parent in output.parents):
        raise ValueError('output must not traverse symlinks')
    used = sorted({key for row in rows for key in row['page_keys']})
    public_pages = {}
    for key in used:
        page = manifest['pages'][key]
        filename = page['filename']
        if not re.fullmatch(r'[0-9a-f]{64}\.pdf', filename):
            raise ValueError('unsafe derivative filename')
        source = facsimiles.parent/filename
        if source.is_symlink() or digest(source) != page['sha256']:
            raise ValueError('unsafe or changed derivative')
        public_pages[key] = {k: page[k] for k in (
            'source', 'source_sha256', 'physical_page', 'volume', 'printed_page',
            'side', 'crop', 'sha256', 'filename')}
    output.mkdir(parents=True)
    (output/'pages').mkdir()
    for page in public_pages.values():
        shutil.copyfile(facsimiles.parent/page['filename'], output/'pages'/page['filename'])
    rng = random.Random(seed)
    assessment = sorted(rng.sample([r['source_id'] for r in rows], min(40, len(rows))))
    report = dict(version=1, policy='local research only; all candidates pending source review',
                  proposals_sha256=digest(proposals), facsimiles_sha256=digest(facsimiles),
                  seed=seed, assessment_sample=assessment, pages=public_pages, candidates=rows,
                  counts=dict(witnesses=len(rows), physical_pages=len({(r['family'], r['physical_page']) for r in rows}),
                              derivatives=len({p['filename'] for p in public_pages.values()}),
                              families=dict(Counter(r['family'] for r in rows))))
    (output/'pilot.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    groups = defaultdict(list)
    for row in rows:
        groups[(row['family'], row['physical_page'])].append(row)
    esc = lambda value: html.escape(str(value))
    parts = ['<!doctype html><meta charset="utf-8"><title>Page-first linking pilot</title>',
             '<style>body{max-width:1100px;margin:auto;font:18px Georgia}article{border-top:1px solid;padding:1em}iframe{width:100%;height:850px}pre{white-space:pre-wrap}a{color:#145}</style>',
             '<h1>Page-first linking pilot</h1><p>Local research only. Machine proposals are not accepted source identities. Printed OCR below is unreviewed. All attachment eligibility remains false.</p>']
    for (family, physical), candidates in groups.items():
        parts.append(f'<section><h2>{esc(family)} — physical PDF page {physical}</h2>')
        for key in sorted({k for r in candidates for k in r['page_keys']}):
            p = public_pages[key]
            url = 'pages/'+p['filename']
            parts.append(f'<p>Volume {p["volume"]}, printed page {p["printed_page"]}, {esc(p["side"])}: <a href="{url}">single-page PDF</a></p><iframe title="{esc(key)}" loading="lazy" src="{url}#view=FitH"></iframe>')
        for row in candidates:
            headword = ' / '.join(v for v in row['headword'].values() if v) if isinstance(row['headword'], dict) else row['headword']
            parts.append(f'<article id="{hashlib.sha256(row["source_id"].encode()).hexdigest()[:16]}"><h3><a href="{esc(row["source_url"])}">{esc(headword)} ({esc(row["homonym"])})</a></h3><p>HTML: {esc(row["definition"])}</p><p>Proposed printed heading, QA line {row["line"]}: {esc(row["printed_heading"])}</p><p>Printed OCR: {esc(row["printed_evidence"])}</p><details><summary>Uncertainties and alternatives</summary><pre>{esc(json.dumps({k: row[k] for k in ("risks", "alternatives", "definition_evidence", "evidence_lines")}, ensure_ascii=False, indent=2))}</pre></details></article>')
        parts.append('</section>')
    (output/'index.html').write_text('\n'.join(parts))
    return report['counts']


def validate_observations(pilot_path, observations_path, image_directory=None):
    """Check source bindings, not the truth of a visual interpretation.

    Wrong-side, rejected and deferred observations remain useful records; none
    of these statuses confers certificate or reader-attachment authority.
    """
    pilot = json.loads(pilot_path.read_text())
    observations = json.loads(observations_path.read_text())
    if observations['pilot_sha256'] != digest(pilot_path):
        raise ValueError('stale pilot checksum')
    indexed = {}
    for row in pilot['candidates']:
        if row['source_id'] in indexed:
            raise ValueError('duplicate pilot candidate')
        indexed[row['source_id']] = row
    pages = set()
    physical = set()
    for observation in observations['observations']:
        key = observation['page_key']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', key) or key in pages:
            raise ValueError('unsafe or duplicate observed page')
        page = observation['page']
        if page != pilot['pages'].get(key):
            raise ValueError('changed observed page identity or geometry')
        family = observation['family']
        if FAMILIES.get(family) != page['source']:
            raise ValueError('observed page belongs to another scan family')
        if image_directory is not None:
            filename = observation.get('image_filename', key + '.png')
            if not re.fullmatch(r'[A-Za-z0-9_-]+\.png', filename):
                raise ValueError('unsafe rendered evidence filename')
            image = image_directory / filename
            if image.is_symlink() or digest(image) != observation['image_sha256']:
                raise ValueError('changed rendered evidence')
        pages.add(key)
        physical.add((family, page['physical_page']))
    seen = set()
    statuses = {'observed_candidate_requires_certificate', 'rejected_proposed_article', 'deferred'}
    fields = ('source_id', 'source_url', 'html_sha256', 'input_identity',
              'anchor', 'headword', 'homonym', 'family', 'physical_page')
    for row in observations['candidates']:
        sid = row['source_id']
        if sid in seen or sid not in indexed:
            raise ValueError('duplicate or unknown observed candidate')
        expected = indexed[sid]
        if any(row.get(field) != expected.get(field) for field in fields):
            raise ValueError('changed observed candidate identity')
        if (row['family'], row['physical_page']) not in physical:
            raise ValueError('candidate has no observed physical page')
        if row['observation_status'] not in statuses or not row.get('reason'):
            raise ValueError('missing observation decision or reason')
        if row.get('eligible_for_original_print_link') is not False:
            raise ValueError('observations cannot authorize attachment')
        seen.add(sid)
    counts = dict(printed_pages_observed=len(pages), physical_pages_observed=len(physical),
                  candidates_observed=len(seen), new_verified_links=0)
    if observations['counts'] != counts:
        raise ValueError('incorrect observation counts')
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposals', type=Path)
    parser.add_argument('--facsimiles', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pilot', type=Path)
    parser.add_argument('--validate-observations', type=Path)
    parser.add_argument('--images', type=Path)
    args = parser.parse_args()
    if args.validate_observations:
        if not args.pilot:
            parser.error('--validate-observations requires --pilot')
        result = validate_observations(args.pilot, args.validate_observations, args.images)
    else:
        if not all((args.proposals, args.facsimiles, args.output)):
            parser.error('building requires --proposals, --facsimiles and --output')
        result = build(args.proposals, args.facsimiles, args.output)
    print(json.dumps(result, sort_keys=True))
