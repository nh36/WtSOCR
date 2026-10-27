import json
from pathlib import Path
import sys

import pytest
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_badw_editorial_collection import build, digest, extract_page, select_text


def fixture_inputs(tmp_path):
    source = tmp_path / 'scan.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=920, height=674)
    with source.open('wb') as stream:
        writer.write(stream)
    row = dict(zone_id='intro', scan_page=1, source_label='scan',
               pdf_sha256=digest(source), ocr_sha256='a' * 64,
               reading_status='unreviewed_ocr',
               source_span=dict(start=0, end=30, raw_text='=== page 1 ===\nImprint\nVorwort\nText\nBibliography'))
    inventory = tmp_path / 'inventory.jsonl'
    inventory.write_text(json.dumps(row) + '\n')
    config = tmp_path / 'config.json'
    selection = dict(scan_page=1, start='Vorwort', end_before='Bibliography',
                     views=[dict(side='right', folio='i', gutter_fraction=.486)])
    doc = dict(id='intro', title='Vorwort', volume='Lieferung 1', category='Preface',
               authors=[], sections=[selection])
    config.write_text(json.dumps(dict(inventory_sha256=digest(inventory), documents=[doc])))
    registry = tmp_path / 'sources.tsv'
    registry.write_text('label\tfilename\tsha256\nscan\tscan.pdf\t' + digest(source) + '\n')
    return source, inventory, config, registry


def run_build(tmp_path, name='reader'):
    source, inventory, config, registry = fixture_inputs(tmp_path)
    output = tmp_path / name
    result = build(output, tmp_path, config, inventory, registry)
    return output, result, source


def test_shared_deterministic_pages_and_private_boundary(tmp_path):
    source, inventory, config, registry = fixture_inputs(tmp_path)
    data = json.loads(config.read_text())
    data['documents'][0]['sections'] *= 2
    config.write_text(json.dumps(data))
    before = digest(source)
    first, second = tmp_path / 'first', tmp_path / 'second'
    for output in (first, second):
        assert build(output, tmp_path, config, inventory, registry) == dict(documents=1, source_sections=2, derivatives=1)
    manifest = json.loads((first / 'collection.json').read_text())
    assert manifest['distribution_authorised'] is False
    assert manifest['local_research_only'] is True
    section = manifest['documents'][0]['sections'][0]
    assert section['text'] == 'Vorwort\nText'
    assert section['reading_status'] == 'unreviewed_ocr'
    view = section['views'][0]
    assert list(PdfReader(first / view['url']).pages[0].mediabox) == [447.12, 0, 920, 674]
    assert digest(source) == before
    assert (first / 'collection.json').read_bytes() == (second / 'collection.json').read_bytes()
    assert digest(first / view['url']) == digest(second / view['url']) == view['sha256']
    assert str(tmp_path) not in (first / 'collection.json').read_text()
    assert not any(p.is_symlink() for p in first.rglob('*'))
    assert len(list(first.rglob('*.pdf'))) == 1
    assert not (first / 'scan.pdf').exists()


def test_single_page_preserves_geometry(tmp_path):
    source, inventory, config, registry = fixture_inputs(tmp_path)
    data = json.loads(config.read_text())
    data['documents'][0]['sections'][0]['views'] = [dict(side='single', folio='ii')]
    config.write_text(json.dumps(data))
    output = tmp_path / 'reader'
    build(output, tmp_path, config, inventory, registry)
    assert list(PdfReader(next((output / 'pages').glob('*.pdf'))).pages[0].mediabox) == [0, 0, 920, 674]


def test_stale_inventory_and_scan_rejected(tmp_path):
    source, inventory, config, registry = fixture_inputs(tmp_path)
    inventory.write_text(inventory.read_text() + '\n')
    with pytest.raises(ValueError, match='inventory changed'):
        build(tmp_path / 'reader', tmp_path, config, inventory, registry)
    data = json.loads(config.read_text())
    data['inventory_sha256'] = digest(inventory)
    config.write_text(json.dumps(data))
    source.write_bytes(source.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='checksum mismatch'):
        build(tmp_path / 'reader', tmp_path, config, inventory, registry)


def test_text_boundaries_and_review_status():
    row = dict(source_span=dict(raw_text='=== page 1 ===\nVorwort'), verified_editorial_transcription='Reviewed text')
    assert select_text(row, {}) == 'Reviewed text'
    with pytest.raises(ValueError, match='nonunique'):
        select_text(row, dict(start='absent'))


def test_invalid_crop_and_rotation(tmp_path):
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=200)
    with pytest.raises(ValueError, match='outside'):
        extract_page(page, [-1, 0, 100, 200], tmp_path / 'page.pdf')
    page.rotate(90)
    with pytest.raises(ValueError, match='rotation'):
        extract_page(page, [0, 0, 100, 200], tmp_path / 'page.pdf')
