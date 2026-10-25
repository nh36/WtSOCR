#!/usr/bin/env python3
"""Render the deterministic sample locally. Never copy or serve source PDFs.

The full-page PNGs are private review evidence, not newly approved facsimiles.
No unreviewed folio, spread side, or gutter split is asserted by this utility.
"""
import argparse
import csv
import json
import html
from pathlib import Path
import subprocess
import tempfile

from badw_html_print_alignment import FAMILIES, digest
from badw_html_print_engine import atomic_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    if not run.is_relative_to(ROOT / 'work'):
        parser.error('review output must remain under ignored work/')
    pin = json.loads((run / 'inputs.json').read_text())
    # A bounded, paginated exception queue; the JSONL retains every proposal.
    queue = run / 'report/exceptions'
    queue.mkdir(exist_ok=True)
    batch = []
    links = []
    def flush():
        if not batch:
            return
        name = f'page-{len(links):03d}.html'
        content = ['<!doctype html><meta charset="utf-8"><title>Alignment exceptions</title>',
                   '<h1>Provisional exceptions — not accepted links</h1><a href="index.html">Queue index</a>']
        for row in batch:
            content.append('<article><h2>' + html.escape(row['editorial_headword']['loc']) + '</h2><pre>' +
                           html.escape(json.dumps(row, ensure_ascii=False, indent=2)) + '</pre></article>')
        (queue / name).write_text('\n'.join(content))
        links.append(name)
        batch.clear()
    with (run / 'witnesses.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            if row['result_category'] != 'mechanically_supported_provisional':
                batch.append(row)
                if len(batch) == 100:
                    flush()
    flush()
    (queue / 'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>Complete exception queue</h1>' +
        ''.join(f'<p><a href="{name}">{name}</a></p>' for name in links))
    sample = json.loads((run / 'validation.json').read_text())['sample']
    registry = {r['label']: r for r in csv.DictReader((ROOT / 'data/source_pdfs.tsv').open(), delimiter='\t')}
    for family, label in FAMILIES.items():
        if digest(ROOT / registry[label]['filename']) != pin['inputs']['scan:' + family]:
            raise ValueError('source changed: ' + family)
    images = run / 'report/images'
    images.mkdir(exist_ok=True)
    rendered = {}
    records = []
    for number, row in enumerate(sample):
        family, page, line = row['anchor'].split(':')
        target = images / f'{number:02d}.png'
        source = ROOT / registry[FAMILIES[family]]['filename']
        key = (family, page)
        if key in rendered:
            # Reuse a local image, never a link to private source storage.
            target.write_bytes(rendered[key].read_bytes())
        else:
            with tempfile.TemporaryDirectory(dir=run) as tmp:
                prefix = Path(tmp) / 'page'
                subprocess.run(['pdftoppm', '-f', page, '-l', page, '-singlefile',
                                '-r', '120', '-png', str(source), str(prefix)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                prefix.with_suffix('.png').replace(target)
            rendered[key] = target
        records.append(dict(source_id=row['source_id'], anchor=row['anchor'],
                            scan_sha256=pin['inputs']['scan:' + family],
                            image=target.relative_to(run / 'report').as_posix(),
                            image_sha256=digest(target), dpi=120,
                            interpretation='complete physical scan page for private review; not an accepted crop'))
        print(f'{number + 1}/{len(sample)} {row["anchor"]}', flush=True)
    atomic_json(run / 'report/images.json', records)
    gallery = ['<!doctype html><meta charset="utf-8"><title>Source-page review images</title>',
               '<style>body{font:16px system-ui;max-width:1100px;margin:auto}img{max-width:100%}pre{white-space:pre-wrap}</style>',
               '<h1>Private source-page review — provisional proposals</h1>',
               '<p><a href="review.html">Evidence report</a> · <a href="exceptions/index.html">Complete exception queue</a></p>']
    for number, record in enumerate(records):
        gallery.append('<article><h2>' + html.escape(record['anchor']) + '</h2>' +
                       f'<p><a href="review.html#case-{number}">OCR, HTML evidence and alternatives</a></p>' +
                       '<img loading="lazy" alt="Physical scan page for review" src="' + record['image'] + '"></article>')
    (run / 'report/index.html').write_text('\n'.join(gallery))


if __name__ == '__main__':
    main()
