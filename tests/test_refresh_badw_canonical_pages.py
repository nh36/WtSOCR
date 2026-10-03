"""Synthetic regression tests for immutable registry refreshes."""
from copy import deepcopy
import csv
import gzip
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from refresh_badw_canonical_pages import (refresh_page, source_geometry,
                                         unknown_identities, write_unknown_census)
from badw_canonical_pages import stable_json_bytes


def fixture():
    positioned = {
        'visible_text': 'UNKNOWN', 'normalized_reading': 'UNKNOWN',
        'unknown_glyphs': 1,
        'positioned_text_runs': [{
            'run_index': 0, 'x': 12, 'y': 24, 'font_id': 'f1',
            'decoded_unicode': 'UNKNOWN', 'unknown_glyphs': 1,
            'glyphs': [{'cid_hex': '0001', 'glyph_signature': 'outline',
                        'x': 12, 'y': 24, 'unicode': 'UNKNOWN',
                        'unknown': True, 'mapping_method': 'unregistered'}]}]}
    old = {'page_id': 'old', 'volume': 2, 'printed_page': 1,
           'representative_source': {'source_sha256': 'abc', 'pdf_page_index': 1},
           'positioned_page': positioned, 'glyph_registry_sha256': 'old-registry',
           'representative_positioned_sha256': 'old-positioned'}
    new = deepcopy(positioned)
    new.update(visible_text='ź', normalized_reading='ź', unknown_glyphs=0)
    run = new['positioned_text_runs'][0]
    run.update(decoded_unicode='ź', unknown_glyphs=0)
    run['glyphs'][0].update(unicode='ź', unknown=False, mapping_method='reviewed')
    decoded = {'source_sha256': 'abc', 'pages': [new], 'fonts': [],
               'decoder_version': 'v1', 'contract_version': 'c1',
               'glyph_registry_sha256': 'new-registry'}
    return old, decoded


def test_refresh_preserves_geometry_and_old_record():
    old, decoded = fixture()
    before = deepcopy(old)
    refreshed = refresh_page(old, decoded)
    assert old == before
    assert refreshed['source_faithful_decoded_text'] == 'ź'
    assert refreshed['unknown_glyph_occurrences'] == 0
    assert refreshed['refresh_provenance']['previous_page_id'] == 'old'
    assert refreshed['glyph_registry_sha256'] == 'new-registry'
    assert source_geometry(old['positioned_page']) == source_geometry(decoded['pages'][0])
    assert stable_json_bytes(refreshed) == stable_json_bytes(refresh_page(old, decoded))


@pytest.mark.parametrize('field,value', [('x', 13), ('cid_hex', '0002'),
                                         ('glyph_signature', 'different')])
def test_source_changes_fail_closed(field, value):
    old, decoded = fixture()
    decoded['pages'][0]['positioned_text_runs'][0]['glyphs'][0][field] = value
    with pytest.raises(ValueError, match='geometry'):
        refresh_page(old, decoded)


def test_wrong_pdf_hash_fails_closed():
    old, decoded = fixture()
    decoded['source_sha256'] = 'different'
    with pytest.raises(ValueError, match='source hash'):
        refresh_page(old, decoded)


def test_current_unknown_census_counts_positioned_glyphs(tmp_path):
    old, _ = fixture()
    old['representative_fonts'] = [{'font_id': 'f1', 'family': 'Synthetic',
                                   'style': 'regular'}]
    old['unknown_glyph_occurrences'] = 1
    counts = unknown_identities(old)
    assert counts == {('Synthetic', 'regular', '0001', 'outline'): 1}
    write_unknown_census(tmp_path, counts)
    first = (tmp_path / 'canonical_unknown_glyphs.tsv').read_bytes()
    write_unknown_census(tmp_path, counts)
    assert first == (tmp_path / 'canonical_unknown_glyphs.tsv').read_bytes()
    old['unknown_glyph_occurrences'] = 0
    with pytest.raises(ValueError, match='census'):
        unknown_identities(old)


def test_build_is_offline_immutable_and_rewrites_page_links(tmp_path, monkeypatch):
    import refresh_badw_canonical_pages as module
    from badw_canonical_pages import write_gzip_json, write_tsv

    source, cache, output = (tmp_path / name for name in ('source', 'cache', 'output'))
    body = b'synthetic cached PDF bytes'
    digest = module.sha(body)
    object_path = cache / 'objects/sha256' / digest[:2] / digest
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(body)
    mapping = tmp_path / 'mapping.tsv'
    mapping.write_text('synthetic registry', encoding='utf-8')
    calls = []
    old, decoded = fixture()
    decoded['source_sha256'] = digest
    decoded['fonts'] = [{'font_id': 'f1', 'family': 'Synthetic', 'style': 'regular'}]
    monkeypatch.setattr(module.GlyphRegistry, 'from_tsv', lambda path: object())

    def decode(cached, **kwargs):
        assert cached == body
        calls.append(kwargs['canonical_url'])
        return deepcopy(decoded)

    monkeypatch.setattr(module, 'decode_pdf_bytes', decode)
    for volume in (2, 3, 4):
        root = source / f'volume_{volume}'
        root.mkdir(parents=True)
        page = deepcopy(old)
        page.update(volume=volume, page_id=f'old-{volume}',
                    unknown_glyph_occurrences=1,
                    source_faithful_decoded_text='UNKNOWN')
        page['representative_source'].update(source_sha256=digest,
                                             canonical_url='https://example.test/pdf')
        write_gzip_json(root / 'pages/old.json.gz', page)
        row = {'page_id': page['page_id'], 'canonical_object': 'pages/old.json.gz',
               'visible_body_sha256': module.sha(b'UNKNOWN'),
               'representative_positioned_sha256': 'old-positioned',
               'unknown_glyph_occurrences': '1',
               'predecessor_page_id': page['page_id'], 'successor_page_id': ''}
        write_tsv(root / 'canonical_pages.tsv', list(row), [row])
    result = module.build(source, cache, output, mapping)
    assert result['counts'] == {'pages': 3, 'changed_pages': 3,
                               'unknown_before': 3, 'unknown_after': 0}
    assert result['unique_pdf_objects'] == len(calls) == 1
    for volume in (2, 3, 4):
        root = output / f'volume_{volume}'
        with (root / 'canonical_pages.tsv').open(encoding='utf-8') as handle:
            row = next(csv.DictReader(handle, delimiter='\t'))
        assert row['predecessor_page_id'] == row['page_id']
        assert row['page_id'] != f'old-{volume}'
        with gzip.open(root / row['canonical_object'], 'rt', encoding='utf-8') as handle:
            assert json.load(handle)['source_faithful_decoded_text'] == 'ź'
        assert (root / 'historical_provenance/canonical_pages.tsv').read_bytes() == (
            source / f'volume_{volume}/canonical_pages.tsv').read_bytes()
        assert (root / 'canonical_unknown_glyphs.tsv').read_text().count('\n') == 1
    with pytest.raises(FileExistsError, match='refusing to replace'):
        module.build(source, cache, output, mapping)
