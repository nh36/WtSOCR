#!/usr/bin/env python3
"""Migrate exact reviews only across verified page and unchanged line anchors.

No fuzzy matching: a changed reviewed line requires renewed source review.
Outputs are proposals, not modifications to the tracked review tables.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

from badw_canonical_pages import stable_json_bytes, write_tsv


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def visual(article: dict) -> str:
    return '\n'.join(line['text'] for line in article['visual_lines'])


def anchor(line: dict, pages: dict[str, str]) -> tuple:
    return (pages.get(line['page_id'], line['page_id']), line['span_index'],
            line['run_start'], line['run_end_exclusive'])


def migrate_review(row: dict, old: dict, new: dict, pages: dict[str, str]) -> dict:
    """Require identical PDF/run spans and exact text on every reviewed line."""
    if row['article_id'] != old['article_id'] or row['visual_sha256'] != digest(visual(old)):
        raise ValueError('stale original review')
    old_objects = [(pages[o['page_id']], o['pdf_sha256'], o['run_start'],
                    o['run_end_exclusive']) for o in old['source_objects']]
    new_objects = [(o['page_id'], o['pdf_sha256'], o['run_start'],
                    o['run_end_exclusive']) for o in new['source_objects']]
    if old_objects != new_objects:
        raise ValueError('article source coordinates changed')
    targets = {}
    offset = 0
    for line in new['visual_lines']:
        key = anchor(line, {})
        if key in targets:
            raise ValueError('ambiguous new line anchor')
        targets[key] = (offset, line['text'])
        offset += len(line['text']) + 1

    def transfer(start: int, end: int, expected_hash: str) -> tuple[int, int]:
        text = visual(old)
        if not 0 <= start < end <= len(text) or digest(text[start:end]) != expected_hash:
            raise ValueError('stale original reviewed span')
        segments = []
        cursor = 0
        for line in old['visual_lines']:
            right = cursor + len(line['text'])
            if start < right + 1 and end > cursor:
                key = anchor(line, pages)
                target = targets.get(key)
                if target is None or target[1] != line['text']:
                    raise ValueError('reviewed line changed; manual review required')
                left = max(start, cursor) - cursor
                stop = min(end, right + 1) - cursor
                segments.append((target[0] + left, target[0] + stop))
            cursor = right + 1
        if not segments or any(a[1] != b[0] for a, b in zip(segments, segments[1:])):
            raise ValueError('reviewed span is no longer contiguous')
        bounds = segments[0][0], segments[-1][1]
        if visual(new)[bounds[0]:bounds[1]] != text[start:end]:
            raise ValueError('reviewed literal changed')
        return bounds

    result = dict(row)
    result['article_id'] = new['article_id']
    result['visual_sha256'] = digest(visual(new))
    for prefix, hash_key in [('visual', 'quote_sha256'), ('example', 'example_sha256')]:
        if hash_key in row:
            start, end = transfer(int(row[prefix + '_start']), int(row[prefix + '_end']), row[hash_key])
            result[prefix + '_start'], result[prefix + '_end'] = str(start), str(end)
    return result


def build(old_path: Path, new_path: Path, crosswalk: Path, reviews: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    with crosswalk.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))
    if any(row['geometry_verified'] != 'True' for row in rows):
        raise ValueError('unverified page crosswalk')
    pages = {row['old_page_id']: row['new_page_id'] for row in rows}
    if len(pages) != len(rows) or len(set(pages.values())) != len(rows):
        raise ValueError('non-bijective page crosswalk')
    with reviews.open(encoding='utf-8', newline='') as handle:
        reviews_rows = list(csv.DictReader(handle, delimiter='\t'))
    if not reviews_rows:
        raise ValueError('review table is empty')
    ids = {row['article_id'] for row in reviews_rows}
    articles = {}
    with gzip.open(old_path, 'rt', encoding='utf-8') as handle:
        for line in handle:
            article = json.loads(line)
            if article['article_id'] in ids:
                articles[article['article_id']] = article
    new_ids = {}
    for ident in ids:
        head, run = ident.rsplit(':', 1)
        page = head.removeprefix('badw:pdf:')
        new_ids[ident] = 'badw:pdf:' + pages[page] + ':' + run
    targets = {}
    target_ids = set(new_ids.values())
    with gzip.open(new_path, 'rt', encoding='utf-8') as handle:
        for line in handle:
            article = json.loads(line)
            if article['article_id'] in target_ids:
                targets[article['article_id']] = article
    proposals, blocked = [], []
    for row in reviews_rows:
        ident = row['article_id']
        try:
            proposals.append(migrate_review(row, articles[ident], targets[new_ids[ident]], pages))
        except (ValueError, KeyError) as error:
            blocked.append({'review': row, 'reason': str(error),
                            'new_article_id': new_ids[ident],
                            'changed_lines': changed_lines(articles.get(ident),
                                                           targets.get(new_ids[ident]), pages)})
    write_tsv(output, list(reviews_rows[0]), proposals)
    diagnostics = output.with_suffix('.blocked.jsonl')
    diagnostics.write_bytes(b''.join(stable_json_bytes(row) + b'\n' for row in blocked))
    report = {'contract_version': 'badw-review-migration-v1', 'reviews': len(proposals),
              'attempted': len(reviews_rows), 'blocked': len(blocked),
              'complete': not blocked, 'blocked_sha256': hashlib.sha256(diagnostics.read_bytes()).hexdigest(),
              'method': 'verified_pdf_run_coordinates_and_unchanged_reviewed_lines',
              'inputs': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in [old_path, new_path, crosswalk, reviews]},
              'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
    output.with_suffix('.migration.json').write_bytes(stable_json_bytes(report) + b'\n')
    return report


def changed_lines(old: dict | None, new: dict | None, pages: dict[str, str]) -> list[dict]:
    """Audit evidence only; never use changed text to authorize a migration."""
    if old is None or new is None:
        return []
    targets = {anchor(line, {}): line['text'] for line in new['visual_lines']}
    return [{'anchor': anchor(line, pages), 'old_text': line['text'],
             'new_text': targets.get(anchor(line, pages))}
            for line in old['visual_lines']
            if targets.get(anchor(line, pages)) != line['text']]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['old', 'new', 'crosswalk', 'reviews', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.old, args.new, args.crosswalk, args.reviews, args.output)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['complete'] else 1)
