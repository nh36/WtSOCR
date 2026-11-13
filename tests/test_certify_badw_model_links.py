"""Source-derived controls for the bounded automated certification policy."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import certify_badw_model_links as c

FIXTURE = Path(__file__).parent/'fixtures/badw_model_policy_examples.json'


@pytest.fixture
def positive():
    return (copy.deepcopy(json.loads(c.CONTROLS.read_text())['candidates'][0]),
            json.loads(FIXTURE.read_text())['positive_body'])


def test_source_derived_positive_and_descriptive_absence(positive):
    row, body = positive
    assert c.policy_reason(row, body, 1) is None
    for observation in c.readings(row)[0] + c.readings(row)[1]:
        observation['uncertainty'] = 'No printed numeral visible.'
    assert c.policy_reason(row, body, 1) is None


@pytest.mark.parametrize('field,value', [
    ('classification', 'running_header'), ('classification', 'continuation'),
    ('heading_loc', 'another article'), ('printed_homonym', 2),
    ('uncertainty', 'Could be the preceding article; numeral unclear'),
    ('preceding', ''), ('following', ''),
])
def test_independent_source_negative_controls(positive, field, value):
    row, body = positive
    row['second_reading']['inventory'][0][field] = value
    assert c.policy_reason(row, body, 1)


def test_editorial_split_and_prior_decisions_abstain(positive):
    row, body = positive
    assert c.policy_reason(row, body, 2)
    row['previous_decisions'] = [{'decision': 'defer'}]
    assert c.policy_reason(row, body, 1) == 'prior decision'


@pytest.mark.parametrize('change', ['identity','checksum','quote','component','unsupported','short'])
def test_exact_identity_lexical_and_component_controls(positive, change):
    row, body = positive
    if change == 'identity': row['second_reading']['matching'][0]['source_id'] = 'wrong identity'
    if change == 'checksum': row['html_sha256'] = '0'*64
    if change == 'quote': row['second_reading']['matching'][0]['html_evidence'] = 'invented quotation'
    if change == 'component': row['component_index'] = 0
    if change == 'unsupported': row['second_reading']['matching'][0]['outcome'] = 'insufficient'
    if change == 'short':
        for m in c.readings(row)[1]: m['printed_evidence'] = 'generic gloss'
    assert c.policy_reason(row, body, 1)


def test_pool_and_prior_inspections_are_preserved():
    controls = json.loads(c.CONTROLS.read_text())
    assert len(controls['candidates']) == 92
    assert len({r['source_id'] for r in controls['candidates']}) == 92
    assert len(controls['inspections']) == 32
    fixture = json.loads(FIXTURE.read_text())
    assert len(fixture['audit']) == 8
    # Audit includes seven examples OUTSIDE the proposed acceptance class.
    assert sum(r['in_initial_pool'] for r in fixture['audit']) == 1
    assert all(r['identity_correct'] for r in fixture['audit'])
    ref = c.a.ROOT/fixture['heldout']['reference']
    assert c.a.digest(ref) == fixture['heldout']['reference_sha256']


@pytest.mark.parametrize('observation', json.loads(FIXTURE.read_text())['audit'],
                         ids=lambda o: o['body']['headword']['loc'])
def test_source_first_sample_not_selected_by_policy(observation):
    # Apply the actual policy to independently sampled cached cases, including
    # numbered headings, reference-only entries and descriptive uncertainty.
    reason = c.policy_reason(observation['cached_row'], observation['body'],
                             observation['headword_count'])
    assert reason == observation['expected_policy_reason']
    if reason is None:
        assert observation['identity_correct']


def test_compiler_rejects_unvalidated_pool_even_with_matching_controls_hash():
    assertion = dict(certificate_type=c.TYPE, review_basis=c.BASIS, policy=c.POLICY,
                     controls_sha256=c.a.digest(c.CONTROLS), model_evidence={},
                     page_observations={})
    with pytest.raises(ValueError, match='outside validated production pool'):
        c.validate_model(assertion, {}, {}, ())


def test_original_page_geometry_rejects_swapped_scan(tmp_path):
    fitz = pytest.importorskip('pymupdf')
    pdf_path = tmp_path/'source.pdf'
    with fitz.open() as pdf:
        for text in ('original physical page one', 'different physical page two'):
            page = pdf.new_page(width=300.64, height=400.44)
            page.insert_text((30, 40), text)
        pdf.save(pdf_path)
    directory = tmp_path/'pages'/'family-1'; directory.mkdir(parents=True)
    with fitz.open(pdf_path) as pdf:
        page = pdf[0]; pix = page.get_pixmap(alpha=False)
        png = pix.tobytes('png'); box = list(page.mediabox)
        transform = dict(pdf_crop=box, pdf_to_mupdf=list(page.transformation_matrix),
                         points_per_pixel=[1,1], image_device_origin=[pix.x,pix.y])
    (directory/'page.png').write_bytes(png)
    image = dict(path='page.png', sha256=hashlib.sha256(png).hexdigest(),
                 dpi=72, pixels=[pix.width,pix.height], transform=transform)
    source = dict(filename=str(pdf_path), sha256=c.a.digest(pdf_path), label='test source')
    pack = dict(source=source['label'], source_sha256=source['sha256'], image=image,
                family='family', physical_page=1)
    (directory/'pack.json').write_text(json.dumps(pack))
    args = (str(tmp_path), 'family-1', json.dumps(source), json.dumps(image))
    # Publish exact PDF coordinates rather than MuPDF float32 roundoff.
    exact = c.original_media_box(str(pdf_path), 1)
    assert c.source_geometry(*args) == exact
    assert exact != box
    # A self-consistent cached hash cannot establish the correct physical page.
    pack['physical_page'] = 2
    pack['family'] = 'family'; (directory/'pack.json').write_text(json.dumps(pack))
    c.source_geometry.cache_clear()
    with pytest.raises(ValueError, match='source page binding'): c.source_geometry(*args)
    pack['physical_page'] = 1
    (directory/'pack.json').write_text(json.dumps(pack))
    with fitz.open(pdf_path) as pdf: swapped = pdf[1].get_pixmap(alpha=False).tobytes('png')
    image['sha256'] = hashlib.sha256(swapped).hexdigest()
    (directory/'page.png').write_bytes(swapped); pack['image'] = image
    (directory/'pack.json').write_text(json.dumps(pack))
    with pytest.raises(ValueError, match='registered physical scan'):
        c.source_geometry(str(tmp_path), 'family-1', json.dumps(source), json.dumps(image))
