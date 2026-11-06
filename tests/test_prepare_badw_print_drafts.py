"""Preparation binds existing inputs without generating review or authority."""
import copy

import pytest

from test_badw_html_print_alignment import evidence, fixture_rows
import badw_html_print_alignment as a
import prepare_badw_print_drafts as d


def draft(evidence):
    body, anchor, _, edges, cert = copy.deepcopy(evidence)
    cert['pages'][0]['accepted'] = []
    registry = {'WtS_1-34': {'sha256': 'b'*64}}
    return d.prepare(cert, body, anchor['anchor_id'], {anchor['anchor_id']: anchor},
                     edges, registry, fixture_rows(), 'v1-p16')


def test_reproducible_bindings_without_review(evidence):
    value = draft(evidence)
    assert value == draft(evidence)
    assert value['html_sha256'] == 'a'*64
    assert value['components'][0]['sha256'] == a.object_digest(evidence[0]['components'][0])
    assert not value['missing_bindings']
    assert value['reviewed_page']['crop'] == [0, 0, 438, 640]
    assert 'accepted' not in value['reviewed_page']
    assert not {'scan_review', 'review_basis', 'printed_homonym', 'print_observation',
                'article_boundary', 'definition_evidence'} & value.keys()
    body, anchor, _, edges, cert = copy.deepcopy(evidence)
    cert['pages'][0]['accepted'] = [value]
    with pytest.raises((ValueError, KeyError)):
        a.compile_records(cert, {body['inspection_id']: body}, {anchor['anchor_id']: anchor},
                          edges, {'WtS_1-34': {'sha256': 'b'*64}}, qa_rows=fixture_rows())


def test_missing_bindings_are_reported_not_manufactured(evidence):
    body, _, _, _, cert = copy.deepcopy(evidence)
    cert['pages'][0]['accepted'] = []
    value = d.prepare(cert, body, 'missing:1:1', {}, [], {}, {})
    assert value['anchor'] is None
    assert value['candidate_edges'] == []
    assert len(value['missing_bindings']) == 4


def test_duplicate_witness_anchor_and_wrong_page_fail(evidence):
    body, anchor, _, edges, cert = copy.deepcopy(evidence)
    args = (cert, body, anchor['anchor_id'], {anchor['anchor_id']: anchor}, edges,
            {'WtS_1-34': {'sha256': 'b'*64}}, fixture_rows())
    with pytest.raises(ValueError, match='duplicate witness'):
        d.prepare(*args)
    cert['pages'][0]['accepted'][0]['source_id'] = 'other'
    with pytest.raises(ValueError, match='already assigned'):
        d.prepare(*args)
    cert['pages'][0]['accepted'] = []
    cert['pages'][0]['physical_page'] = 42
    with pytest.raises(ValueError, match='outside reviewed page'):
        d.prepare(*args, page_key='v1-p16')
