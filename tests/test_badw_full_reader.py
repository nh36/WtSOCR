"""Fail-closed preservation of accepted bibliography identities in full export."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_badw_full_reader import citation_baseline, preserve_relationships
from census_badw_reader_references import classify
from resolve_badw_cross_references import EntryIndex


def test_census_uses_reviewed_editorial_target_without_claiming_print_review():
    url = 'https://wts-digital.badw.de/lemma/%3Ctib%3Eabsent/1'
    ref = dict(source_url=url, wording='absent', status='unresolved',
               resolution_evidence=dict(method='reviewed_exact_editorial_target',
                   target_review=dict(lemma='absent', source_target_url=url)))
    diagnosis = classify(ref, ref, EntryIndex([]))
    assert diagnosis['target_label'] == 'absent'
    assert diagnosis['classification'] == 'missing_exact_identity'
    assert diagnosis['review_status'] == 'editorial_link_reviewed_destination_absent'
    assert diagnosis['printed_facsimile_checked'] is False
    ref['resolution_evidence']['target_review']['source_target_url'] = 'different'
    assert classify(ref, ref, EntryIndex([]))['target_label'] == '<tib>absent'


def test_baseline_requires_exact_original_citation_span():
    packet = {'review_text': 'a citation b'}
    projection = {'nodes': [{'kind': 'citation', 'start': 2, 'end': 10}]}
    citation = {'source_form': 'citation', 'accepted_authority_ids': ['original']}
    assert citation_baseline(packet, projection, {'citations': [citation]}) == {(2, 10): citation}
    with pytest.raises(ValueError, match='count mismatch'):
        citation_baseline(packet, projection, {'citations': []})
    with pytest.raises(ValueError, match='literal mismatch'):
        citation_baseline(packet, projection, {'citations': [{**citation, 'source_form': 'other'}]})
    with pytest.raises(ValueError, match='duplicate'):
        citation_baseline(packet, {'nodes': projection['nodes'] * 2}, {'citations': [citation] * 2})


def test_relationship_preservation_rejects_loss_but_accepts_gains():
    import copy
    before = dict(citations=[dict(component_id='c', accepted_authority_ids=['a'],
        ownership='owned', supports=['passage'], sense_node_id='sense')],
        cross_references=[dict(component_id='r', status='resolved', target_entry_id='entry',
            candidate_entry_ids=['entry'])])
    after = copy.deepcopy(before)
    after['citations'][0]['accepted_authority_ids'].append('additional')
    preserve_relationships(before, after)
    for key, value, message in [('accepted_authority_ids', [], 'identity'),
            ('ownership', 'unresolved', 'ownership'), ('supports', ['other'], 'ownership'),
            ('sense_node_id', 'other', 'ownership')]:
        changed = copy.deepcopy(after)
        changed['citations'][0][key] = value
        with pytest.raises(ValueError, match=message):
            preserve_relationships(before, changed)
    for key, value in [('status', 'ambiguous'), ('candidate_entry_ids', ['different'])]:
        changed = copy.deepcopy(after)
        changed['cross_references'][0][key] = value
        with pytest.raises(ValueError, match='cross-reference'):
            preserve_relationships(before, changed)
