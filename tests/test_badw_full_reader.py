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


def test_census_keeps_reviewed_printed_expansion_and_absent_destination_separate():
    ref=dict(wording='bag la ~',status='unresolved',
        parsed_target=dict(lexical_target='bag la ~'),
        resolution_evidence=dict(method='reviewed_exact_printed_substitution',
            target_review=dict(lemma='bag la ñal')))
    diagnosis=classify(ref,ref,EntryIndex([]))
    assert diagnosis['target_label']=='bag la ñal'
    assert diagnosis['printed_facsimile_checked'] is True
    assert diagnosis['classification']=='missing_exact_identity'
    assert diagnosis['review_status']=='printed_abbreviation_reviewed_destination_absent'
    assert 'No printing error or acquisition gap established' in diagnosis['diagnostic_reason']


def test_reviewed_arrow_contraction_keeps_accepted_member_as_single_target():
    import copy
    from badw_dictionary_entry_view import identifier
    binding=dict(identity='entry',text_sha256='review-hash')
    old_span=dict(start=0,end=9);new_span=dict(start=0,end=3)
    old_id=identifier('entry','review-hash','cross_reference',0,9)
    printed=dict(literal='ka',lexical_target='ka',source_span=dict(start=1,end=3))
    review=dict(kind='cross_reference_extent',effective_status='accepted',
        claim=dict(basis='reviewed_printed_arrow_boundary',
                   previous_range=dict(**old_span,literal='↑ka,\n↓kha')),
        ranges=[dict(**new_span,literal='↑ka')])
    member=dict(literal='ka',source_span=dict(start=1,end=3),
        source_binding=dict(identity='entry',text_sha256='faithful-hash'),
        resolution_status='resolved',target_entry_id='dest',target_lexical_entity='entity',
        exact_index_candidate_ids=['dest'],printed_target=printed)
    before=dict(citations=[],cross_references=[dict(component_id=old_id,status='unresolved',
        source_span=old_span,source_binding=binding,target_members=[member])])
    new=dict(component_id=identifier('entry','review-hash','cross_reference',0,3),
        supersedes_component_id=old_id,extent_review=review,source_span=new_span,
        source_binding=binding,status='resolved',wording='ka',target_entry_id='dest',
        target_lexical_entity='entity',candidate_entry_ids=['dest'],parsed_target=printed)
    after=dict(citations=[],cross_references=[new])
    preserve_relationships(before,after,[review])
    for key,value in [('wording','kha'),('target_entry_id','other'),
            ('target_lexical_entity','other'),('candidate_entry_ids',['other']),
            ('parsed_target',dict(lexical_target='different')),('status','ambiguous')]:
        changed=copy.deepcopy(after);changed['cross_references'][0][key]=value
        with pytest.raises(ValueError,match='member changed'):
            preserve_relationships(before,changed,[review])
    extra=copy.deepcopy(before);extra['cross_references'][0]['target_members'].append(
        dict(member,literal='kha',source_span=dict(start=6,end=9)))
    with pytest.raises(ValueError,match='member changed'):
        preserve_relationships(extra,after,[review])
    with pytest.raises(ValueError,match='occurrence lost'):
        preserve_relationships(before,after)


def test_reindex_stages_only_the_exact_reviewed_arrow_contraction(monkeypatch):
    import copy
    import build_badw_full_reader as builder
    old = dict(visual_start=1, visual_end=20)
    new = dict(visual_start=1, visual_end=8)
    following = dict(visual_start=10, visual_end=20)
    original = dict(candidates=dict(cross_references=[old, following]))
    current = dict(candidates=dict(cross_references=[new, following]))
    monkeypatch.setattr(builder, 'reindex_article', lambda _: copy.deepcopy(current))
    review = dict(kind='cross_reference_extent', claim=dict(
        basis='reviewed_printed_arrow_boundary', previous_range=dict(start=1,end=20)),
        ranges=[dict(start=1,end=8)])
    assert builder.reindex_for_review(original, [review]) == original
    assert current['candidates']['cross_references'][0] == new
    for reviews in ([], [review,review], [{**review, 'ranges':[dict(start=1,end=9)]}],
                    [{**review, 'claim':{**review['claim'], 'basis':'reviewed_printed_extent'}}]):
        with pytest.raises(ValueError, match='explicit structural replay'):
            builder.reindex_for_review(original, reviews)
    current['candidates']['cross_references'].append(dict(visual_start=22,visual_end=30))
    with pytest.raises(ValueError, match='explicit structural replay'):
        builder.reindex_for_review(original, [review])


@pytest.mark.parametrize('arguments', [
    ['--witness-ids', 'ids.json'], ['--baseline-reader', 'baseline'],
])
def test_affected_witness_mode_requires_paired_baseline(monkeypatch, arguments):
    import build_badw_full_reader as builder
    monkeypatch.setattr('sys.argv', ['builder', '--output', 'work/unused', *arguments])
    with pytest.raises(SystemExit) as error:
        builder.main()
    assert error.value.code == 2


@pytest.mark.parametrize('selection', [[], 'source', ['source', 'source'], [42]])
def test_affected_witness_mode_rejects_invalid_selection(tmp_path, monkeypatch, selection):
    import json
    import build_badw_full_reader as builder
    path = tmp_path/'ids.json'
    path.write_text(json.dumps(selection))
    monkeypatch.setattr('sys.argv', ['builder', '--output', 'work/unused',
        '--witness-ids', str(path), '--baseline-reader', str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        builder.main()
    assert error.value.code == 2


def test_catalogue_independent_print_sequences():
    import json
    from build_badw_full_reader import prepare_catalogue
    fixture = json.loads((Path(__file__).parent/'fixtures/wts_tibetan_order.json').read_text())
    for sequence in fixture['sequences']:
        entries = [dict(id=f'pdf:{i}', headword=dict(tibetan=word, loc=f'roman-{99-i}'), source_kind='pdf') for i, word in enumerate(sequence)]
        prepared = prepare_catalogue(list(reversed(entries)))
        assert [e['headword']['tibetan'] for e in prepared['entries']] == sequence
        assert prepared['collation']['fallback'] == 0


def test_catalogue_numeric_homonyms_witnesses_fallback_and_source_preservation():
    import copy
    from build_badw_full_reader import prepare_catalogue
    entries = [dict(id=f'{kind}:{number}', headword=dict(tibetan='འགྱུར་།' if kind=='pdf' else 'འགྱུར་', loc='’gyur'),
                    homonym=number, source_kind=kind, search_aliases=['‘alternative'])
               for number in [10, 2, 1] for kind in ['pdf', 'html']]
    for identity, tibetan in [('missing', ''), ('mixed', 'ཀā'), ('sanskrit', 'ཀཱ'), ('stack', 'ཀརྐ'), ('noncanonical', 'ཀཷ')]:
        entries.append(dict(id=identity, headword=dict(tibetan=tibetan, loc=identity)))
    original = copy.deepcopy(entries)
    prepared = prepare_catalogue(entries)
    actual = prepared['entries']
    assert entries == original
    assert [e['id'] for e in actual[:6]] == ['html:1','pdf:1','html:2','pdf:2','html:10','pdf:10']
    assert len(actual) == len(entries)
    assert {e['id'] for e in actual} == {e['id'] for e in original}
    assert prepared['collation']['keyed'] == 6
    assert prepared['collation']['fallback'] == 5
    for e in actual[:6]:
        assert e['headword']['loc'] == '’gyur'
        assert e['search_keys'][0] == "'gyur"
        assert "'alternative" in e['search_keys']
    again = prepare_catalogue(list(reversed(entries)))
    assert again['entries'] == actual
