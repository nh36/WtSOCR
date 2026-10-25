"""Source-bound reviewed pages, never lexical or PDF-witness matching."""
import copy
import json
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject, DecodedStreamObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import badw_html_print_facsimiles as fac


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    original = tmp_path/'scan.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=900, height=640)
    writer.add_blank_page(width=460, height=640)
    image = DecodedStreamObject()
    image.set_data(bytes(range(12)))
    image.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                  NameObject('/Width'): NumberObject(2), NameObject('/Height'): NumberObject(2),
                  NameObject('/ColorSpace'): NameObject('/DeviceRGB'), NameObject('/BitsPerComponent'): NumberObject(8)})
    writer.pages[0][NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/Im0'): writer._add_object(image)})})
    with original.open('wb') as stream:
        writer.write(stream)
    digest = fac.sha256(original)
    registry = tmp_path/'registry.tsv'
    registry.write_text('label\tfilename\tsha256\nscan\tscan.pdf\t'+digest+'\n')
    common = dict(source='scan', source_sha256=digest, volume=1,
                  geometry_review='Full margins inspected', page_evidence='Visible printed folio')
    pages = dict(left=dict(common, physical_page=1, printed_page=14, side='left', crop=[0., 0., 438., 640.]),
                 right=dict(common, physical_page=1, printed_page=15, side='right', crop=[438., 0., 900., 640.]),
                 single=dict(common, physical_page=2, printed_page=1, side='single', crop=[0., 0., 460., 640.]))
    witness = dict(source_url='https://wts-digital.badw.de/lemma/ba/1', html_sha256='a'*64,
                   headword='ba', homonym=1, page='left', printed_heading='ba 1', evidence='Definition and references checked')
    reviews = tmp_path/'reviews.json'
    reviews.write_text(json.dumps(dict(version=1, pages=pages, witnesses=[witness])))
    monkeypatch.setattr(fac, 'REVIEWS', reviews)
    # Facsimiles normally reads the repository registry.
    monkeypatch.setattr(fac, 'ROOT', tmp_path)
    (tmp_path/'data').mkdir()
    (tmp_path/'data/source_pdfs.tsv').write_bytes(registry.read_bytes())
    manifest = fac.prepare(tmp_path, tmp_path/'cache', reviews, registry)
    return tmp_path, manifest, original, reviews, registry


def entry(homonym=1, kind='html'):
    return dict(source_kind=kind, source_url=f'https://wts-digital.badw.de/lemma/ba/{homonym}',
                headword=dict(loc='ba'), homonym=homonym,
                sources=[dict(url='https://wts-digital.badw.de/lemma/ba/1', sha256='a'*64, label='Editorial')])


def test_asymmetric_spread_single_and_deterministic_reuse(prepared):
    root, manifest, original, reviews, registry = prepared
    before = original.read_bytes()
    for key, expected in [('left', [0, 0, 438, 640]), ('right', [438, 0, 900, 640]), ('single', [0, 0, 460, 640])]:
        record = manifest['pages'][key]
        pdf = PdfReader(root/'cache'/record['filename'])
        assert len(pdf.pages) == 1
        assert list(pdf.pages[0].mediabox) == expected
        assert list(pdf.pages[0].cropbox) == expected
        if key != 'single':
            image = pdf.pages[0]['/Resources']['/XObject']['/Im0']
            assert image.get_data() == bytes(range(12))
            assert (image['/Width'], image['/Height'], image['/BitsPerComponent']) == (2, 2, 8)
    assert manifest['pages']['right']['printed_page'] == 15
    assert manifest['pages']['single']['physical_page'] == 2  # pagination reset, no offset arithmetic
    snapshots = {p.name: p.read_bytes() for p in (root/'cache').glob('*.pdf')}
    fac.prepare(root, root/'cache', reviews, registry)
    assert snapshots == {p.name: p.read_bytes() for p in (root/'cache').glob('*.pdf')}
    assert original.read_bytes() == before
    attach = fac.Facsimiles(root/'cache/manifest.json', root/'reader')
    first, second = entry(), entry()
    attach.attach(first)
    attach.attach(second)
    assert len(list((root/'reader/sources/print').glob('*.pdf'))) == 1
    assert first['sources'][0]['url'] == second['sources'][0]['url']
    assert first['sources'][1]['url'].endswith('#page=1&view=Fit')
    assert first['sources'][1]['print_provenance']['physical_page'] == 1
    assert not (root/'reader/sources/originals').exists()
    assert not any(p.is_symlink() for p in (root/'reader').rglob('*'))
    assert 'original_url' not in first['sources'][1]['print_provenance']
    assert str(root) not in json.dumps(first)
    assert 'file:' not in json.dumps(first)
    assert first['sources'][1]['print_provenance']['source_sha256'] == fac.sha256(original)


def test_missing_homonym_checksum_and_pdf_are_not_promoted(prepared):
    root, *_ = prepared
    attach = fac.Facsimiles(root/'cache/manifest.json', root/'reader')
    for record in [entry(2), entry(kind='pdf'), {**entry(), 'source_url':'https://wts-digital.badw.de/lemma/absent/1'}]:
        before = copy.deepcopy(record)
        attach.attach(record)
        assert record == before
    record = entry()
    record['sources'][0]['sha256'] = 'b'*64
    attach.attach(record)
    assert len(record['sources']) == 1
    record = entry()
    record['headword']['loc'] = 'other'
    with pytest.raises(ValueError, match='identity changed'):
        attach.attach(record)
    # The exact URL still identifies the reviewed witness, but an absent
    # homonym must never be silently converted to the ledger's numeral 1.
    record = entry()
    record['homonym'] = None
    with pytest.raises(ValueError, match='identity changed'):
        attach.attach(record)


def test_machine_metadata_cannot_authorize_attachment(prepared):
    root, *_ = prepared
    attach = fac.Facsimiles(root/'cache/manifest.json', root/'reader')
    record = entry()
    record['source_url'] = 'https://wts-digital.badw.de/lemma/unreviewed/1'
    record.update(eligible_for_original_print_link=True, result_category='verified',
                  reviewed_page='left', eligibility_basis='machine changed metadata')
    before = copy.deepcopy(record)
    attach.attach(record)
    assert record == before
    assert not list((root/'reader').rglob('*.pdf'))


def test_fail_closed_stale_tampered_manifest_and_derivative(prepared):
    root, manifest, *_ = prepared
    path = root/'cache/manifest.json'
    changed = copy.deepcopy(manifest)
    changed['pages']['left']['crop'][2] = 450
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='reviewed geometry'):
        fac.Facsimiles(path, root/'reader')
    path.write_text(json.dumps(manifest))
    (root/'cache'/manifest['pages']['left']['filename']).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='facsimile checksum'):
        fac.Facsimiles(path, root/'reader').attach(entry())
    changed = copy.deepcopy(manifest)
    changed['witnesses'][0]['homonym'] = 2
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='reviewed evidence'):
        fac.Facsimiles(path, root/'reader')


def test_invalid_geometry_and_source_checksums(prepared):
    root, manifest, original, reviews, registry = prepared
    page = PdfReader(original).pages[0]
    for side, crop in [('left', [0, 0, 901, 640]), ('single', [0, 0, 438, 640]), ('unknown', [0, 0, 438, 640])]:
        with pytest.raises(ValueError):
            fac.check_page(page, dict(side=side, crop=crop))
    original.write_bytes(original.read_bytes()+b'changed')
    with pytest.raises(ValueError, match='original scan checksum'):
        fac.prepare(root, root/'cache', reviews, registry)


def test_reviewed_real_pages_have_source_bound_evidence():
    reviewed = json.loads((Path(__file__).resolve().parents[1]/'data/badw_html_print_pages.json').read_text())
    assert len(reviewed['witnesses']) == 32
    assert len(reviewed['pages']) == 10
    assert {(r['headword'], r['homonym']) for r in reviewed['witnesses']} >= {('ba', 1), ('ba', 2), ('ba', 3), ('ma', 1), ('ma', 2), ('ma', 5)}
    assert all(r['evidence'] and r['html_sha256'] and r['printed_heading'] for r in reviewed['witnesses'])
    assert not any(r['headword'] == '’gyur' for r in reviewed['witnesses'])  # PDF witness stays outside scope
