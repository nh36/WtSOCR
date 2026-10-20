"""Add independently corroborated, derived LoC display forms to a full reader.

Refuses existing outputs and verifies the parent catalog and every entry shard.
Only exact whole headwords and whole, exclusively Tibetan-language segments
which match those headwords are eligible. No source fields are replaced.
"""
import argparse
import collections
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_display(entry, attested):
    result = collections.Counter()
    headword = entry['headword']
    value = attested.get(headword.get('loc'))
    if value and value == headword.get('tibetan'):
        entry['derived_headword'] = dict(tibetan=value, evidence='independent_paired_headword_agreement')
        result['headwords'] += 1
    for block in entry['display_blocks']:
        for segment in block['segments']:
            languages = segment.get('effective_languages', segment.get('languages', []))
            value = attested.get(segment['text'])
            if value and languages == ['bo']:
                segment['derived_tibetan'] = value
                segment['derived_evidence'] = 'exact_whole_attested_headword_in_exclusive_bo_span'
                result['passages'] += 1
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reader', type=Path, required=True)
    ap.add_argument('--experiment', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'work'):
        ap.error('output must be a new directory under work/')
    parent = json.loads((args.reader/'manifest.json').read_text())
    metrics = json.loads((args.experiment/'metrics.json').read_text())
    catalog_hash = sha(args.reader/'data.json')
    if catalog_hash != parent['catalog_sha256'] or catalog_hash != metrics['catalog_sha256']:
        raise ValueError('parent/experiment catalog mismatch')
    if sha(args.experiment/'attested_display.json') != metrics['display_sha256']:
        raise ValueError('display evidence hash mismatch')
    for name, expected in metrics['input_sha256'].items():
        if sha(ROOT/name) != expected:
            raise ValueError('stale experiment input: '+name)
    display = json.loads((args.experiment/'attested_display.json').read_text())['headwords']
    catalog = json.loads((args.reader/'data.json').read_text())
    out.mkdir(parents=True)
    (out/'entries').mkdir()
    counts = collections.Counter()
    for meta in catalog['entries']:
        path = Path(meta['path'])
        if path.parent != Path('entries') or sha(args.reader/path) != meta['sha256']:
            raise ValueError('parent shard integrity failure')
        entry = json.loads((args.reader/path).read_text())
        if entry['id'] != meta['id']:
            raise ValueError('parent shard identity mismatch')
        counts.update(add_display(entry, display))
        (out/path).write_text(json.dumps(entry, ensure_ascii=False, separators=(',', ':')))
        meta['sha256'] = sha(out/path)
    for name in ('sources', 'fonts'):
        shutil.copytree(args.reader/name, out/name)
    for name in ('reference_cases.jsonl', 'annotation_conflicts.json'):
        shutil.copyfile(args.reader/name, out/name)
    for name in ('index.html', 'app.js', 'style.css'):
        shutil.copyfile(ROOT/'scripts/badw_dictionary_prototype'/name, out/name)
    catalog['preview']['loc_experiment'] = dict(version=metrics['version'], **counts)
    (out/'data.json').write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')))
    parent.update(catalog_sha256=sha(out/'data.json'), parent_manifest_sha256=sha(args.reader/'manifest.json'),
                  loc_experiment=dict(metrics_sha256=sha(args.experiment/'metrics.json'), **counts),
                  display_inputs=[dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for p in
                                  [Path(__file__).resolve(), *[ROOT/'scripts/badw_dictionary_prototype'/n for n in ('index.html', 'app.js', 'style.css')]]])
    (out/'manifest.json').write_text(json.dumps(parent, ensure_ascii=False, indent=2)+'\n')
    shutil.copyfile(args.experiment/'metrics.json', out/'loc_metrics.json')
    print(json.dumps(dict(reader=str(out), **counts)))


if __name__ == '__main__':
    main()
