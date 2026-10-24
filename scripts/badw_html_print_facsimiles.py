"""Reviewed HTML witness → original printed page; lossless, shared PDF views.

No lexical matching is performed here. A reviewed row binds an exact acquired
HTML checksum to a heading/definition on an explicitly inspected scan page.
PDF-derived witnesses are deliberately outside this contract.
"""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / 'data/badw_html_print_pages.json'
METHOD = 'pdf-page-boxes-v1'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def derivative_id(source_sha256, page, crop):
    return hashlib.sha256(json.dumps([METHOD, source_sha256, page, crop], separators=(',', ':')).encode()).hexdigest()


def check_page(page, review):
    """PDF coordinates in points, bottom left origin; physical pages are 1-based."""
    crop = review['crop']
    box = page.mediabox
    if page.rotation or len(crop) != 4 or not (
        float(box.left) <= crop[0] < crop[2] <= float(box.right) and
        float(box.bottom) <= crop[1] < crop[3] <= float(box.top)
    ):
        raise ValueError('unreviewed rotation or invalid crop geometry')
    if review['side'] not in ('left', 'right', 'single'):
        raise ValueError('unknown printed-page side')
    if review['side'] == 'single' and crop != list(map(float, box)):
        raise ValueError('single-page source must retain its complete page')


def prepare(scans_root, output, reviews=REVIEWS, registry=ROOT/'data/source_pdfs.tsv'):
    """Generate each distinct page once. Never modify registered originals."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    reviewed = json.loads(Path(reviews).read_text())
    sources = {r['label']: r for r in csv.DictReader(Path(registry).open(), delimiter='\t')}
    readers, originals, pages = {}, {}, {}
    for key, row in reviewed['pages'].items():
        source = sources[row['source']]
        path = Path(scans_root)/source['filename']
        if row['source_sha256'] != source['sha256']:
            raise ValueError('review differs from registered source checksum')
        if row['source'] not in readers:
            if sha256(path) != source['sha256']:
                raise ValueError('original scan checksum mismatch')
            readers[row['source']] = PdfReader(path)
            originals[source['sha256']] = str(path.resolve())
        reader = readers[row['source']]
        if not 1 <= row['physical_page'] <= len(reader.pages):
            raise ValueError('physical PDF page out of range')
        page = reader.pages[row['physical_page']-1]
        check_page(page, row)
        identity = derivative_id(source['sha256'], row['physical_page'], row['crop'])
        dest = output/(identity+'.pdf')
        writer = PdfWriter()
        writer.add_page(page)
        # Both boxes are required: ordinary browser viewers must open a single
        # printed page at normal scale. Image XObjects are copied, not resampled.
        writer.pages[0].mediabox = RectangleObject(row['crop'])
        writer.pages[0].cropbox = RectangleObject(row['crop'])
        writer.add_metadata({'/Title': f"WTS {row['volume']}, p. {row['printed_page']}",
                             '/Producer': METHOD})
        with dest.open('wb') as stream:
            writer.write(stream)
        pages[key] = dict(row, id=identity, filename=dest.name, sha256=sha256(dest), method=METHOD)
    witnesses, seen = [], set()
    for row in reviewed['witnesses']:
        binding = (row['source_url'], row['html_sha256'])
        if binding in seen or row['page'] not in pages or not row['evidence'] or not row['printed_heading']:
            raise ValueError('duplicate or incomplete reviewed witness')
        seen.add(binding)
        witnesses.append(row)
    manifest = dict(version=1, reviews_sha256=sha256(reviews), registry_sha256=sha256(registry),
                    pages=pages, witnesses=witnesses, originals=originals)
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


class Facsimiles:
    def __init__(self, manifest, output):
        self.path = Path(manifest)
        self.data = json.loads(self.path.read_text())
        if self.data['version'] != 1 or self.data['reviews_sha256'] != sha256(REVIEWS) or self.data['registry_sha256'] != sha256(ROOT/'data/source_pdfs.tsv'):
            raise ValueError('stale facsimile manifest')
        reviewed = json.loads(REVIEWS.read_text())
        if self.data['witnesses'] != reviewed['witnesses'] or set(self.data['pages']) != set(reviewed['pages']):
            raise ValueError('facsimile manifest differs from reviewed evidence')
        for key, review in reviewed['pages'].items():
            page = self.data['pages'][key]
            if any(page.get(field) != value for field, value in review.items()) or page.get('method') != METHOD:
                raise ValueError('facsimile manifest differs from reviewed geometry')
        self.witnesses = {(r['source_url'], r['html_sha256']): r for r in self.data['witnesses']}
        self.output = Path(output)
        self.used = set()

    def attach(self, entry):
        if entry['source_kind'] != 'html':
            return
        editorial = entry['sources'][0]
        row = self.witnesses.get((entry['source_url'], editorial['sha256']))
        if row is None:
            return
        if entry['headword']['loc'] != row['headword'] or str(entry.get('homonym') or 1) != str(row['homonym']):
            raise ValueError('reviewed HTML witness identity changed')
        page = self.data['pages'][row['page']]
        expected_id = derivative_id(page['source_sha256'], page['physical_page'], page['crop'])
        if page['id'] != expected_id or page['filename'] != expected_id+'.pdf':
            raise ValueError('invalid derivative identity')
        if page['id'] not in self.used:
            src = self.path.parent/page['filename']
            if sha256(src) != page['sha256']:
                raise ValueError('facsimile checksum mismatch')
            dest = self.output/'sources/print'/page['filename']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            # Verify private originals without exposing them in the served reader.
            original = Path(self.data['originals'][page['source_sha256']])
            if sha256(original) != page['source_sha256']:
                raise ValueError('original scan checksum mismatch')
            self.used.add(page['id'])
        editorial['label'] = 'BAdW editorial text'
        entry['sources'].append(dict(url='sources/print/'+page['filename']+'#page=1&view=Fit',
            label=f"Original printed edition · {page['volume']}, p. {page['printed_page']}",
            sha256=page['sha256'], print_provenance=dict(page, evidence=row['evidence'],
                printed_heading=row['printed_heading'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scans-root', type=Path, required=True, help='Checkout containing the registered pdfs/ directory')
    parser.add_argument('--output', type=Path, required=True, help='Ignored derivative cache directory')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'work'):
        parser.error('derivatives must be under ignored work/')
    result = prepare(args.scans_root, args.output)
    print(json.dumps(dict(witnesses=len(result['witnesses']), distinct_pages=len(result['pages']),
        cropped=sum(p['side'] != 'single' for p in result['pages'].values()),
        single=sum(p['side'] == 'single' for p in result['pages'].values()))))


if __name__ == '__main__':
    main()
