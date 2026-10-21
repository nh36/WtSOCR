"""Fail-closed preservation of accepted bibliography identities in full export."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_badw_full_reader import citation_baseline, preserve_relationships
from census_badw_reader_references import classify, case_record
from resolve_badw_cross_references import EntryIndex


def test_residual_member_retains_its_own_parse_and_source_view():
    ref = dict(component_id='parent', wording='ka, kha', status='unresolved',
        source_binding=dict(identity='same-source', text_sha256='parent-view'),
        source_span=dict(start=1,end=8), parsed_target=dict(lexical_target='ka, kha'))
    unit = dict(member_id='member-2', literal='kha', resolution_status='unresolved',
        source_span=dict(start=5,end=8), printed_target=dict(lexical_target='kha'),
        source_binding=dict(identity='same-source',text_sha256='member-view'),
        resolution_evidence=dict(reason='missing_exact_identity'))
    entry = dict(id='entry',headword=dict(loc='source'),source_kind='pdf',sources=[],
        components=[dict(id='parent',source_form='↑ka, kha')])
    case = case_record(entry,ref,unit,EntryIndex([]))
    assert case['target_label'] == 'kha'
    assert case['literal'] == 'kha'
    assert case['member_id'] == 'member-2'
    assert case['source_span'] == unit['source_span']
    assert case['source_binding'] == unit['source_binding']
    assert case['parent_source_binding'] == ref['source_binding']
    assert case['resolution_evidence'] == unit['resolution_evidence']
    assert case['printed_facsimile_checked'] is False


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


def test_extent_transition_needs_validated_review_and_preserves_accepted_members():
    import copy
    from badw_dictionary_entry_view import identifier
    binding=dict(identity='entry',text_sha256='hash')
    old_span=dict(start=2,end=8);new_span=dict(start=2,end=12)
    old_id=identifier('entry','hash','cross_reference',2,8)
    review=dict(kind='cross_reference_extent',effective_status='accepted',
        claim=dict(previous_range=dict(**old_span,literal='↑ka, k')),
        ranges=[dict(**new_span,literal='↑ka, kha ga')])
    member=dict(literal='ka',source_span=dict(start=3,end=5),source_binding=binding,
        resolution_status='resolved',target_entry_id='destination',printed_target=dict(lexical_target='ka'))
    before=dict(citations=[],cross_references=[dict(component_id=old_id,status='unresolved',
        source_span=old_span,source_binding=binding,target_members=[member])])
    after=copy.deepcopy(before)
    after['cross_references'][0].update(component_id=identifier('entry','hash','cross_reference',2,12),
        supersedes_component_id=old_id,extent_review=review,source_span=new_span)
    preserve_relationships(before,after,[review])
    with pytest.raises(ValueError,match='occurrence lost'): preserve_relationships(before,after)
    for key,value in [('target_entry_id','other'),('source_binding',dict(identity='other',text_sha256='hash')),
                      ('resolution_status','unresolved'),('printed_target',dict(lexical_target='different'))]:
        changed=copy.deepcopy(after);changed['cross_references'][0]['target_members'][0][key]=value
        with pytest.raises(ValueError,match='member changed'): preserve_relationships(before,changed,[review])
    changed=copy.deepcopy(after);changed['cross_references'][0]['source_span']['end']=13
    with pytest.raises(ValueError,match='unbound'): preserve_relationships(before,changed,[review])
