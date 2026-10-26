"""Render binding is mechanical provenance, never verification of OCR readings."""
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_badw_coordinate_inputs import parse_hocr, validate_bundle, VERSION
from badw_html_print_alignment import FAMILIES, digest


def test_hocr_scales_exact_source_canvas_and_preserves_reading(tmp_path):
    p=tmp_path/'page.hocr'
    p.write_text('<html><div class="ocr_page" title="bbox 0 0 100 200"><span class="ocr_line" title="bbox 10 20 90 40">ཀ་ printed reading</span></div></html>')
    rows=parse_hocr(p, 50, 100, [100,200])
    assert rows==[dict(text='ཀ་ printed reading',pixel_box=[10,20,90,40],box=[5,10,45,20])]
    with pytest.raises(ValueError,match='canvas'):
        parse_hocr(p,50,100,[100,201])
    p.write_text(p.read_text().replace('10 20 90 40','10 20 101 40'))
    with pytest.raises(ValueError,match='outside'):
        parse_hocr(p,50,100,[100,200])


def test_bundle_rejects_wrong_source_missing_pages_and_changed_files(tmp_path):
    registry={label:dict(sha256='source-'+family,pages='1') for family,label in FAMILIES.items()}
    manifest=dict(schema=1,method=VERSION,files={},pages={},sources={})
    for family,label in FAMILIES.items():
        p=tmp_path/(family+'.jsonl')
        p.write_text(json.dumps(dict(family=family,physical_page=1,source_sha256=registry[label]['sha256'],method=VERSION))+'\n')
        manifest['files'][p.name]=digest(p)
        manifest['pages'][family]=1
        manifest['sources'][family]=registry[label]['sha256']
    target=tmp_path/'manifest.json'
    target.write_text(json.dumps(manifest))
    assert validate_bundle(tmp_path,registry)==manifest
    family=next(iter(FAMILIES));p=tmp_path/(family+'.jsonl')
    p.write_text(p.read_text().replace('"physical_page": 1','"physical_page": 2'))
    with pytest.raises(ValueError,match='checksum'):
        validate_bundle(tmp_path,registry)
    manifest['files'][p.name]=digest(p);target.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='page identity'):
        validate_bundle(tmp_path,registry)


def test_empty_ocr_retains_page_without_inventing_locations(tmp_path):
    p=tmp_path/'empty.hocr'
    p.write_text('<html><div class="ocr_page" title="bbox 0 0 100 200"/></html>')
    assert parse_hocr(p,50,100,[100,200]) == []
