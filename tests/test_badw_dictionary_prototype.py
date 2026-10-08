import copy
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_badw_dictionary_prototype import view
from resolve_badw_cross_references import EntryIndex


def record():
    text = 'für skt. Viṣṇus'
    entry = dict(record_type='entry', id='entry:1', headword=dict(loc='ka'), homonym='', stable_url='https://wts-digital.badw.de/lemma/ka/1')
    return dict(contract_version='badw-structural-candidate-projection-v6', identity='source:1',
                source_kind='html', source=dict(article_source_text=text),
                review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                nodes=[dict(id='n1',kind='definition',start=0,end=len(text))],
                original_records=[entry],edges=[],semantic_annotations=[],semantic_relationships=[])


def test_view_preserves_source_contract_without_inventing_relationships():
    r = record()
    before = copy.deepcopy(r)
    output = view([r], EntryIndex(r['original_records']))
    assert r == before
    assert output[0]['projection'] == r
    assert output[0]['review_text'] == 'für skt. Viṣṇus'
    assert output == view([r], EntryIndex(r['original_records']))


def test_exact_reference_resolves_but_printed_reference_is_not_guessed():
    r = record()
    ref = dict(record_type='cross_reference',id='ref',target_label='ka',marker='↑',
               source_spans=[dict(start=0,end=2)], target_url=r['original_records'][0]['stable_url'])
    r['original_records'].append(ref)
    output = view([r], EntryIndex(r['original_records']))
    assert output[0]['cross_references'][0]['canonical_resolution']['target_entry_id']=='entry:1'
    assert 'canonical_resolution' not in ref
    del ref['target_url']
    assert view([r], EntryIndex(r['original_records']))[0]['cross_references'][0]['canonical_resolution']['status']=='unresolved'


def test_pdf_uses_exact_index_identity_and_keeps_printed_candidates_unresolved():
    r = record()
    entry = r.pop('original_records')[0]
    entry['id'] = r['identity']
    r['source_kind'] = 'pdf'
    text = 'für\u2028skt. Viṣṇus'
    r['source'] = dict(visual_lines=[dict(text=text)])
    r['review_text_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    r['original_structure'] = dict(candidates=dict(cross_references=[
        dict(marker='↑', target_label_candidate='ka', visual_start=0, visual_end=2)]))
    before = copy.deepcopy(r)
    result = view([r], EntryIndex([entry]))[0]
    assert result['entry'] == entry
    assert result['review_text'] == text
    assert 'canonical_resolution' not in result['cross_references'][0]
    assert r == before
    with pytest.raises(ValueError, match='actual entry'):
        view([r], EntryIndex([]))


@pytest.mark.parametrize('damage',['hash','bounds','parent','duplicate','cycle'])
def test_rejects_inconsistent_projection(damage):
    r=record()
    if damage=='hash':r['review_text_sha256']='bad'
    if damage=='bounds':r['nodes'][0]['end']=100
    if damage=='parent':r['nodes'][0]['parent']='missing'
    if damage=='cycle':r['nodes'][0]['parent']='n1'
    with pytest.raises(ValueError):view([r,r] if damage=='duplicate' else [r],EntryIndex(r['original_records']))
