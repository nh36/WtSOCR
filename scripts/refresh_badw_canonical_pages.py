#!/usr/bin/env python3
"""Offline, immutable canonical-page refresh from the original cached PDF bytes.

This is a registry refresh, not source acquisition or article segmentation.
Positioned source identities must remain unchanged. Historical overlap/URL
observations are retained separately; they are not claimed to be new decodes.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from collections import Counter, OrderedDict

from badw_canonical_pages import stable_json_bytes, write_gzip_json, write_tsv
from badw_pdf_decoder import GlyphRegistry, decode_pdf_bytes


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def source_geometry(page: dict) -> list:
    """Exclude decoded readings, but include every positioned source glyph."""
    return [{k: v for k, v in run.items()
             if k not in ('decoded_unicode', 'glyphs', 'unknown_glyphs')} |
            {'glyphs': [{k: v for k, v in glyph.items()
                         if k not in ('unicode', 'unknown', 'mapping_method')}
                        for glyph in run['glyphs']]}
            for run in page['positioned_text_runs']]


UNKNOWN_FIELDS = ['family', 'style', 'cid', 'glyph_signature',
                  'canonical_page_occurrences']


def unknown_identities(page: dict) -> Counter:
    """Count source glyphs, not placeholders in a normalized text layer."""
    fonts = {str(font['font_id']): font for font in page['representative_fonts']}
    counts = Counter()
    for run in page['positioned_page']['positioned_text_runs']:
        font = fonts[str(run['font_id'])]
        for glyph in run['glyphs']:
            if glyph['unknown']:
                counts[(font['family'], font['style'], glyph['cid_hex'],
                        glyph['glyph_signature'])] += 1
    if sum(counts.values()) != page['unknown_glyph_occurrences']:
        raise ValueError('unknown-glyph census disagrees with positioned source')
    return counts


def write_unknown_census(target: Path, counts: Counter) -> None:
    rows = [dict(zip(UNKNOWN_FIELDS, (*key, count)))
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    write_tsv(target / 'canonical_unknown_glyphs.tsv', UNKNOWN_FIELDS, rows)


def refresh_page(old: dict, decoded: dict) -> dict:
    src = old['representative_source']
    if decoded['source_sha256'] != src['source_sha256']:
        raise ValueError('PDF source hash changed')
    positioned = decoded['pages'][int(src['pdf_page_index']) - 1]
    if stable_json_bytes(source_geometry(old['positioned_page'])) != stable_json_bytes(source_geometry(positioned)):
        raise ValueError('positioned source geometry changed')
    digest = sha(positioned['visible_text'].encode('utf-8'))
    page = dict(old)
    page.update(page_id=f"badw-v{old['volume']}-{digest}",
                visible_body_sha256=digest,
                representative_positioned_sha256=sha(stable_json_bytes(positioned)),
                positioned_page=positioned, representative_fonts=decoded['fonts'],
                source_faithful_decoded_text=positioned['visible_text'],
                derived_reading_order_text=positioned['normalized_reading'],
                unknown_glyph_occurrences=positioned['unknown_glyphs'],
                decoder_version=decoded['decoder_version'],
                source_decoder_contract_version=decoded['contract_version'],
                glyph_registry_sha256=decoded['glyph_registry_sha256'])
    page['refresh_provenance'] = {
        'previous_page_id': old['page_id'],
        'previous_registry_sha256': old['glyph_registry_sha256'],
        'previous_positioned_sha256': old['representative_positioned_sha256'],
        'method': 'offline_exact_cached_pdf_registry_refresh',
    }
    return page


def build(source: Path, cache: Path, output: Path, mapping: Path) -> dict:
    if output.exists():
        raise FileExistsError(f'refusing to replace snapshot: {output}')
    output.mkdir(parents=True)
    registry = GlyphRegistry.from_tsv(mapping)
    decoded_by_sha = OrderedDict()
    decoded_hashes = set()
    crosswalk = []
    counts = {'pages': 0, 'changed_pages': 0, 'unknown_before': 0, 'unknown_after': 0}
    inputs = {}
    for volume in (2, 3, 4):
        root = source / f'volume_{volume}'
        target = output / f'volume_{volume}'
        target.mkdir()
        index = root / 'canonical_pages.tsv'
        inputs[str(index)] = sha(index.read_bytes())
        with index.open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle, delimiter='\t'))
        changes = {}
        new_rows = []
        unknown_counts = Counter()
        for row in rows:
            old_path = root / row['canonical_object']
            with gzip.open(old_path, 'rt', encoding='utf-8') as handle:
                old = json.load(handle)
            if old['page_id'] != row['page_id'] or sha(old['source_faithful_decoded_text'].encode()) != row['visible_body_sha256']:
                raise ValueError(f'old index/object mismatch: {old_path}')
            src = old['representative_source']
            digest = src['source_sha256']
            if digest not in decoded_by_sha:
                body = (cache / 'objects/sha256' / digest[:2] / digest).read_bytes()
                if sha(body) != digest:
                    raise ValueError(f'cache hash mismatch: {digest}')
                decoded_by_sha[digest] = decode_pdf_bytes(body,
                    canonical_url=src['canonical_url'], catalogue_lemma='', registry=registry)
                decoded_hashes.add(digest)
                if len(decoded_by_sha) > 8:
                    decoded_by_sha.popitem(last=False)
            decoded_by_sha.move_to_end(digest)
            page = refresh_page(old, decoded_by_sha[digest])
            unknown_counts.update(unknown_identities(page))
            relative = f"pages/{page['page_id']}.json.gz"
            if (target / relative).exists():
                raise ValueError('refresh collapsed distinct canonical pages; requires review')
            write_gzip_json(target / relative, page)
            changes[old['page_id']] = page['page_id']
            new_row = dict(row)
            new_row.update(page_id=page['page_id'], canonical_object=relative,
                visible_body_sha256=page['visible_body_sha256'],
                representative_positioned_sha256=page['representative_positioned_sha256'],
                unknown_glyph_occurrences=str(page['unknown_glyph_occurrences']))
            new_rows.append(new_row)
            crosswalk.append({'old_page_id': old['page_id'], 'new_page_id': page['page_id'],
                'volume': volume, 'printed_page': old['printed_page'],
                'pdf_sha256': digest, 'pdf_page_index': src['pdf_page_index'],
                'old_object_sha256': sha(old_path.read_bytes()),
                'new_object_sha256': sha((target / relative).read_bytes()),
                'geometry_verified': True})
            counts['pages'] += 1
            counts['changed_pages'] += old['page_id'] != page['page_id']
            counts['unknown_before'] += old['unknown_glyph_occurrences']
            counts['unknown_after'] += page['unknown_glyph_occurrences']
        for row in new_rows:
            for field in ('predecessor_page_id', 'successor_page_id'):
                if row[field]:
                    row[field] = changes[row[field]]
        write_tsv(target / 'canonical_pages.tsv', list(new_rows[0]), new_rows)
        write_unknown_census(target, unknown_counts)
        # Preserve the original observations verbatim, never stale current hashes.
        historical = target / 'historical_provenance'
        historical.mkdir()
        for path in sorted(root.iterdir()):
            if path.is_file():
                shutil.copyfile(path, historical / path.name)
    write_tsv(output / 'page_crosswalk.tsv', list(crosswalk[0]), crosswalk)
    result = {'contract_version': 'badw-canonical-refresh-v1', 'counts': counts,
        'unique_pdf_objects': len(decoded_hashes), 'source_index_sha256': inputs,
        'glyph_registry_sha256': sha(mapping.read_bytes()),
        'crosswalk_sha256': sha((output / 'page_crosswalk.tsv').read_bytes())}
    (output / 'summary.json').write_bytes(stable_json_bytes(result) + b'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mapping', type=Path, default=Path('data/badw_pdf_glyph_mappings.tsv'))
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.cache, args.output, args.mapping), indent=2))
