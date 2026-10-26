#!/usr/bin/env python3
"""Bind cached hOCR coordinates to exact registered PDF renderings, offline.

This does not rerun OCR. Every cached image must reproduce pixel-for-pixel at
300 dpi from its registered PDF page. The portable result contains text/boxes,
checksums and no private paths. Keep it under ignored work/, never serve it.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image
from pypdf import PdfReader
from badw_html_print_alignment import FAMILIES, digest, object_digest
from badw_html_print_engine import atomic_json

VERSION = 'render-bound-hocr-v1'


def parse_hocr(path, width, height, raster_size):
    text = ''.join(c for c in path.read_text() if c in '\t\r\n' or ord(c) >= 32)
    root = ET.fromstring(text)
    pages = [e for e in root.iter() if 'ocr_page' in e.get('class', '').split()]
    if len(pages) != 1:
        raise ValueError('hOCR must describe exactly one physical page')
    def bbox(element):
        m = re.search(r'\bbbox (\d+) (\d+) (\d+) (\d+)', element.get('title', ''))
        if not m:
            raise ValueError('missing hOCR box')
        return list(map(int, m.groups()))
    bounds = bbox(pages[0])
    if bounds != [0, 0, *raster_size]:
        raise ValueError('hOCR canvas does not match source-bound raster')
    rows = []
    for e in root.iter():
        if 'ocr_line' not in e.get('class', '').split():
            continue
        b = bbox(e)
        if not (0 <= b[0] < b[2] <= raster_size[0] and 0 <= b[1] < b[3] <= raster_size[1]):
            raise ValueError('hOCR line outside source image')
        rows.append(dict(text=''.join(e.itertext()).strip(), pixel_box=b,
                         box=[b[0]*width/raster_size[0], b[1]*height/raster_size[1],
                              b[2]*width/raster_size[0], b[3]*height/raster_size[1]]))
    return rows


def pixels(path):
    with Image.open(path) as im:
        im = im.convert('RGB')
        return list(im.size), hashlib.sha256(im.tobytes()).hexdigest()


def prepare_page(job):
    family, number, pdf, source_sha, cache, width, height, output = job
    image, hocr = cache/f'p{number:04d}.png', cache/f'p{number:04d}_A.hocr'
    image_sha, hocr_sha = digest(image), digest(hocr)
    identity = dict(source_sha256=source_sha, physical_page=number, image_sha256=image_sha,
                    hocr_sha256=hocr_sha, width=width, height=height, method=VERSION)
    target = output/'verified'/family/f'{number:04d}.json'
    if target.exists():
        prior = json.loads(target.read_text())
        if prior['input_identity'] == identity and prior['record_sha256'] == object_digest(prior['record']):
            return prior['record']
    size, pixel_sha = pixels(image)
    with tempfile.TemporaryDirectory(prefix='wts-render-') as temporary:
        prefix = Path(temporary)/'page'
        subprocess.run(['pdftoppm', '-f', str(number), '-l', str(number), '-r', '300',
                        '-png', '-singlefile', str(pdf), str(prefix)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        actual_size, actual_sha = pixels(prefix.with_suffix('.png'))
    if (size, pixel_sha) != (actual_size, actual_sha):
        raise ValueError(f'cached raster is not an exact registered-page rendering: {family}:{number}')
    lines = parse_hocr(hocr, width, height, size)
    record = dict(family=family, physical_page=number, source_sha256=source_sha,
                  raster_size=size, raster_sha256=image_sha, pixel_sha256=pixel_sha,
                  hocr_sha256=hocr_sha, width=width, height=height, method=VERSION,
                  render=dict(tool='pdftoppm', dpi=300, comparison='exact RGB pixels'),
                  lines=lines)
    if not lines:
        record['unsupported'] = 'no_ocr_lines; not evidence that the scan is blank'
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(target, dict(input_identity=identity, record=record, record_sha256=object_digest(record)))
    return record



def validate_bundle(directory, registry):
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest['schema'] != 1 or manifest['method'] != VERSION:
        raise ValueError('unsupported coordinate input schema/method')
    if set(manifest['files']) != {f+'.jsonl' for f in FAMILIES}:
        raise ValueError('incomplete coordinate input families')
    for family, label in FAMILIES.items():
        source = registry[label]
        if manifest['sources'][family] != source['sha256'] or manifest['pages'][family] != int(source['pages']):
            raise ValueError('coordinate registry identity mismatch: '+family)
        path = directory/(family+'.jsonl')
        if digest(path) != manifest['files'][path.name]:
            raise ValueError('coordinate file checksum mismatch: '+family)
        count = 0
        with path.open() as stream:
            for count, line in enumerate(stream, 1):
                record = json.loads(line)
                if (record['family'], record['physical_page'], record['source_sha256'], record['method']) != (family, count, source['sha256'], VERSION):
                    raise ValueError('wrong coordinate page identity: '+family)
        if count != int(source['pages']):
            raise ValueError('incomplete coordinate page population: '+family)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache-map', type=Path, required=True, help='JSON mapping family to cached pages directory')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--workers', type=int, default=2, choices=(1, 2, 3, 4))
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = a.output.resolve()
    if not output.is_relative_to((root/'work').resolve()):
        p.error('coordinate inputs must remain under ignored work/')
    output.mkdir(parents=True, exist_ok=True)
    caches = json.loads(a.cache_map.read_text())
    if set(caches) != set(FAMILIES):
        raise ValueError('all four source families required')
    registry = {r['label']: r for r in csv.DictReader((root/'data/source_pdfs.tsv').open(), delimiter='\t')}
    files = {}; counts = {}; sources = {}
    for family, label in FAMILIES.items():
        source = registry[label]; pdf = root/source['filename']
        if digest(pdf) != source['sha256']:
            raise ValueError('changed registered scan: '+family)
        reader = PdfReader(pdf)
        if len(reader.pages) != int(source['pages']):
            raise ValueError('registered page count mismatch')
        jobs = []
        for n, page in enumerate(reader.pages, 1):
            if page.rotation or list(map(float, page.mediabox))[:2] != [0., 0.]:
                raise ValueError(f'rotation/media-box origin requires an explicit transform: {family}:{n}')
            jobs.append((family, n, pdf, source['sha256'], Path(caches[family]),
                         float(page.mediabox.width), float(page.mediabox.height), output))
        target = output/(family+'.jsonl'); temporary = target.with_suffix('.jsonl.tmp')
        with ThreadPoolExecutor(max_workers=a.workers) as pool, temporary.open('w') as f:
            for n, record in enumerate(pool.map(prepare_page, jobs), 1):
                f.write(json.dumps(record, ensure_ascii=False, sort_keys=True)+'\n')
                if n % 50 == 0 or n == len(jobs):
                    print(f'{family}: {n}/{len(jobs)} registered raster/hOCR pages bound', flush=True)
        temporary.replace(target)
        files[target.name] = digest(target); counts[family] = len(jobs); sources[family] = source['sha256']
    atomic_json(output/'manifest.json', dict(schema=1, method=VERSION, files=files, pages=counts,
        sources=sources, authority='render-bound OCR geometry; not independent verification of OCR readings'))


if __name__ == '__main__':
    main()
