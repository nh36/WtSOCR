#!/usr/bin/env python3
"""Prepare the local editorial reader from the reviewed apparatus inventory.

No source volumes are copied or linked. PDF page boxes are visual crops, not
redaction; these outputs are for local research, not external distribution.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / 'data/bibliography_apparatus_editorial_pages.jsonl'
CONFIG = ROOT / 'data/badw_editorial_collection.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def select_text(row, selection):
    text = row.get('verified_editorial_transcription') or re.sub(r'^=== page \d+ ===\s*', '', row['source_span']['raw_text'])
    if selection.get('start'):
        start = selection['start']
        if text.count(start) != 1:
            raise ValueError('nonunique editorial start')
        text = text[text.index(start):]
    if selection.get('end_before'):
        end = selection['end_before']
        if text.count(end) != 1:
            raise ValueError('nonunique editorial end')
        text = text[:text.index(end)]
    return text.strip()


def extract_page(source, crop, target):
    box = list(map(float, source.mediabox))
    if source.get('/Rotate', 0) != 0:
        raise ValueError('unreviewed rotation')
    x0, y0, x1, y1 = crop
    if not (box[0] <= x0 < x1 <= box[2] and box[1] <= y0 < y1 <= box[3]):
        raise ValueError('crop outside original page')
    writer = PdfWriter()
    page = writer.add_page(source)
    page.mediabox = RectangleObject(crop)
    page.cropbox = RectangleObject(crop)
    with target.open('wb') as stream:
        writer.write(stream)


def build(output, source_root=ROOT, config_path=CONFIG, inventory_path=INVENTORY, registry_path=ROOT / 'data/source_pdfs.tsv'):
    config = json.loads(config_path.read_text())
    if digest(inventory_path) != config['inventory_sha256']:
        raise ValueError('editorial inventory changed; review selections')
    if output.exists():
        raise ValueError('output must be a fresh directory')
    rows = [json.loads(line) for line in inventory_path.read_text().splitlines() if line.strip()]
    registry = {r['label']: r for r in csv.DictReader(registry_path.open(), delimiter='\t') if r['label']}
    readers = {}
    for label in {r['source_label'] for r in rows}:
        registered = registry[label]
        relative_source = Path(registered['filename'])
        if relative_source.is_absolute() or '..' in relative_source.parts:
            raise ValueError('unsafe registered source path')
        path = source_root / relative_source
        if digest(path) != registered['sha256']:
            raise ValueError('registered scan checksum mismatch: ' + label)
        readers[label] = PdfReader(path)
    output.mkdir(parents=True)
    (output / 'pages').mkdir()
    documents = []
    prepared = {}
    for document in config['documents']:
        sections = []
        for selection in document['sections']:
            matches = [r for r in rows if r['zone_id'] == document['id'] and r['scan_page'] == selection['scan_page']]
            if len(matches) != 1:
                raise ValueError('missing or duplicate inventory page')
            row = matches[0]
            if row['pdf_sha256'] != registry[row['source_label']]['sha256']:
                raise ValueError('inventory/scan identity mismatch')
            if not 1 <= row['scan_page'] <= len(readers[row['source_label']].pages):
                raise ValueError('physical page outside registered scan')
            page = readers[row['source_label']].pages[row['scan_page'] - 1]
            box = list(map(float, page.mediabox))
            views = []
            for view in selection['views']:
                if view['side'] not in ('single', 'left', 'right'):
                    raise ValueError('invalid page side')
                if view['side'] != 'single' and not 0 < view['gutter_fraction'] < 1:
                    raise ValueError('invalid gutter')
                crop = box.copy()
                if view['side'] != 'single':
                    cut = box[0] + view['gutter_fraction'] * (box[2] - box[0])
                    crop[2 if view['side'] == 'left' else 0] = cut
                identity = dict(source_sha256=row['pdf_sha256'], physical_page=row['scan_page'], crop=crop, method='pdf-page-boxes-editorial-v1')
                key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                relative = 'pages/' + key + '.pdf'
                if key not in prepared:
                    extract_page(page, crop, output / relative)
                    prepared[key] = dict(**identity, url=relative, sha256=digest(output / relative))
                views.append(dict(folio=view['folio'], **prepared[key]))
            sections.append(dict(text=select_text(row, selection), reading_status='verified_editorial_transcription' if row.get('verified_editorial_transcription') else row['reading_status'], source_label=row['source_label'], physical_page=row['scan_page'], ocr_sha256=row['ocr_sha256'], source_span={k: row['source_span'][k] for k in ('start', 'end')}, raw_span_sha256=hashlib.sha256(row['source_span']['raw_text'].encode()).hexdigest(), views=views))
        documents.append({**{k: v for k, v in document.items() if k != 'sections'}, 'sections': sections})
    manifest = dict(local_research_only=True, distribution_authorised=False, inventory_sha256=digest(inventory_path), configuration_sha256=digest(config_path), documents=documents)
    (output / 'collection.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    assets = ROOT / 'scripts/badw_dictionary_prototype'
    for src, dst in [('editorial.html', 'index.html'), ('editorial.js', 'editorial.js'), ('style.css', 'style.css')]:
        shutil.copyfile(assets / src, output / dst)
    shutil.copytree(assets / 'fonts', output / 'fonts')
    return dict(documents=len(documents), source_sections=sum(len(d['sections']) for d in documents), derivatives=len(prepared))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.source_root)))


if __name__ == '__main__':
    main()
