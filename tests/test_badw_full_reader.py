"""Fail-closed preservation of accepted bibliography identities in full export."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_badw_full_reader import citation_baseline, preserve_relationships


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
