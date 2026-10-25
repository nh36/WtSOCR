#!/usr/bin/env python3
"""Prepare portable, checksum-bound alignment inputs from a complete local reader.

No acquisition, publication or source mutation. The prepared body map is private.
Optional historical corroboration is copied, not required to discover QA starts.
"""
import argparse
import json
import os
from pathlib import Path
import shutil

from badw_html_print_engine import atomic_json, catalogue_records, connection, index_witnesses
from badw_html_print_alignment import digest

ROOT = Path(__file__).resolve().parents[1]


def prepare(reader, output, history=None):
    reader, output = reader.resolve(), output.resolve()
    if not output.is_relative_to((ROOT / 'work').resolve()):
        raise ValueError('private prepared inputs must stay under work/')
    output.mkdir(parents=True, exist_ok=True)
    rows, _ = catalogue_records(reader / 'data.json')
    temporary = output / 'bodies.json.tmp'
    with temporary.open('w') as stream:
        stream.write('{')
        first = True
        for row in rows:
            if row['source_kind'] != 'html':
                continue
            supplied = reader / row['path']
            path = supplied.resolve()
            if not path.is_relative_to(reader) or supplied.is_symlink():
                raise ValueError('unsafe entry shard')
            if digest(path) != row['sha256']:
                raise ValueError('entry shard checksum mismatch: ' + row['id'])
            body = json.loads(path.read_text())
            stream.write(('' if first else ',') + json.dumps(body['inspection_id']) + ':' +
                         json.dumps(body, ensure_ascii=False, separators=(',', ':')))
            first = False
        stream.write('}\n')
    shutil.copyfile(reader / 'data.json', output / 'catalogue.json.tmp')
    db = connection(':memory:')
    counts = index_witnesses(db, temporary, output / 'catalogue.json.tmp')
    db.close()
    os.replace(temporary, output / 'bodies.json')
    os.replace(output / 'catalogue.json.tmp', output / 'catalogue.json')
    files = ['bodies.json', 'catalogue.json']
    if history:
        for key in ('anchors', 'edges'):
            name = key + '.jsonl'
            shutil.copyfile(history[key], output / (name + '.tmp'))
            os.replace(output / (name + '.tmp'), output / name)
            files.append(name)
    manifest = dict(schema=1, counts=counts, historical_corroboration=bool(history),
                    files={name: digest(output / name) for name in sorted(files)})
    atomic_json(output / 'manifest.json', manifest)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reader', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'work/html-print-inputs')
    p.add_argument('--anchors', type=Path)
    p.add_argument('--edges', type=Path)
    a = p.parse_args()
    if bool(a.anchors) != bool(a.edges):
        p.error('--anchors and --edges must be supplied together')
    print(json.dumps(prepare(a.reader, a.output, dict(anchors=a.anchors, edges=a.edges)
                            if a.anchors else None), indent=2))


if __name__ == '__main__':
    main()
