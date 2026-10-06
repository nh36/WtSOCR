"""Synthetic tests for immutable, source-only offline replay."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from freeze_badw_relationship_predictions import (
    digest, freeze, projection_packet, verify_pdf_objects, verify_unseen_pdf_cases,
)


def packet():
    return dict(contract_version='badw-blind-relationship-review-v1', review_text='ṅa ↑',
                review_text_sha256=digest('ṅa ↑'.encode()), sampling_cue='gloss')


def test_projection_does_not_mutate_source_packet():
    original = packet()
    projected = projection_packet(original)
    assert projected['review_text'] == original['review_text']
    assert original['contract_version'] == 'badw-blind-relationship-review-v1'
    assert projected['split'] == 'development'


@pytest.mark.parametrize('change', [dict(reviewer='reviewed'),
    dict(reviewed_relationships=[{'kind': 'citation_of'}]), dict(review_text='changed'),
    dict(contract_version='unsupported')])
def test_reject_reviewed_or_changed_packet(change):
    with pytest.raises(ValueError):
        projection_packet(dict(packet(), **change))


def test_freeze_is_immutable_and_reproducible(tmp_path):
    path = tmp_path / 'predictions.jsonl'
    freeze(path, b'first\n')
    freeze(path, b'first\n')
    with pytest.raises(ValueError, match='frozen output differs'):
        freeze(path, b'second\n')
    assert path.read_bytes() == b'first\n'


@pytest.mark.parametrize('reviews', [({('seen', 0): {}}, {}), ({}, {('seen', 4): {}})])
def test_preexisting_exact_reviews_cannot_leak_into_fresh_predictions(reviews):
    with pytest.raises(ValueError, match='previously reviewed'):
        verify_unseen_pdf_cases([dict(identity='seen', source_kind='pdf')], *reviews)
    verify_unseen_pdf_cases([dict(identity='fresh', source_kind='pdf')], *reviews)


def test_pdf_objects_are_verified_offline(tmp_path):
    body = b'%PDF-synthetic-body'
    sha = digest(body)
    path = tmp_path / 'objects' / 'sha256' / sha[:2] / sha
    path.parent.mkdir(parents=True)
    path.write_bytes(body)
    verify_pdf_objects([{'pdf_sha256': sha}], tmp_path)
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='cached PDF hash mismatch'):
        verify_pdf_objects([{'pdf_sha256': sha}], tmp_path)


@pytest.mark.parametrize('objects', [[], [{'pdf_sha256': '../invalid'}]])
def test_pdf_objects_fail_closed(objects, tmp_path):
    with pytest.raises(ValueError):
        verify_pdf_objects(objects, tmp_path)
