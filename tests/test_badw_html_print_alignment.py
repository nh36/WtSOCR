"""Independent controls for page certificates, not tests of lexical similarity."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import badw_html_print_alignment as a


@pytest.fixture
def evidence():
    body = dict(inspection_id='html:one', source_kind='html', source_url='https://wts-digital.badw.de/lemma/test/2',
                sources=[dict(sha256='a'*64)], headword=dict(loc='test'), homonym=2,
                components=[dict(type='definition', source_form='Eine bestimmte Heilpflanze.')])
    anchor = dict(anchor_id='v:41:20', volume='v', start_page=41, start_line=20)
    assertion = dict(source_id='html:one', anchor=anchor['anchor_id'], heading_position='left column',
                     printed_homonym=2, definition_evidence='bestimmte Heilpflanze', scan_review='Printed numeral 2 and plant definition, not numeral 1 meaning a vessel.',
                     html_sha256='a'*64, anchor_sha256=a.object_digest(anchor), definition_component_sha256=a.object_digest(body['components'][0]))
    edge = dict(source_id='html:one', local_anchor_id=anchor['anchor_id'])
    page = dict(key='v1-p16', family='v', source='registered', source_sha256='b'*64,
                physical_page=41, volume=1, printed_page=16, side='left', crop=[0,0,438,640],
                geometry_review='Noncentral empty gutter checked', page_evidence='Printed folio 16 visible', accepted=[assertion])
    return body, anchor, assertion, [edge], dict(pages=[page])


def test_expansion_identity_pagination_and_reproducibility(evidence):
    body, anchor, assertion, edges, cert = evidence
    args = (cert, {'html:one':body}, {anchor['anchor_id']:anchor}, edges, {'registered':dict(sha256='b'*64)})
    first = a.compile_records(*args)
    assert first == a.compile_records(*args)
    assert first['pages']['v1-p16']['physical_page'] == 41
    assert first['pages']['v1-p16']['printed_page'] == 16
    assert first['witnesses'][0]['homonym'] == 2
    # Absent is a distinct assertion, never implicitly numbered 1. Definition
    # identity is still required for the exact editorial witness.
    assertion['printed_homonym'] = None
    assert a.compile_records(*args)['witnesses'][0]['evidence']['certificate']['printed_homonym'] is None
    del assertion['printed_homonym']
    with pytest.raises(ValueError, match='explicit'):
        a.compile_records(*args)


@pytest.mark.parametrize('change, message', [
    ({'heading_position':'running header'}, 'not a heading'),
    ({'heading_position':'continuation'}, 'not a heading'),
    ({'printed_homonym':1}, 'competing'),
    ({'html_sha256':'c'*64}, 'stale'),
    ({'anchor_sha256':'c'*64}, 'stale'),
    ({'definition_component_sha256':'c'*64}, 'stale definition'),
    ({'definition_evidence':'unrelated long definition'}, 'not present'),
    ({'definition_evidence':'plant'}, 'insufficient'),
    ({'scan_review':''}, 'scan identity'),
])
def test_rejects_false_or_stale_evidence(evidence, change, message):
    body, anchor, assertion, edges, _ = evidence
    assertion.update(change)
    with pytest.raises(ValueError, match=message):
        a.validate_assertion(assertion, body, anchor, edges)


def test_wrong_source_page_duplicate_and_pdf_fail_closed(evidence):
    body, anchor, assertion, edges, cert = evidence
    def compile():
        return a.compile_records(cert, {'html:one':body}, {anchor['anchor_id']:anchor}, edges, {'registered':dict(sha256='b'*64)})
    cert['pages'][0]['source_sha256'] = 'c'*64
    with pytest.raises(ValueError, match='stale source'): compile()
    cert['pages'][0]['source_sha256'] = 'b'*64
    cert['pages'][0]['physical_page'] = 42
    with pytest.raises(ValueError, match='physical anchor'): compile()
    cert['pages'][0]['physical_page'] = 41
    body['source_kind'] = 'pdf'
    with pytest.raises(ValueError, match='HTML'): compile()
    body['source_kind'] = 'html'
    cert['pages'][0]['accepted'].append(copy.deepcopy(assertion))
    with pytest.raises(ValueError, match='twice'): compile()


def test_real_batch_is_bounded_explicit_and_contains_negative_controls():
    cert = json.loads(a.CERTIFICATE.read_text())
    generated = json.loads(a.GENERATED.read_text())
    assert generated['certificate_sha256'] == a.object_digest(cert)
    assert cert['inspected_pages'] == 40
    assert len(generated['pages']) == 38
    assert len(generated['witnesses']) == 133
    assert len({(r['source_url'], r['html_sha256']) for r in generated['witnesses']}) == 133
    assert {p['source'] for p in cert['pages']} == {'WtS_1-34','WtS_35-51','WtS_8-b','WtS_9-m'}
    assert all('printed_homonym' in r for p in cert['pages'] for r in p['accepted'])
    assert any('continu' in r['reason'] for r in cert['decisions'])
    assert any('Lexical/edition' in r['reason'] for r in cert['decisions'])
    assert not any(p['printed_page']==360 and p['volume']==5 for p in cert['pages'])
